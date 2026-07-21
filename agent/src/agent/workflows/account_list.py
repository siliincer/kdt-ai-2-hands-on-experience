"""관리시트 계약 기반 전체 계좌 목록 조회 Workflow."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, StateGraph

from agent.clients.backend import BackendWebhookClient
from agent.clients.backend.client import AgentToolIntegrationError
from agent.runtime import InteractionWebhookBuilder
from agent.state import AgentState
from agent.tools.contract_registry import (
    ContractToolInputError,
    ContractToolRegistry,
)
from agent.workflows.query_slot_extraction import (
    AccountSlotExtractor,
    extract_account_list_slots_by_rule,
    extract_account_list_slots_llm_first,
)
from agent.workflows.workflow_support import build_tool_error_update
from agent.workflows.workflow_support import config_context as _config_context
from agent.workflows.workflow_support import publish_event as _publish
from agent.workflows.workflow_support import route_key as _route_key
from agent.workflows.workflow_support import state_data as _data
from agent.workflows.workflow_support import terminal_update as _terminal_update
from agent.workflows.workflow_support import tool_call as _tool_call

WORKFLOW_ID = "wf_account_list"
_tool_error_update = build_tool_error_update(
    "계좌 목록을 확인하지 못했습니다. 잠시 후 다시 시도해 주세요."
)


def _default_tool_request_id(parent_request_id: str, step_id: str) -> str:
    return f"{parent_request_id}:{step_id}"


def extract_account_list_slots_from_text(message: str) -> Mapping[str, Any]:
    """테스트와 장애 폴백용 결정적 계좌 힌트 추출."""

    return extract_account_list_slots_by_rule(message)


@dataclass(frozen=True, slots=True)
class AccountListDependencies:
    """계좌 목록 Workflow가 공통 기반에서 주입받는 의존성."""

    tool_registry: ContractToolRegistry
    webhook_client: BackendWebhookClient
    webhook_builder: InteractionWebhookBuilder
    tool_request_id_factory: Callable[[str, str], str] = field(
        default=_default_tool_request_id
    )
    slot_extractor: AccountSlotExtractor = field(
        default=extract_account_list_slots_llm_first
    )


def build_account_list_graph(
    dependencies: AccountListDependencies,
    *,
    checkpointer: Any = None,
) -> Any:
    """계좌 목록 조회 Step과 Route를 관리시트 순서대로 컴파일한다."""

    async def extract_account_list_slots(
        state: AgentState,
    ) -> dict[str, Any]:
        extracted = await dependencies.slot_extractor(
            str(state.get("user_input") or "")
        )
        return {
            "workflow_id": WORKFLOW_ID,
            "current_step_id": "extract_account_list_slots",
            "route_key": "extracted",
            "data": {"account_hint": extracted.get("account_hint")},
        }

    async def fetch_account_list(
        state: AgentState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        try:
            result = await dependencies.tool_registry.invoke_by_tool(
                "fetch_accounts",
                _tool_call(
                    config,
                    dependencies=dependencies,
                    step_id="fetch_account_list",
                    arguments={
                        "account_hint": _data(state).get("account_hint"),
                        "limit": 20,
                    },
                ),
            )
        except (AgentToolIntegrationError, ContractToolInputError) as error:
            return _tool_error_update("fetch_account_list", error)
        return {
            "current_step_id": "fetch_account_list",
            "route_key": "succeeded",
            "data": {
                "account_results": _account_options(result.get("accounts")),
            },
        }

    async def emit_account_list_result(
        state: AgentState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        event = dependencies.webhook_builder.component(
            chat_session_id=_config_context(config, "chat_session_id"),
            workflow_id=WORKFLOW_ID,
            step_id="emit_account_list_result",
            ui_contract_id="UI-ACCOUNT-LIST-RESULT",
            ui_type="account_list",
            content="보유 계좌를 확인했습니다.",
            payload={"accounts": list(_data(state).get("account_results") or [])},
        )
        await _publish(dependencies, event, config)
        return _terminal_update("emit_account_list_result")

    async def emit_account_list_error(
        state: AgentState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        message = str(
            _data(state).get("safe_error_message")
            or "계좌 목록을 확인하지 못했습니다. 잠시 후 다시 시도해 주세요."
        )
        event = dependencies.webhook_builder.error(
            chat_session_id=_config_context(config, "chat_session_id"),
            workflow_id=WORKFLOW_ID,
            step_id="emit_account_list_error",
            ui_contract_id="UI-COMMON-ERROR",
            content=message,
            payload={"message": message},
        )
        await _publish(dependencies, event, config)
        return _terminal_update(
            "emit_account_list_error",
            status="workflow_failed",
        )

    graph = StateGraph(AgentState)
    graph.add_node("extract_account_list_slots", extract_account_list_slots)
    graph.add_node("fetch_account_list", fetch_account_list)
    graph.add_node("emit_account_list_result", emit_account_list_result)
    graph.add_node("emit_account_list_error", emit_account_list_error)
    graph.set_entry_point("extract_account_list_slots")
    graph.add_edge("extract_account_list_slots", "fetch_account_list")
    graph.add_conditional_edges(
        "fetch_account_list",
        _route_key,
        {
            "succeeded": "emit_account_list_result",
            "error": "emit_account_list_error",
        },
    )
    graph.add_edge("emit_account_list_result", END)
    graph.add_edge("emit_account_list_error", END)
    return graph.compile(checkpointer=checkpointer)


def _account_options(raw_accounts: Any) -> list[dict[str, Any]]:
    accounts = raw_accounts if isinstance(raw_accounts, list) else []
    fields = (
        "account_id",
        "bank_name",
        "account_alias",
        "account_type",
        "masked_account_number",
        "currency",
        "is_default",
        "status",
    )
    return [
        {field: account.get(field) for field in fields}
        for account in accounts
        if isinstance(account, Mapping)
    ]
