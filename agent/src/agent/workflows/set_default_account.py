"""관리시트 계약 기반 기본 출금 계좌 변경(wf_set_default_account) Workflow.

Agent Route 매핑은 agent-tools-api-spec.md §19.7·§20.6 표를 그대로 옮긴 것이다.
`wf_internal_transfer`와 구조가 같은 Prepare→승인→Execute 패턴이지만 추가
인증이 없고(auth_policy=none), 수정 대상이 "account" 하나뿐이라 대상별 분기가
없다.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, StateGraph

from agent.clients.backend import BackendWebhookClient
from agent.clients.backend.client import AgentToolApiError, AgentToolIntegrationError
from agent.contracts.backend import AgentWebhookRequest
from agent.runtime import InteractionPauseRuntime, InteractionWebhookBuilder
from agent.state import AgentState
from agent.tools.contract_registry import (
    ContractToolCall,
    ContractToolInputError,
    ContractToolRegistry,
)
from agent.workflows.setting_slot_extraction import (
    SettingSlotExtractor,
    extract_default_account_slots_by_rule,
    extract_default_account_slots_llm_first,
)

WORKFLOW_ID = "wf_set_default_account"


def _default_input_request_id() -> str:
    return f"input_{uuid.uuid4().hex}"


def _default_tool_request_id(parent_request_id: str, step_id: str) -> str:
    return f"{parent_request_id}:{step_id}"


def extract_default_account_slots_from_text(message: str) -> Mapping[str, Any]:
    """테스트와 장애 폴백용 결정적 기본 출금 계좌 변경 Slot 추출."""

    return extract_default_account_slots_by_rule(message)


@dataclass(frozen=True, slots=True)
class DefaultAccountChangeDependencies:
    """기본 출금 계좌 변경 Workflow가 공유 기반에서 주입받는 외부 의존성."""

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
    slot_extractor: SettingSlotExtractor = field(
        default=extract_default_account_slots_llm_first
    )


def build_set_default_account_graph(
    dependencies: DefaultAccountChangeDependencies,
    *,
    checkpointer: Any = None,
) -> Any:
    """기본 출금 계좌 변경 Step과 Route를 관리시트 순서대로 컴파일한다."""

    async def extract_default_account_slots(state: AgentState) -> dict[str, Any]:
        user_input = str(state.get("user_input") or "")
        extracted = await dependencies.slot_extractor(user_input)
        return {
            "workflow_id": WORKFLOW_ID,
            "current_step_id": "extract_default_account_slots",
            "route_key": "always",
            "data": {"account_hint": extracted.get("account_hint")},
        }

    async def resolve_default_account(
        state: AgentState, config: RunnableConfig
    ) -> dict[str, Any]:
        data = _data(state)
        try:
            result = await dependencies.tool_registry.invoke_by_tool(
                "fetch_accounts",
                _tool_call(
                    config,
                    dependencies=dependencies,
                    step_id="resolve_default_account",
                    arguments={
                        "account_hint": data.get("account_hint"),
                        "account_capability": "settings",
                        "resolve_selection": True,
                    },
                ),
            )
        except (AgentToolIntegrationError, ContractToolInputError) as error:
            return _tool_error_update("resolve_default_account", error)

        outcome = result.get("account_resolution_outcome")
        if outcome not in {"resolved", "selection_required", "no_accounts"}:
            return _tool_error_update(
                "resolve_default_account",
                ValueError("계좌 확인 결과가 올바르지 않습니다."),
            )
        account_ids = list(result.get("account_ids") or [])
        update: dict[str, Any] = {
            "account_resolution_outcome": outcome,
            "accounts": list(result.get("accounts") or []),
        }
        if outcome == "resolved":
            if len(account_ids) != 1:
                return _tool_error_update(
                    "resolve_default_account",
                    ValueError("resolved 응답의 계좌가 정확히 하나가 아닙니다."),
                )
            update["account_id"] = account_ids[0]
        elif outcome == "selection_required":
            update["input_request_id"] = dependencies.input_request_id_factory()
        return {
            "current_step_id": "resolve_default_account",
            "route_key": outcome,
            "data": update,
        }

    async def request_default_account_selection(
        state: AgentState, config: RunnableConfig
    ) -> dict[str, Any]:
        data = _data(state)
        input_request_id = data.get("input_request_id")
        if not isinstance(input_request_id, str) or not input_request_id:
            return _tool_error_update(
                "request_default_account_selection",
                ValueError("입력 요청 ID가 없습니다."),
            )
        event = dependencies.webhook_builder.need_input(
            chat_session_id=_config_context(config, "chat_session_id"),
            workflow_id=WORKFLOW_ID,
            step_id="request_default_account_selection",
            input_request_id=input_request_id,
            ui_contract_id="UI-DEFAULT-ACCOUNT-SELECTION",
            ui_type="account_card_list",
            content="새 기본 출금 계좌를 선택해 주세요.",
            payload={
                "title": "새 기본 출금 계좌를 선택해 주세요.",
                "accounts": _account_options(data.get("accounts")),
                "actions": ["select", "cancel"],
            },
        )
        dependencies.interaction_runtime.pause(event)

        resumed = _data(state)
        outcome = resumed.get("account_selection_outcome")
        if outcome == "selected":
            account_id = resumed.get("account_id")
            if not isinstance(account_id, str) or not account_id:
                return _tool_error_update(
                    "request_default_account_selection",
                    ValueError("selected 응답에 account_id가 없습니다."),
                )
            return {
                "current_step_id": "request_default_account_selection",
                "route_key": "selected",
                "data": {"input_request_id": None},
            }
        if outcome == "cancelled":
            return {
                "current_step_id": "request_default_account_selection",
                "route_key": "cancelled",
                "status": "completed",
                "data": {"input_request_id": None},
            }
        return _tool_error_update(
            "request_default_account_selection",
            ValueError("계좌 선택 재개 결과가 올바르지 않습니다."),
        )

    async def emit_default_account_selection_empty(
        state: AgentState, config: RunnableConfig
    ) -> dict[str, Any]:
        event = dependencies.webhook_builder.component(
            chat_session_id=_config_context(config, "chat_session_id"),
            workflow_id=WORKFLOW_ID,
            step_id="emit_default_account_selection_empty",
            ui_contract_id="UI-DEFAULT-ACCOUNT-SELECTION",
            ui_type="account_card_list",
            content="변경 가능한 계좌가 없습니다.",
            payload={
                "title": "변경 가능한 계좌가 없습니다.",
                "accounts": [],
                "actions": [],
            },
        )
        await _publish(dependencies, event, config)
        return _terminal_update("emit_default_account_selection_empty")

    async def start_default_account_prepare(state: AgentState) -> dict[str, Any]:
        attempt = int(_data(state).get("prepare_attempt") or 0) + 1
        return {
            "current_step_id": "start_default_account_prepare",
            "route_key": "always",
            "data": {"prepare_attempt": attempt, "correction_view": None},
        }

    async def prepare_default_account_change(
        state: AgentState, config: RunnableConfig
    ) -> dict[str, Any]:
        data = _data(state)
        idempotency_key = (
            f"default_account_prepare:"
            f"{_config_context(config, 'execution_context_id')}:"
            f"{data.get('prepare_attempt')}"
        )
        try:
            result = await dependencies.tool_registry.invoke_by_tool(
                "prepare_default_account_change",
                _tool_call(
                    config,
                    dependencies=dependencies,
                    step_id="prepare_default_account_change",
                    arguments={"account_id": data.get("account_id")},
                    idempotency_key=idempotency_key,
                ),
            )
        except (AgentToolIntegrationError, ContractToolInputError) as error:
            return _tool_error_update("prepare_default_account_change", error)

        outcome = result.get("outcome")
        update: dict[str, Any] = {}
        if outcome == "ready_for_confirmation":
            update["confirmation_id"] = result.get("confirmation_id")
            update["confirmation_view"] = result.get("confirmation_view")
        elif outcome == "unchanged":
            pass
        elif outcome == "correction_required":
            targets = list(
                (result.get("correction_view") or {}).get("allowed_change_targets")
                or []
            )
            if targets != ["account"]:
                return _tool_error_update(
                    "prepare_default_account_change",
                    ValueError("수정 대상이 계약과 일치하지 않습니다."),
                )
            update["correction_view"] = result.get("correction_view")
        elif outcome == "blocked":
            update["blocked_view"] = result.get("blocked_view")
        else:
            return _tool_error_update(
                "prepare_default_account_change",
                ValueError("Prepare 응답 outcome이 계약과 일치하지 않습니다."),
            )
        return {
            "current_step_id": "prepare_default_account_change",
            "route_key": outcome,
            "data": update,
        }

    async def emit_default_account_unchanged(
        state: AgentState, config: RunnableConfig
    ) -> dict[str, Any]:
        data = _data(state)
        event = dependencies.webhook_builder.component(
            chat_session_id=_config_context(config, "chat_session_id"),
            workflow_id=WORKFLOW_ID,
            step_id="emit_default_account_unchanged",
            ui_contract_id="UI-DEFAULT-ACCOUNT-RESULT",
            ui_type="setting_result",
            content="이미 기본 출금 계좌로 설정되어 있습니다.",
            payload={
                "purpose": "default_account",
                "outcome": "unchanged",
                "account": {"account_id": data.get("account_id")},
            },
        )
        await _publish(dependencies, event, config)
        return _terminal_update("emit_default_account_unchanged")

    async def emit_default_account_blocked(
        state: AgentState, config: RunnableConfig
    ) -> dict[str, Any]:
        view = _data(state).get("blocked_view") or {}
        event = dependencies.webhook_builder.blocked(
            chat_session_id=_config_context(config, "chat_session_id"),
            workflow_id=WORKFLOW_ID,
            step_id="emit_default_account_blocked",
            ui_contract_id="UI-SETTING-BLOCKED",
            content=str(view.get("title") or "기본 출금 계좌를 변경할 수 없습니다."),
            payload=dict(view),
        )
        await _publish(dependencies, event, config)
        return _terminal_update(
            "emit_default_account_blocked", status="workflow_failed"
        )

    async def request_default_account_approval(
        state: AgentState, config: RunnableConfig
    ) -> dict[str, Any]:
        data = _data(state)
        confirmation_id = data.get("confirmation_id")
        if not isinstance(confirmation_id, str) or not confirmation_id:
            return _tool_error_update(
                "request_default_account_approval",
                ValueError("Confirmation ID가 없습니다."),
            )
        event = dependencies.webhook_builder.need_approval(
            chat_session_id=_config_context(config, "chat_session_id"),
            workflow_id=WORKFLOW_ID,
            step_id="request_default_account_approval",
            confirmation_id=confirmation_id,
            ui_contract_id="UI-DEFAULT-ACCOUNT-CONFIRMATION",
            content="기본 출금 계좌 변경 내용을 확인하고 승인해 주세요.",
            payload=_confirmation_payload(data.get("confirmation_view")),
        )
        dependencies.interaction_runtime.pause(event)

        resumed = _data(state)
        outcome = resumed.get("approval_outcome")
        if outcome == "approved":
            return {
                "current_step_id": "request_default_account_approval",
                "route_key": "approved",
            }
        if outcome == "change_requested":
            return {
                "current_step_id": "request_default_account_approval",
                "route_key": "change_requested",
            }
        if outcome == "cancelled":
            return {
                "current_step_id": "request_default_account_approval",
                "route_key": "cancelled",
                "status": "completed",
            }
        return _tool_error_update(
            "request_default_account_approval",
            ValueError("승인 재개 결과가 올바르지 않습니다."),
        )

    async def reset_default_account_target(state: AgentState) -> dict[str, Any]:
        clears = (
            "account_hint",
            "account_resolution_outcome",
            "accounts",
            "account_id",
            "account_selection_outcome",
            "input_request_id",
            "confirmation_id",
            "confirmation_view",
            "approval_outcome",
        )
        return {
            "current_step_id": "reset_default_account_target",
            "route_key": "always",
            "data": {key: None for key in clears},
        }

    async def execute_default_account_change(
        state: AgentState, config: RunnableConfig
    ) -> dict[str, Any]:
        data = _data(state)
        idempotency_key = f"default_account_execute:{data.get('confirmation_id')}"
        try:
            result = await dependencies.tool_registry.invoke_by_tool(
                "execute_default_account_change",
                _tool_call(
                    config,
                    dependencies=dependencies,
                    step_id="execute_default_account_change",
                    arguments={"confirmation_id": data.get("confirmation_id")},
                    idempotency_key=idempotency_key,
                ),
            )
        except (AgentToolIntegrationError, ContractToolInputError) as error:
            return _tool_error_update("execute_default_account_change", error)

        outcome = result.get("outcome")
        if outcome == "completed":
            return {
                "current_step_id": "execute_default_account_change",
                "route_key": outcome,
                "data": {
                    "account_id": result.get("account_id"),
                    "completed_at": result.get("completed_at"),
                },
            }
        if outcome == "correction_required":
            targets = list(
                (result.get("correction_view") or {}).get("allowed_change_targets")
                or []
            )
            if targets != ["account"]:
                return _tool_error_update(
                    "execute_default_account_change",
                    ValueError("수정 대상이 계약과 일치하지 않습니다."),
                )
            return {
                "current_step_id": "execute_default_account_change",
                "route_key": outcome,
                "data": {
                    "correction_view": result.get("correction_view"),
                    "confirmation_id": None,
                },
            }
        if outcome == "blocked":
            return {
                "current_step_id": "execute_default_account_change",
                "route_key": outcome,
                "data": {"blocked_view": result.get("blocked_view")},
            }
        return _tool_error_update(
            "execute_default_account_change",
            ValueError("Execute 응답 outcome이 계약과 일치하지 않습니다."),
        )

    async def emit_default_account_result(
        state: AgentState, config: RunnableConfig
    ) -> dict[str, Any]:
        data = _data(state)
        view = data.get("confirmation_view") or {}
        event = dependencies.webhook_builder.component(
            chat_session_id=_config_context(config, "chat_session_id"),
            workflow_id=WORKFLOW_ID,
            step_id="emit_default_account_result",
            ui_contract_id="UI-DEFAULT-ACCOUNT-RESULT",
            ui_type="setting_result",
            content="기본 출금 계좌를 변경했습니다.",
            payload={
                "purpose": "default_account",
                "outcome": "completed",
                "account": view.get("new_default_account")
                or {"account_id": data.get("account_id")},
                "completed_at": data.get("completed_at"),
            },
        )
        await _publish(dependencies, event, config)
        return _terminal_update("emit_default_account_result")

    async def emit_default_account_error(
        state: AgentState, config: RunnableConfig
    ) -> dict[str, Any]:
        message = str(
            _data(state).get("safe_error_message")
            or "설정을 변경하지 못했습니다. 잠시 후 다시 시도해 주세요."
        )
        event = dependencies.webhook_builder.error(
            chat_session_id=_config_context(config, "chat_session_id"),
            workflow_id=WORKFLOW_ID,
            step_id="emit_default_account_error",
            ui_contract_id="UI-COMMON-ERROR",
            content=message,
            payload={"message": message},
        )
        await _publish(dependencies, event, config)
        return _terminal_update("emit_default_account_error", status="workflow_failed")

    graph = StateGraph(AgentState)
    graph.add_node("extract_default_account_slots", extract_default_account_slots)
    graph.add_node("resolve_default_account", resolve_default_account)
    graph.add_node(
        "request_default_account_selection", request_default_account_selection
    )
    graph.add_node(
        "emit_default_account_selection_empty", emit_default_account_selection_empty
    )
    graph.add_node("start_default_account_prepare", start_default_account_prepare)
    graph.add_node("prepare_default_account_change", prepare_default_account_change)
    graph.add_node("emit_default_account_unchanged", emit_default_account_unchanged)
    graph.add_node("emit_default_account_blocked", emit_default_account_blocked)
    graph.add_node("request_default_account_approval", request_default_account_approval)
    graph.add_node("reset_default_account_target", reset_default_account_target)
    graph.add_node("execute_default_account_change", execute_default_account_change)
    graph.add_node("emit_default_account_result", emit_default_account_result)
    graph.add_node("emit_default_account_error", emit_default_account_error)

    graph.set_entry_point("extract_default_account_slots")
    graph.add_edge("extract_default_account_slots", "resolve_default_account")

    graph.add_conditional_edges(
        "resolve_default_account",
        _route_key,
        {
            "resolved": "start_default_account_prepare",
            "selection_required": "request_default_account_selection",
            "no_accounts": "emit_default_account_selection_empty",
            "error": "emit_default_account_error",
        },
    )
    graph.add_conditional_edges(
        "request_default_account_selection",
        _route_key,
        {
            "selected": "start_default_account_prepare",
            "cancelled": END,
            "error": "emit_default_account_error",
        },
    )
    graph.add_edge("emit_default_account_selection_empty", END)

    graph.add_edge("start_default_account_prepare", "prepare_default_account_change")
    graph.add_conditional_edges(
        "prepare_default_account_change",
        _route_key,
        {
            "ready_for_confirmation": "request_default_account_approval",
            "unchanged": "emit_default_account_unchanged",
            "correction_required": "reset_default_account_target",
            "blocked": "emit_default_account_blocked",
            "error": "emit_default_account_error",
        },
    )
    graph.add_edge("emit_default_account_unchanged", END)
    graph.add_edge("emit_default_account_blocked", END)

    graph.add_conditional_edges(
        "request_default_account_approval",
        _route_key,
        {
            "approved": "execute_default_account_change",
            "change_requested": "reset_default_account_target",
            "cancelled": END,
            "error": "emit_default_account_error",
        },
    )
    graph.add_edge("reset_default_account_target", "resolve_default_account")

    graph.add_conditional_edges(
        "execute_default_account_change",
        _route_key,
        {
            "completed": "emit_default_account_result",
            "correction_required": "reset_default_account_target",
            "blocked": "emit_default_account_blocked",
            "error": "emit_default_account_error",
        },
    )
    graph.add_edge("emit_default_account_result", END)
    graph.add_edge("emit_default_account_error", END)

    return graph.compile(checkpointer=checkpointer)


def _data(state: AgentState) -> dict[str, Any]:
    return dict(state.get("data") or {})


def _route_key(state: AgentState) -> str:
    return str(state.get("route_key") or "error")


def _config_context(config: RunnableConfig, key: str) -> str:
    configurable = config.get("configurable") or {}
    value = configurable.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"LangGraph 실행 Context가 없습니다: {key}")
    return value


def _tool_call(
    config: RunnableConfig,
    *,
    dependencies: DefaultAccountChangeDependencies,
    step_id: str,
    arguments: Mapping[str, Any],
    idempotency_key: str | None = None,
) -> ContractToolCall:
    parent_request_id = _config_context(config, "request_id")
    return ContractToolCall(
        execution_context_id=_config_context(config, "execution_context_id"),
        request_id=dependencies.tool_request_id_factory(parent_request_id, step_id),
        arguments=arguments,
        idempotency_key=idempotency_key,
    )


async def _publish(
    dependencies: DefaultAccountChangeDependencies,
    event: AgentWebhookRequest,
    config: RunnableConfig,
) -> None:
    await dependencies.webhook_client.publish(
        event,
        execution_context_id=_config_context(config, "execution_context_id"),
        request_id=_config_context(config, "request_id"),
    )


def _tool_error_update(step_id: str, error: Exception) -> dict[str, Any]:
    if isinstance(error, AgentToolApiError):
        message = error.safe_message
    else:
        message = "설정을 변경하지 못했습니다. 잠시 후 다시 시도해 주세요."
    return {
        "current_step_id": step_id,
        "route_key": "error",
        "data": {"safe_error_message": message},
    }


def _terminal_update(
    step_id: str,
    *,
    status: Literal["completed", "workflow_failed"] = "completed",
) -> dict[str, Any]:
    return {
        "current_step_id": step_id,
        "route_key": "completed",
        "status": status,
    }


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
    )
    return [
        {field: account.get(field) for field in fields}
        for account in accounts
        if isinstance(account, Mapping)
    ]


def _confirmation_payload(raw_view: Any) -> dict[str, Any]:
    view = raw_view if isinstance(raw_view, Mapping) else {}
    return {
        "current_default_account": view.get("current_default_account"),
        "new_default_account": view.get("new_default_account"),
        "expires_at": view.get("expires_at"),
        "actions": ["approve", "modify_account", "cancel"],
    }
