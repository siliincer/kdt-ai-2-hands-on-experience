"""계약 기반 업무 Workflow를 하나의 서비스 실행 Graph로 조립한다."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, cast

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, StateGraph

from agent.clients.backend import BackendWebhookClient
from agent.contracts.backend import AgentWebhookRequest
from agent.nodes import global_guardrail_node
from agent.runtime import (
    ExecutionGraph,
    InteractionPauseRuntime,
    InteractionWebhookBuilder,
)
from agent.state import AgentState
from agent.tools.contract_registry import ContractToolRegistry
from agent.workflow_matcher import match_workflow
from agent.workflows.account_list import (
    AccountListDependencies,
    build_account_list_graph,
)
from agent.workflows.balance_inquiry import (
    BalanceInquiryDependencies,
    build_balance_inquiry_graph,
)
from agent.workflows.period_amount_summary import (
    PeriodAmountSummaryDependencies,
    build_period_amount_summary_graph,
)
from agent.workflows.transaction_history import (
    TransactionHistoryDependencies,
    build_transaction_history_graph,
)

GLOBAL_WORKFLOW_ID = "wf_global_agent_entry"


@dataclass(frozen=True, slots=True)
class ContractAgentDependencies:
    """서비스용 상위 Graph가 모든 업무 Workflow에 공유하는 의존성."""

    tool_registry: ContractToolRegistry
    webhook_client: BackendWebhookClient
    interaction_runtime: InteractionPauseRuntime
    webhook_builder: InteractionWebhookBuilder


def build_contract_agent_graph(
    dependencies: ContractAgentDependencies,
    *,
    checkpointer: Any = None,
) -> ExecutionGraph:
    """전역 검사와 Workflow 분류 뒤 계약 기반 하위 Graph를 실행한다."""

    workflow_graphs = _build_read_workflow_graphs(dependencies)

    async def run_global_guardrail(state: AgentState) -> dict[str, Any]:
        update = global_guardrail_node(dict(state))
        blocked = update.get("status") == "blocked"
        return {
            **update,
            "workflow_id": GLOBAL_WORKFLOW_ID,
            "current_step_id": "run_global_guardrail",
            "route_key": "blocked" if blocked else "allowed",
        }

    async def match_contract_workflow(state: AgentState) -> dict[str, Any]:
        workflow_id = await asyncio.to_thread(
            match_workflow,
            str(state.get("user_input") or ""),
        )
        if workflow_id not in workflow_graphs:
            return {
                "workflow_id": GLOBAL_WORKFLOW_ID,
                "current_step_id": "match_workflow",
                "route_key": "no_match",
                "status": "no_match",
            }
        return {
            "workflow_id": workflow_id,
            "current_step_id": "match_workflow",
            "route_key": "matched",
            "status": "matched",
        }

    async def emit_global_blocked(
        state: AgentState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        content = str(
            state.get("final_response")
            or "요청하신 내용은 안전 정책상 처리할 수 없습니다."
        )
        await _publish_notice(
            dependencies,
            config,
            step_id="emit_global_blocked",
            ui_contract_id="UI-GLOBAL-BLOCKED",
            ui_type="blocked_message",
            content=content,
        )
        return _terminal_update("emit_global_blocked", status="blocked")

    async def emit_no_matching_workflow(
        state: AgentState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        del state
        content = (
            "아직 처리할 수 없는 요청입니다. 계좌, 잔액, 거래내역과 "
            "기간 합계 조회를 요청해 주세요."
        )
        await _publish_notice(
            dependencies,
            config,
            step_id="emit_no_matching_workflow",
            ui_contract_id="UI-NO-MATCH",
            ui_type="message",
            content=content,
        )
        return _terminal_update("emit_no_matching_workflow", status="no_match")

    graph = StateGraph(AgentState)
    graph.add_node("run_global_guardrail", run_global_guardrail)
    graph.add_node("match_workflow", match_contract_workflow)
    graph.add_node("emit_global_blocked", emit_global_blocked)
    graph.add_node("emit_no_matching_workflow", emit_no_matching_workflow)
    for workflow_id, workflow_graph in workflow_graphs.items():
        graph.add_node(workflow_id, workflow_graph)

    graph.set_entry_point("run_global_guardrail")
    graph.add_conditional_edges(
        "run_global_guardrail",
        _route_key,
        {
            "allowed": "match_workflow",
            "blocked": "emit_global_blocked",
        },
    )
    graph.add_conditional_edges(
        "match_workflow",
        _matched_workflow_route,
        {
            **{workflow_id: workflow_id for workflow_id in workflow_graphs},
            "no_match": "emit_no_matching_workflow",
        },
    )
    graph.add_edge("emit_global_blocked", END)
    graph.add_edge("emit_no_matching_workflow", END)
    for workflow_id in workflow_graphs:
        graph.add_edge(workflow_id, END)
    return cast(ExecutionGraph, graph.compile(checkpointer=checkpointer))


def _build_read_workflow_graphs(
    dependencies: ContractAgentDependencies,
) -> dict[str, Any]:
    common = {
        "tool_registry": dependencies.tool_registry,
        "webhook_client": dependencies.webhook_client,
        "webhook_builder": dependencies.webhook_builder,
    }
    return {
        "wf_account_list": cast(
            ExecutionGraph,
            build_account_list_graph(AccountListDependencies(**common)),
        ),
        "wf_balance_inquiry": cast(
            ExecutionGraph,
            build_balance_inquiry_graph(
                BalanceInquiryDependencies(
                    **common,
                    interaction_runtime=dependencies.interaction_runtime,
                )
            ),
        ),
        "wf_transaction_history": cast(
            ExecutionGraph,
            build_transaction_history_graph(
                TransactionHistoryDependencies(
                    **common,
                    interaction_runtime=dependencies.interaction_runtime,
                )
            ),
        ),
        "wf_period_amount_summary": cast(
            ExecutionGraph,
            build_period_amount_summary_graph(
                PeriodAmountSummaryDependencies(
                    **common,
                    interaction_runtime=dependencies.interaction_runtime,
                )
            ),
        ),
    }


def _route_key(state: AgentState) -> str:
    return str(state.get("route_key") or "blocked")


def _matched_workflow_route(state: AgentState) -> str:
    workflow_id = str(state.get("workflow_id") or "")
    return workflow_id if workflow_id != GLOBAL_WORKFLOW_ID else "no_match"


def _config_context(config: RunnableConfig, key: str) -> str:
    configurable = config.get("configurable") or {}
    value = configurable.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"LangGraph 실행 Context가 없습니다: {key}")
    return value


async def _publish_notice(
    dependencies: ContractAgentDependencies,
    config: RunnableConfig,
    *,
    step_id: str,
    ui_contract_id: str,
    ui_type: str,
    content: str,
) -> None:
    event = AgentWebhookRequest(
        chat_session_id=_config_context(config, "chat_session_id"),
        event_type="component",
        content=content,
        metadata={
            "workflow_id": GLOBAL_WORKFLOW_ID,
            "step_id": step_id,
            "ui_contract_id": ui_contract_id,
            "ui": {"type": ui_type, "payload": {"message": content}},
        },
    )
    await dependencies.webhook_client.publish(
        event,
        execution_context_id=_config_context(config, "execution_context_id"),
        request_id=_config_context(config, "request_id"),
    )


def _terminal_update(step_id: str, *, status: str) -> dict[str, Any]:
    return {
        "workflow_id": GLOBAL_WORKFLOW_ID,
        "current_step_id": step_id,
        "route_key": "completed",
        "status": status,
    }
