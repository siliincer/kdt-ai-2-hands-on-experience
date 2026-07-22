"""관리시트 계약 기반 거래내역 조회 Workflow."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
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
from agent.workflows.inquiry_support import (
    default_recent_month,
    period_was_mentioned,
    reference_date,
)
from agent.workflows.query_slot_extraction import (
    DatedSlotExtractor,
    extract_transaction_slots_by_rule,
    extract_transaction_slots_llm_first,
)
from agent.workflows.workflow_support import build_tool_error_update
from agent.workflows.workflow_support import config_context as _config_context
from agent.workflows.workflow_support import masked_account_options as account_options
from agent.workflows.workflow_support import (
    new_input_request_id as _default_input_request_id,
)
from agent.workflows.workflow_support import publish_event as _publish
from agent.workflows.workflow_support import (
    required_input_request_id as _required_input_request_id,
)
from agent.workflows.workflow_support import resume_data_update as _resume_update
from agent.workflows.workflow_support import resume_state_data as _resume_data
from agent.workflows.workflow_support import route_key as _route_key
from agent.workflows.workflow_support import state_data as _data
from agent.workflows.workflow_support import step_request_id as _default_tool_request_id
from agent.workflows.workflow_support import terminal_update as _terminal_update
from agent.workflows.workflow_support import tool_call as _tool_call
from agent.workflows.workflow_support import valid_iso_date as _valid_date

WORKFLOW_ID = "wf_transaction_history"
_tool_error_update = build_tool_error_update(
    "거래내역을 확인하지 못했습니다. 잠시 후 다시 시도해 주세요."
)


def _default_now() -> datetime:
    return datetime.now(timezone.utc)


def extract_transaction_slots_from_text(
    message: str,
    requested_date: date,
) -> Mapping[str, Any]:
    """테스트와 장애 폴백용 결정적 거래내역 Slot 추출."""

    return extract_transaction_slots_by_rule(message, requested_date)


@dataclass(frozen=True, slots=True)
class TransactionHistoryDependencies:
    """거래내역 Workflow가 공통 기반에서 주입받는 의존성."""

    tool_registry: ContractToolRegistry
    webhook_client: BackendWebhookClient
    interaction_runtime: InteractionPauseRuntime
    webhook_builder: InteractionWebhookBuilder
    input_request_id_factory: Callable[[], str] = field(
        default=_default_input_request_id
    )
    tool_request_id_factory: Callable[[str, str], str] = field(
        default=_default_tool_request_id
    )
    now_factory: Callable[[], datetime] = field(default=_default_now)
    slot_extractor: DatedSlotExtractor = field(
        default=extract_transaction_slots_llm_first
    )


def build_transaction_history_graph(
    dependencies: TransactionHistoryDependencies,
    *,
    checkpointer: Any = None,
) -> Any:
    """거래내역 조회 Step과 Route를 관리시트 순서대로 컴파일한다."""

    async def extract_transaction_slots(
        state: AgentState,
    ) -> dict[str, Any]:
        data = _data(state)
        extracted = await dependencies.slot_extractor(
            str(state.get("user_input") or ""),
            reference_date(data, fallback=dependencies.now_factory()),
        )
        return {
            "workflow_id": WORKFLOW_ID,
            "current_step_id": "extract_transaction_slots",
            "route_key": "extracted",
            "data": {
                "account_hint": extracted.get("account_hint"),
                "all_accounts_requested": bool(
                    extracted.get("all_accounts_requested", False)
                ),
                "start_date": extracted.get("start_date"),
                "end_date": extracted.get("end_date"),
                "keyword": extracted.get("keyword"),
                "transaction_type": extracted.get("transaction_type"),
            },
        }

    async def resolve_transaction_accounts(
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
                    step_id="resolve_transaction_accounts",
                    arguments={
                        "account_hint": data.get("account_hint"),
                        "account_capability": "inquiry",
                        "resolve_selection": True,
                        "all_accounts_requested": bool(
                            data.get("all_accounts_requested", False)
                        ),
                    },
                ),
            )
        except (AgentToolIntegrationError, ContractToolInputError) as error:
            return _tool_error_update("resolve_transaction_accounts", error)

        outcome = result.get("account_resolution_outcome")
        if outcome not in {"resolved", "selection_required", "no_accounts"}:
            return _tool_error_update(
                "resolve_transaction_accounts",
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
            "current_step_id": "resolve_transaction_accounts",
            "route_key": outcome,
            "data": update,
        }

    async def request_transaction_account_selection(
        state: AgentState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        data = _data(state)
        input_request_id = _required_input_request_id(data)
        event = dependencies.webhook_builder.need_input(
            chat_session_id=_config_context(config, "chat_session_id"),
            workflow_id=WORKFLOW_ID,
            step_id="request_transaction_account_selection",
            input_request_id=input_request_id,
            ui_contract_id="UI-TRANSACTION-ACCOUNT-SELECTION",
            ui_type="account_card_list",
            content="거래내역을 확인할 계좌를 선택해 주세요.",
            payload={
                "title": "계좌를 선택해 주세요.",
                "accounts": account_options(data.get("accounts")),
                "actions": ["select", "cancel"],
            },
        )
        resumed_data = _resume_data(state, dependencies.interaction_runtime, event)
        outcome = resumed_data.get("account_selection_outcome")
        route_key = outcome if outcome in {"selected", "cancelled"} else "error"
        return {
            "current_step_id": "request_transaction_account_selection",
            "route_key": route_key,
            "status": "completed" if route_key == "cancelled" else "running",
            "data": _resume_update(resumed_data, input_request_id=None),
        }

    async def emit_transaction_accounts_empty(
        state: AgentState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        event = dependencies.webhook_builder.component(
            chat_session_id=_config_context(config, "chat_session_id"),
            workflow_id=WORKFLOW_ID,
            step_id="emit_transaction_accounts_empty",
            ui_contract_id="UI-TRANSACTION-ACCOUNT-SELECTION",
            ui_type="account_card_list",
            content="조회 가능한 계좌가 없습니다.",
            payload={
                "title": "조회 가능한 계좌가 없습니다.",
                "accounts": [],
                "actions": [],
            },
        )
        await _publish(dependencies, event, config)
        return _terminal_update("emit_transaction_accounts_empty")

    async def check_transaction_period(
        state: AgentState,
    ) -> dict[str, Any]:
        data = _data(state)
        start_date = _valid_date(data.get("start_date"))
        end_date = _valid_date(data.get("end_date"))
        message = str(state.get("user_input") or "")
        if start_date is not None and end_date is not None:
            return {
                "current_step_id": "check_transaction_period",
                "route_key": "normalized",
                "data": {
                    "start_date": start_date,
                    "end_date": end_date,
                },
            }
        if period_was_mentioned(message):
            return {
                "current_step_id": "check_transaction_period",
                "route_key": "selection_required",
                "data": {
                    "input_request_id": dependencies.input_request_id_factory(),
                },
            }
        default_start, default_end = default_recent_month(
            reference_date(data, fallback=dependencies.now_factory())
        )
        return {
            "current_step_id": "check_transaction_period",
            "route_key": "normalized",
            "data": {
                "start_date": default_start,
                "end_date": default_end,
            },
        }

    async def request_period_selection(
        state: AgentState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        input_request_id = _required_input_request_id(_data(state))
        event = dependencies.webhook_builder.need_input(
            chat_session_id=_config_context(config, "chat_session_id"),
            workflow_id=WORKFLOW_ID,
            step_id="request_period_selection",
            input_request_id=input_request_id,
            ui_contract_id="UI-PERIOD-SELECTION",
            ui_type="period_input",
            content="조회 기간을 선택해 주세요.",
            payload={
                "title": "조회 기간을 선택해 주세요.",
                "presets": ["this_month", "last_month", "recent_1_month"],
                "manual_range": True,
                "actions": ["select", "cancel"],
            },
        )
        resumed_data = _resume_data(state, dependencies.interaction_runtime, event)
        outcome = resumed_data.get("period_selection_outcome")
        route_key = outcome if outcome in {"selected", "cancelled"} else "error"
        return {
            "current_step_id": "request_period_selection",
            "route_key": route_key,
            "status": "completed" if route_key == "cancelled" else "running",
            "data": _resume_update(resumed_data, input_request_id=None),
        }

    async def query_transactions(
        state: AgentState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        data = _data(state)
        try:
            result = await dependencies.tool_registry.invoke_by_tool(
                "query_transactions",
                _tool_call(
                    config,
                    dependencies=dependencies,
                    step_id="query_transactions",
                    arguments={
                        "account_ids": list(data.get("account_ids") or []),
                        "start_date": data.get("start_date"),
                        "end_date": data.get("end_date"),
                        "keyword": data.get("keyword"),
                        "transaction_type": data.get("transaction_type"),
                        "limit": 10,
                    },
                ),
            )
        except (AgentToolIntegrationError, ContractToolInputError) as error:
            return _tool_error_update("query_transactions", error)
        return {
            "current_step_id": "query_transactions",
            "route_key": "succeeded",
            "data": {
                "transaction_results": list(result.get("transaction_results") or []),
                "transaction_query_id": result.get("transaction_query_id"),
                "next_cursor": result.get("next_cursor"),
            },
        }

    async def emit_transaction_result(
        state: AgentState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        data = _data(state)
        event = dependencies.webhook_builder.component(
            chat_session_id=_config_context(config, "chat_session_id"),
            workflow_id=WORKFLOW_ID,
            step_id="emit_transaction_result",
            ui_contract_id="UI-TRANSACTION-LIST",
            ui_type="transaction_list",
            content="거래내역을 확인했습니다.",
            payload={
                "account_ids": list(data.get("account_ids") or []),
                "period": {
                    "start_date": data.get("start_date"),
                    "end_date": data.get("end_date"),
                },
                "keyword": data.get("keyword"),
                "transactions": list(data.get("transaction_results") or []),
                "transaction_query_id": data.get("transaction_query_id"),
                "pagination": {"next_cursor": data.get("next_cursor")},
            },
        )
        await _publish(dependencies, event, config)
        return _terminal_update("emit_transaction_result")

    async def emit_transaction_error(
        state: AgentState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        message = str(
            _data(state).get("safe_error_message")
            or "거래내역을 확인하지 못했습니다. 잠시 후 다시 시도해 주세요."
        )
        event = dependencies.webhook_builder.error(
            chat_session_id=_config_context(config, "chat_session_id"),
            workflow_id=WORKFLOW_ID,
            step_id="emit_transaction_error",
            ui_contract_id="UI-COMMON-ERROR",
            content=message,
            payload={"message": message},
        )
        await _publish(dependencies, event, config)
        return _terminal_update(
            "emit_transaction_error",
            status="workflow_failed",
        )

    graph = StateGraph(AgentState)
    graph.add_node("extract_transaction_slots", extract_transaction_slots)
    graph.add_node("resolve_transaction_accounts", resolve_transaction_accounts)
    graph.add_node(
        "request_transaction_account_selection",
        request_transaction_account_selection,
    )
    graph.add_node(
        "emit_transaction_accounts_empty",
        emit_transaction_accounts_empty,
    )
    graph.add_node("check_transaction_period", check_transaction_period)
    graph.add_node("request_period_selection", request_period_selection)
    graph.add_node("query_transactions", query_transactions)
    graph.add_node("emit_transaction_result", emit_transaction_result)
    graph.add_node("emit_transaction_error", emit_transaction_error)
    graph.set_entry_point("extract_transaction_slots")
    graph.add_edge("extract_transaction_slots", "resolve_transaction_accounts")
    graph.add_conditional_edges(
        "resolve_transaction_accounts",
        _route_key,
        {
            "resolved": "check_transaction_period",
            "selection_required": "request_transaction_account_selection",
            "no_accounts": "emit_transaction_accounts_empty",
            "error": "emit_transaction_error",
        },
    )
    graph.add_conditional_edges(
        "request_transaction_account_selection",
        _route_key,
        {
            "selected": "check_transaction_period",
            "cancelled": END,
            "error": "emit_transaction_error",
        },
    )
    graph.add_edge("emit_transaction_accounts_empty", END)
    graph.add_conditional_edges(
        "check_transaction_period",
        _route_key,
        {
            "normalized": "query_transactions",
            "selection_required": "request_period_selection",
        },
    )
    graph.add_conditional_edges(
        "request_period_selection",
        _route_key,
        {
            "selected": "query_transactions",
            "cancelled": END,
            "error": "emit_transaction_error",
        },
    )
    graph.add_conditional_edges(
        "query_transactions",
        _route_key,
        {
            "succeeded": "emit_transaction_result",
            "error": "emit_transaction_error",
        },
    )
    graph.add_edge("emit_transaction_result", END)
    graph.add_edge("emit_transaction_error", END)
    return graph.compile(checkpointer=checkpointer)
