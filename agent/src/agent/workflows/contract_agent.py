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
from agent.workflow_routing import route_workflow, workflow_name
from agent.workflows.account_list import (
    AccountListDependencies,
    build_account_list_graph,
)
from agent.workflows.balance_inquiry import (
    BalanceInquiryDependencies,
    build_balance_inquiry_graph,
)
from agent.workflows.external_transfer import (
    ExternalTransferDependencies,
    build_external_transfer_graph,
)
from agent.workflows.internal_transfer import (
    InternalTransferDependencies,
    build_internal_transfer_graph,
)
from agent.workflows.period_amount_summary import (
    PeriodAmountSummaryDependencies,
    build_period_amount_summary_graph,
)
from agent.workflows.set_account_alias import (
    AccountAliasChangeDependencies,
    build_set_account_alias_graph,
)
from agent.workflows.set_default_account import (
    DefaultAccountChangeDependencies,
    build_set_default_account_graph,
)
from agent.workflows.transaction_history import (
    TransactionHistoryDependencies,
    build_transaction_history_graph,
)
from agent.workflows.workflow_support import config_context as _config_context
from agent.workflows.workflow_support import new_input_request_id as _new_input_request_id
from agent.workflows.workflow_support import publish_event
from agent.workflows.workflow_support import resume_data_update as _resume_update
from agent.workflows.workflow_support import resume_state_data as _resume_data
from agent.workflows.workflow_support import state_data as _state_data

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

    workflow_graphs = _build_workflow_graphs(dependencies)

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
        # 분류기·검증기 분리 파이프라인. resolved면 워크플로우로 진입하고,
        # ambiguous면 라우팅 단계 사용자 확인(clarification)으로, failed·no_match는
        # 안전 종료한다.
        resolution = await asyncio.to_thread(
            route_workflow,
            str(state.get("user_input") or ""),
        )
        if resolution.status == "resolved" and resolution.workflow_id in workflow_graphs:
            return {
                "workflow_id": resolution.workflow_id,
                "current_step_id": "match_workflow",
                "route_key": "matched",
                "status": "matched",
            }
        candidates = [c for c in resolution.candidates if c in workflow_graphs]
        if resolution.status == "ambiguous" and len(candidates) >= 2:
            return {
                "workflow_id": GLOBAL_WORKFLOW_ID,
                "current_step_id": "match_workflow",
                "route_key": "clarify",
                "status": "running",
                "data": {
                    "input_request_id": _new_input_request_id(),
                    "workflow_clarification_candidates": candidates,
                },
            }
        # failed·no_match·후보 부족 ambiguous → 안전 종료(지원 없음 안내).
        return {
            "workflow_id": GLOBAL_WORKFLOW_ID,
            "current_step_id": "match_workflow",
            "route_key": "no_match",
            "status": "no_match",
        }

    async def request_workflow_clarification(
        state: AgentState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        data = _state_data(state)
        input_request_id = data.get("input_request_id")
        candidates = [c for c in (data.get("workflow_clarification_candidates") or []) if c in workflow_graphs]
        event = dependencies.webhook_builder.need_input(
            chat_session_id=_config_context(config, "chat_session_id"),
            workflow_id=GLOBAL_WORKFLOW_ID,
            step_id="request_workflow_clarification",
            input_request_id=input_request_id,
            ui_contract_id="UI-WORKFLOW-CLARIFICATION",
            ui_type="option_select",
            content="요청하신 업무를 확인해 주세요.",
            payload={
                "title": "요청하신 업무를 확인해 주세요.",
                "options": [{"value": wid, "label": workflow_name(wid)} for wid in candidates],
                "actions": ["select", "cancel"],
            },
        )
        resumed = _resume_data(state, dependencies.interaction_runtime, event)
        outcome = resumed.get("workflow_clarification_outcome")
        selected = resumed.get("selected_workflow_id")
        if outcome == "selected" and selected in workflow_graphs:
            route_key = cast(str, selected)
            workflow_id = cast(str, selected)
            status = "running"
        elif outcome == "cancelled":
            route_key = "cancelled"
            workflow_id = GLOBAL_WORKFLOW_ID
            status = "completed"
        else:
            route_key = "no_match"
            workflow_id = GLOBAL_WORKFLOW_ID
            status = "no_match"
        return {
            "workflow_id": workflow_id,
            "current_step_id": "request_workflow_clarification",
            "route_key": route_key,
            "status": status,
            "data": _resume_update(resumed, input_request_id=None),
        }

    async def emit_global_blocked(
        state: AgentState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        content = str(state.get("final_response") or "요청하신 내용은 안전 정책상 처리할 수 없습니다.")
        event = dependencies.webhook_builder.blocked(
            chat_session_id=_config_context(config, "chat_session_id"),
            workflow_id=GLOBAL_WORKFLOW_ID,
            step_id="emit_global_blocked",
            ui_contract_id="UI-GLOBAL-BLOCKED",
            content=content,
            payload={"message": content},
        )
        await dependencies.webhook_client.publish(
            event,
            execution_context_id=_config_context(config, "execution_context_id"),
            request_id=_config_context(config, "request_id"),
        )
        return _terminal_update("emit_global_blocked", status="blocked")

    async def emit_no_matching_workflow(
        state: AgentState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        del state
        content = "아직 처리할 수 없는 요청입니다. 계좌, 잔액, 거래내역과 기간 합계 조회를 요청해 주세요."
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
    graph.add_node("request_workflow_clarification", request_workflow_clarification)
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
            "clarify": "request_workflow_clarification",
            "no_match": "emit_no_matching_workflow",
        },
    )
    # 사용자가 후보 중 하나를 선택하면 해당 워크플로우로, 취소·오류면 안전 종료.
    graph.add_conditional_edges(
        "request_workflow_clarification",
        _clarified_workflow_route,
        {
            **{workflow_id: workflow_id for workflow_id in workflow_graphs},
            "cancelled": "emit_no_matching_workflow",
            "no_match": "emit_no_matching_workflow",
        },
    )
    graph.add_edge("emit_global_blocked", END)
    graph.add_edge("emit_no_matching_workflow", END)
    for workflow_id in workflow_graphs:
        graph.add_edge(workflow_id, END)
    return cast(ExecutionGraph, graph.compile(checkpointer=checkpointer))


def _build_workflow_graphs(
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
        "wf_set_default_account": cast(
            ExecutionGraph,
            build_set_default_account_graph(
                DefaultAccountChangeDependencies(
                    **common,
                    interaction_runtime=dependencies.interaction_runtime,
                )
            ),
        ),
        "wf_set_account_alias": cast(
            ExecutionGraph,
            build_set_account_alias_graph(
                AccountAliasChangeDependencies(
                    **common,
                    interaction_runtime=dependencies.interaction_runtime,
                )
            ),
        ),
        "wf_internal_transfer": cast(
            ExecutionGraph,
            build_internal_transfer_graph(
                InternalTransferDependencies(
                    **common,
                    interaction_runtime=dependencies.interaction_runtime,
                )
            ),
        ),
        "wf_external_transfer": cast(
            ExecutionGraph,
            build_external_transfer_graph(
                ExternalTransferDependencies(
                    **common,
                    interaction_runtime=dependencies.interaction_runtime,
                )
            ),
        ),
    }


def _route_key(state: AgentState) -> str:
    return str(state.get("route_key") or "blocked")


def _matched_workflow_route(state: AgentState) -> str:
    if str(state.get("route_key") or "") == "clarify":
        return "clarify"
    workflow_id = str(state.get("workflow_id") or "")
    return workflow_id if workflow_id != GLOBAL_WORKFLOW_ID else "no_match"


def _clarified_workflow_route(state: AgentState) -> str:
    route_key = str(state.get("route_key") or "")
    if route_key in ("cancelled", "no_match"):
        return route_key
    workflow_id = str(state.get("workflow_id") or "")
    return workflow_id if workflow_id != GLOBAL_WORKFLOW_ID else "no_match"


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
    await publish_event(dependencies, event, config)


def _terminal_update(step_id: str, *, status: str) -> dict[str, Any]:
    return {
        "workflow_id": GLOBAL_WORKFLOW_ID,
        "current_step_id": step_id,
        "route_key": "completed",
        "status": status,
    }
