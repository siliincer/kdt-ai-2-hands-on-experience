"""관리시트 계약 기반 기간 거래 합계 조회 Workflow."""

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
    account_options,
    default_recent_month,
    period_was_mentioned,
    reference_date,
)
from agent.workflows.query_slot_extraction import (
    DatedSlotExtractor,
    extract_amount_summary_slots_by_rule,
    extract_amount_summary_slots_llm_first,
)
from agent.workflows.workflow_support import build_tool_error_update
from agent.workflows.workflow_support import config_context as _config_context
from agent.workflows.workflow_support import (
    new_input_request_id as _default_input_request_id,
)
from agent.workflows.workflow_support import publish_event as _publish
from agent.workflows.workflow_support import route_key as _route_key
from agent.workflows.workflow_support import state_data as _data
from agent.workflows.workflow_support import step_request_id as _default_tool_request_id
from agent.workflows.workflow_support import terminal_update as _terminal_update
from agent.workflows.workflow_support import tool_call as _tool_call

WORKFLOW_ID = "wf_period_amount_summary"
_tool_error_update = build_tool_error_update(
    "거래 합계를 확인하지 못했습니다. 잠시 후 다시 시도해 주세요."
)


def _default_now() -> datetime:
    return datetime.now(timezone.utc)


def extract_amount_summary_slots_from_text(
    message: str,
    requested_date: date,
) -> Mapping[str, Any]:
    """테스트와 장애 폴백용 결정적 기간 합계 Slot 추출."""

    return extract_amount_summary_slots_by_rule(message, requested_date)


@dataclass(frozen=True, slots=True)
class PeriodAmountSummaryDependencies:
    """기간 합계 Workflow가 공통 기반에서 주입받는 의존성."""

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
        default=extract_amount_summary_slots_llm_first
    )


def build_period_amount_summary_graph(
    dependencies: PeriodAmountSummaryDependencies,
    *,
    checkpointer: Any = None,
) -> Any:
    """기간 거래 합계 Step과 Route를 관리시트 순서대로 컴파일한다."""

    async def extract_amount_summary_slots(
        state: AgentState,
    ) -> dict[str, Any]:
        data = _data(state)
        extracted = await dependencies.slot_extractor(
            str(state.get("user_input") or ""),
            reference_date(data, fallback=dependencies.now_factory()),
        )
        return {
            "workflow_id": WORKFLOW_ID,
            "current_step_id": "extract_amount_summary_slots",
            "route_key": "extracted",
            "data": {
                "account_hint": extracted.get("account_hint"),
                "all_accounts_requested": bool(
                    extracted.get("all_accounts_requested", True)
                ),
                "start_date": extracted.get("start_date"),
                "end_date": extracted.get("end_date"),
                "summary_type": extracted.get("summary_type"),
                "keyword": extracted.get("keyword"),
            },
        }

    async def resolve_summary_accounts(
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
                    step_id="resolve_summary_accounts",
                    arguments={
                        "account_hint": data.get("account_hint"),
                        "account_capability": "inquiry",
                        "resolve_selection": True,
                        "all_accounts_requested": bool(
                            data.get("all_accounts_requested", True)
                        ),
                    },
                ),
            )
        except (AgentToolIntegrationError, ContractToolInputError) as error:
            return _tool_error_update("resolve_summary_accounts", error)

        outcome = result.get("account_resolution_outcome")
        if outcome not in {"resolved", "selection_required", "no_accounts"}:
            return _tool_error_update(
                "resolve_summary_accounts",
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
            "current_step_id": "resolve_summary_accounts",
            "route_key": outcome,
            "data": update,
        }

    async def request_summary_account_selection(
        state: AgentState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        data = _data(state)
        input_request_id = _required_input_request_id(data)
        event = dependencies.webhook_builder.need_input(
            chat_session_id=_config_context(config, "chat_session_id"),
            workflow_id=WORKFLOW_ID,
            step_id="request_summary_account_selection",
            input_request_id=input_request_id,
            ui_contract_id="UI-SUMMARY-ACCOUNT-SELECTION",
            ui_type="account_card_list",
            content="합계를 확인할 계좌를 선택해 주세요.",
            payload={
                "title": "계좌를 선택해 주세요.",
                "accounts": account_options(data.get("accounts")),
                "actions": ["select", "cancel"],
            },
        )
        dependencies.interaction_runtime.pause(event)
        resumed_data = _data(state)
        outcome = resumed_data.get("account_selection_outcome")
        route_key = outcome if outcome in {"selected", "cancelled"} else "error"
        return {
            "current_step_id": "request_summary_account_selection",
            "route_key": route_key,
            "status": "completed" if route_key == "cancelled" else "running",
            "data": {"input_request_id": None},
        }

    async def emit_summary_accounts_empty(
        state: AgentState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        event = dependencies.webhook_builder.component(
            chat_session_id=_config_context(config, "chat_session_id"),
            workflow_id=WORKFLOW_ID,
            step_id="emit_summary_accounts_empty",
            ui_contract_id="UI-SUMMARY-ACCOUNT-SELECTION",
            ui_type="account_card_list",
            content="집계 가능한 계좌가 없습니다.",
            payload={
                "title": "집계 가능한 계좌가 없습니다.",
                "accounts": [],
                "actions": [],
            },
        )
        await _publish(dependencies, event, config)
        return _terminal_update("emit_summary_accounts_empty")

    async def check_summary_period(
        state: AgentState,
    ) -> dict[str, Any]:
        data = _data(state)
        start_date = _valid_date(data.get("start_date"))
        end_date = _valid_date(data.get("end_date"))
        message = str(state.get("user_input") or "")
        if start_date is not None and end_date is not None:
            return {
                "current_step_id": "check_summary_period",
                "route_key": "normalized",
                "data": {
                    "start_date": start_date,
                    "end_date": end_date,
                },
            }
        if period_was_mentioned(message):
            return {
                "current_step_id": "check_summary_period",
                "route_key": "selection_required",
                "data": {
                    "input_request_id": dependencies.input_request_id_factory(),
                },
            }
        default_start, default_end = default_recent_month(
            reference_date(data, fallback=dependencies.now_factory())
        )
        return {
            "current_step_id": "check_summary_period",
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
        dependencies.interaction_runtime.pause(event)
        resumed_data = _data(state)
        outcome = resumed_data.get("period_selection_outcome")
        route_key = outcome if outcome in {"selected", "cancelled"} else "error"
        return {
            "current_step_id": "request_period_selection",
            "route_key": route_key,
            "status": "completed" if route_key == "cancelled" else "running",
            "data": {"input_request_id": None},
        }

    async def check_summary_type(
        state: AgentState,
    ) -> dict[str, Any]:
        summary_type = _data(state).get("summary_type")
        if summary_type in {"spending", "income"}:
            return {
                "current_step_id": "check_summary_type",
                "route_key": "resolved",
                "data": {"summary_type": summary_type},
            }
        return {
            "current_step_id": "check_summary_type",
            "route_key": "selection_required",
            "data": {
                "input_request_id": dependencies.input_request_id_factory(),
            },
        }

    async def request_summary_type(
        state: AgentState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        input_request_id = _required_input_request_id(_data(state))
        event = dependencies.webhook_builder.need_input(
            chat_session_id=_config_context(config, "chat_session_id"),
            workflow_id=WORKFLOW_ID,
            step_id="request_summary_type",
            input_request_id=input_request_id,
            ui_contract_id="UI-SUMMARY-TYPE-SELECTION",
            ui_type="option_select",
            content="합계 유형을 선택해 주세요.",
            payload={
                "title": "합계 유형을 선택해 주세요.",
                "options": [
                    {"value": "spending", "label": "지출"},
                    {"value": "income", "label": "수입"},
                ],
                "actions": ["select", "cancel"],
            },
        )
        dependencies.interaction_runtime.pause(event)
        resumed_data = _data(state)
        outcome = resumed_data.get("summary_type_selection_outcome")
        route_key = outcome if outcome in {"selected", "cancelled"} else "error"
        return {
            "current_step_id": "request_summary_type",
            "route_key": route_key,
            "status": "completed" if route_key == "cancelled" else "running",
            "data": {"input_request_id": None},
        }

    async def query_transaction_summary(
        state: AgentState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        data = _data(state)
        try:
            result = await dependencies.tool_registry.invoke_by_tool(
                "query_transaction_summary",
                _tool_call(
                    config,
                    dependencies=dependencies,
                    step_id="query_transaction_summary",
                    arguments={
                        "account_ids": list(data.get("account_ids") or []),
                        "start_date": data.get("start_date"),
                        "end_date": data.get("end_date"),
                        "summary_type": data.get("summary_type"),
                        "keyword": data.get("keyword"),
                    },
                ),
            )
        except (AgentToolIntegrationError, ContractToolInputError) as error:
            return _tool_error_update("query_transaction_summary", error)
        return {
            "current_step_id": "query_transaction_summary",
            "route_key": "succeeded",
            "data": {"summary_result": result.get("summary_result")},
        }

    async def emit_amount_summary(
        state: AgentState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        data = _data(state)
        summary = data.get("summary_result")
        summary_payload = dict(summary) if isinstance(summary, Mapping) else {}
        event = dependencies.webhook_builder.component(
            chat_session_id=_config_context(config, "chat_session_id"),
            workflow_id=WORKFLOW_ID,
            step_id="emit_amount_summary",
            ui_contract_id="UI-AMOUNT-SUMMARY",
            ui_type="amount_summary",
            content="기간 거래 합계를 확인했습니다.",
            payload={
                "account_ids": list(data.get("account_ids") or []),
                "keyword": data.get("keyword"),
                "start_date": summary_payload.get("start_date"),
                "end_date": summary_payload.get("end_date"),
                "summary_type": summary_payload.get("summary_type"),
                "total_amount": summary_payload.get("total_amount"),
                "transaction_count": summary_payload.get("transaction_count"),
                "currency": summary_payload.get("currency"),
            },
        )
        await _publish(dependencies, event, config)
        return _terminal_update("emit_amount_summary")

    async def emit_amount_summary_error(
        state: AgentState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        message = str(
            _data(state).get("safe_error_message")
            or "거래 합계를 확인하지 못했습니다. 잠시 후 다시 시도해 주세요."
        )
        event = dependencies.webhook_builder.error(
            chat_session_id=_config_context(config, "chat_session_id"),
            workflow_id=WORKFLOW_ID,
            step_id="emit_amount_summary_error",
            ui_contract_id="UI-COMMON-ERROR",
            content=message,
            payload={"message": message},
        )
        await _publish(dependencies, event, config)
        return _terminal_update(
            "emit_amount_summary_error",
            status="workflow_failed",
        )

    graph = StateGraph(AgentState)
    graph.add_node("extract_amount_summary_slots", extract_amount_summary_slots)
    graph.add_node("resolve_summary_accounts", resolve_summary_accounts)
    graph.add_node(
        "request_summary_account_selection",
        request_summary_account_selection,
    )
    graph.add_node("emit_summary_accounts_empty", emit_summary_accounts_empty)
    graph.add_node("check_summary_period", check_summary_period)
    graph.add_node("request_period_selection", request_period_selection)
    graph.add_node("check_summary_type", check_summary_type)
    graph.add_node("request_summary_type", request_summary_type)
    graph.add_node("query_transaction_summary", query_transaction_summary)
    graph.add_node("emit_amount_summary", emit_amount_summary)
    graph.add_node("emit_amount_summary_error", emit_amount_summary_error)
    graph.set_entry_point("extract_amount_summary_slots")
    graph.add_edge("extract_amount_summary_slots", "resolve_summary_accounts")
    graph.add_conditional_edges(
        "resolve_summary_accounts",
        _route_key,
        {
            "resolved": "check_summary_period",
            "selection_required": "request_summary_account_selection",
            "no_accounts": "emit_summary_accounts_empty",
            "error": "emit_amount_summary_error",
        },
    )
    graph.add_conditional_edges(
        "request_summary_account_selection",
        _route_key,
        {
            "selected": "check_summary_period",
            "cancelled": END,
            "error": "emit_amount_summary_error",
        },
    )
    graph.add_edge("emit_summary_accounts_empty", END)
    graph.add_conditional_edges(
        "check_summary_period",
        _route_key,
        {
            "normalized": "check_summary_type",
            "selection_required": "request_period_selection",
        },
    )
    graph.add_conditional_edges(
        "request_period_selection",
        _route_key,
        {
            "selected": "check_summary_type",
            "cancelled": END,
            "error": "emit_amount_summary_error",
        },
    )
    graph.add_conditional_edges(
        "check_summary_type",
        _route_key,
        {
            "resolved": "query_transaction_summary",
            "selection_required": "request_summary_type",
        },
    )
    graph.add_conditional_edges(
        "request_summary_type",
        _route_key,
        {
            "selected": "query_transaction_summary",
            "cancelled": END,
            "error": "emit_amount_summary_error",
        },
    )
    graph.add_conditional_edges(
        "query_transaction_summary",
        _route_key,
        {
            "succeeded": "emit_amount_summary",
            "error": "emit_amount_summary_error",
        },
    )
    graph.add_edge("emit_amount_summary", END)
    graph.add_edge("emit_amount_summary_error", END)
    return graph.compile(checkpointer=checkpointer)


def _required_input_request_id(data: Mapping[str, Any]) -> str:
    value = data.get("input_request_id")
    if not isinstance(value, str) or not value:
        raise ValueError("입력 요청 ID가 없습니다.")
    return value


def _valid_date(value: Any) -> str | None:
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        try:
            return date.fromisoformat(value).isoformat()
        except ValueError:
            return None
    return None
