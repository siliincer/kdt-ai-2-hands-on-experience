"""관리시트 계약 기반 잔액 조회 기준 Workflow."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, StateGraph

from agent.clients.backend import BackendWebhookClient
from agent.clients.backend.client import AgentToolIntegrationError
from agent.runtime import InteractionPauseRuntime, InteractionWebhookBuilder
from agent.state import AgentState
from agent.tools.contract_registry import (
    ContractToolInputError,
    ContractToolRegistry,
)
from agent.workflows.query_slot_extraction import (
    AccountSlotExtractor,
    extract_balance_slots_by_rule,
    extract_balance_slots_llm_first,
)
from agent.workflows.workflow_support import build_tool_error_update
from agent.workflows.workflow_support import config_context as _config_context
from agent.workflows.workflow_support import masked_account_options as _account_options
from agent.workflows.workflow_support import (
    new_input_request_id as _default_input_request_id,
)
from agent.workflows.workflow_support import publish_event as _publish
from agent.workflows.workflow_support import resume_data_update as _resume_update
from agent.workflows.workflow_support import resume_state_data as _resume_data
from agent.workflows.workflow_support import route_key as _route_key
from agent.workflows.workflow_support import state_data as _data
from agent.workflows.workflow_support import step_request_id as _default_tool_request_id
from agent.workflows.workflow_support import terminal_update as _terminal_update
from agent.workflows.workflow_support import tool_call as _tool_call

WORKFLOW_ID = "wf_balance_inquiry"
_tool_error_update = build_tool_error_update("잔액 조회를 완료하지 못했습니다. 잠시 후 다시 시도해 주세요.")


def extract_balance_slots_from_text(message: str) -> Mapping[str, Any]:
    """테스트와 장애 폴백용 결정적 잔액조회 Slot 추출."""

    return extract_balance_slots_by_rule(message)


@dataclass(frozen=True, slots=True)
class BalanceInquiryDependencies:
    """잔액 Workflow가 공유 기반에서 주입받는 외부 의존성."""

    tool_registry: ContractToolRegistry
    webhook_client: BackendWebhookClient
    interaction_runtime: InteractionPauseRuntime
    webhook_builder: InteractionWebhookBuilder
    input_request_id_factory: Callable[[], str] = field(default=_default_input_request_id)
    tool_request_id_factory: Callable[[str, str], str] = field(default=_default_tool_request_id)
    slot_extractor: AccountSlotExtractor = field(default=extract_balance_slots_llm_first)


def build_balance_inquiry_graph(
    dependencies: BalanceInquiryDependencies,
    *,
    checkpointer: Any = None,
) -> Any:
    """잔액 조회 Step과 Route를 관리시트 순서대로 컴파일한다."""

    async def extract_balance_slots(
        state: AgentState,
    ) -> dict[str, Any]:
        extracted = await dependencies.slot_extractor(str(state.get("user_input") or ""))
        return {
            "workflow_id": WORKFLOW_ID,
            "current_step_id": "extract_balance_slots",
            "route_key": "extracted",
            "data": {
                "account_hint": extracted.get("account_hint"),
                "all_accounts_requested": bool(extracted.get("all_accounts_requested", False)),
            },
        }

    async def resolve_balance_accounts(
        state: AgentState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        data = _data(state)
        try:
            result = await dependencies.tool_registry.invoke_by_tool(
                "fetch_accounts",
                _tool_call(
                    config,
                    dependencies=dependencies,
                    step_id="resolve_balance_accounts",
                    arguments={
                        "account_hint": data.get("account_hint"),
                        "account_capability": "inquiry",
                        "resolve_selection": True,
                        "all_accounts_requested": bool(data.get("all_accounts_requested", False)),
                    },
                ),
            )
        except (AgentToolIntegrationError, ContractToolInputError) as error:
            return _tool_error_update("resolve_balance_accounts", error)

        outcome = result.get("account_resolution_outcome")
        if outcome not in {"resolved", "selection_required", "no_accounts"}:
            return _tool_error_update(
                "resolve_balance_accounts",
                ValueError("계좌 확인 결과가 올바르지 않습니다."),
            )
        update: dict[str, Any] = {
            "account_resolution_outcome": outcome,
            "accounts": list(result.get("accounts") or []),
            "account_ids": list(result.get("account_ids") or []),
        }
        if outcome == "selection_required":
            update["input_request_id"] = dependencies.input_request_id_factory()
        return {
            "current_step_id": "resolve_balance_accounts",
            "route_key": outcome,
            "data": update,
        }

    async def request_balance_account_selection(
        state: AgentState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        data = _data(state)
        input_request_id = data.get("input_request_id")
        if not isinstance(input_request_id, str) or not input_request_id:
            return _tool_error_update(
                "request_balance_account_selection",
                ValueError("입력 요청 ID가 없습니다."),
            )
        event = dependencies.webhook_builder.need_input(
            chat_session_id=_config_context(config, "chat_session_id"),
            workflow_id=WORKFLOW_ID,
            step_id="request_balance_account_selection",
            input_request_id=input_request_id,
            ui_contract_id="UI-BALANCE-ACCOUNT-SELECTION",
            ui_type="account_card_list",
            content="잔액을 확인할 계좌를 선택해 주세요.",
            payload={
                "title": "계좌를 선택해 주세요.",
                "accounts": _account_options(data.get("accounts")),
                "actions": ["select", "cancel"],
                "multiple": True,
            },
        )
        resumed_data = _resume_data(state, dependencies.interaction_runtime, event)
        outcome = resumed_data.get("account_selection_outcome")
        route_key = outcome if outcome in {"selected", "cancelled"} else "error"
        return {
            "current_step_id": "request_balance_account_selection",
            "route_key": route_key,
            "status": "completed" if route_key == "cancelled" else "running",
            "data": _resume_update(resumed_data, input_request_id=None),
        }

    async def query_balances(
        state: AgentState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        try:
            result = await dependencies.tool_registry.invoke_by_tool(
                "query_balances",
                _tool_call(
                    config,
                    dependencies=dependencies,
                    step_id="query_balances",
                    arguments={"account_ids": list(_data(state).get("account_ids") or [])},
                ),
            )
        except (AgentToolIntegrationError, ContractToolInputError) as error:
            return _tool_error_update("query_balances", error)
        return {
            "current_step_id": "query_balances",
            "route_key": "succeeded",
            "data": {"balance_results": list(result.get("balance_results") or [])},
        }

    async def emit_balance_accounts_empty(
        state: AgentState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        event = dependencies.webhook_builder.component(
            chat_session_id=_config_context(config, "chat_session_id"),
            workflow_id=WORKFLOW_ID,
            step_id="emit_balance_accounts_empty",
            ui_contract_id="UI-BALANCE-ACCOUNT-SELECTION",
            ui_type="account_card_list",
            content="조회 가능한 계좌가 없습니다.",
            payload={
                "title": "조회 가능한 계좌가 없습니다.",
                "accounts": [],
                "actions": [],
                "multiple": True,
            },
        )
        await _publish(dependencies, event, config)
        return _terminal_update("emit_balance_accounts_empty")

    async def emit_balance_result(
        state: AgentState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        event = dependencies.webhook_builder.component(
            chat_session_id=_config_context(config, "chat_session_id"),
            workflow_id=WORKFLOW_ID,
            step_id="emit_balance_result",
            ui_contract_id="UI-BALANCE-RESULT",
            ui_type="balance_result",
            content="계좌 잔액을 확인했습니다.",
            payload={"accounts": _balance_result_options(_data(state).get("balance_results"))},
        )
        await _publish(dependencies, event, config)
        return _terminal_update("emit_balance_result")

    async def emit_balance_error(
        state: AgentState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        message = str(
            _data(state).get("safe_error_message") or "잔액 조회를 완료하지 못했습니다. 잠시 후 다시 시도해 주세요."
        )
        event = dependencies.webhook_builder.error(
            chat_session_id=_config_context(config, "chat_session_id"),
            workflow_id=WORKFLOW_ID,
            step_id="emit_balance_error",
            ui_contract_id="UI-COMMON-ERROR",
            content=message,
            payload={"message": message},
        )
        await _publish(dependencies, event, config)
        return _terminal_update("emit_balance_error", status="workflow_failed")

    graph = StateGraph(AgentState)
    graph.add_node("extract_balance_slots", extract_balance_slots)
    graph.add_node("resolve_balance_accounts", resolve_balance_accounts)
    graph.add_node(
        "request_balance_account_selection",
        request_balance_account_selection,
    )
    graph.add_node("query_balances", query_balances)
    graph.add_node("emit_balance_accounts_empty", emit_balance_accounts_empty)
    graph.add_node("emit_balance_result", emit_balance_result)
    graph.add_node("emit_balance_error", emit_balance_error)
    graph.set_entry_point("extract_balance_slots")
    graph.add_edge("extract_balance_slots", "resolve_balance_accounts")
    graph.add_conditional_edges(
        "resolve_balance_accounts",
        _route_key,
        {
            "resolved": "query_balances",
            "selection_required": "request_balance_account_selection",
            "no_accounts": "emit_balance_accounts_empty",
            "error": "emit_balance_error",
        },
    )
    graph.add_conditional_edges(
        "request_balance_account_selection",
        _route_key,
        {
            "selected": "query_balances",
            "cancelled": END,
            "error": "emit_balance_error",
        },
    )
    graph.add_conditional_edges(
        "query_balances",
        _route_key,
        {"succeeded": "emit_balance_result", "error": "emit_balance_error"},
    )
    graph.add_edge("emit_balance_accounts_empty", END)
    graph.add_edge("emit_balance_result", END)
    graph.add_edge("emit_balance_error", END)
    return graph.compile(checkpointer=checkpointer)


def _balance_result_options(raw_results: Any) -> list[dict[str, Any]]:
    results = raw_results if isinstance(raw_results, list) else []
    return [
        {
            "account_id": result.get("account_id"),
            "account_alias": result.get("account_alias"),
            "masked_account_number": result.get("masked_account_number"),
            "balance": result.get("balance"),
            "available_amount": result.get("available_balance"),
            "currency": result.get("currency"),
        }
        for result in results
        if isinstance(result, Mapping)
    ]
