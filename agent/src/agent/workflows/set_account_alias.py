"""관리시트 계약 기반 계좌 별칭 변경(wf_set_account_alias) Workflow.

`wf_set_default_account`와 구조가 같은 Prepare→승인→Execute 패턴이지만 추가
인증이 없고(auth_policy=none), 수정 대상이 "account"·"alias" 둘이라
`_RESET_STEP_BY_TARGET` 딕셔너리로 분기한다. API 스펙(agent-tools-api-spec.md
§21.7·§22.6)이 `correction_required` 응답마다 정확히 하나의 대상만 보장하므로
별도 "route_*_correction" 스텝 없이 Prepare/Execute 노드가 직접 분기한다.
"""

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
from agent.workflows.setting_slot_extraction import (
    SettingSlotExtractor,
    extract_account_alias_slots_by_rule,
    extract_account_alias_slots_llm_first,
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

WORKFLOW_ID = "wf_set_account_alias"
_tool_error_update = build_tool_error_update(
    "설정을 변경하지 못했습니다. 잠시 후 다시 시도해 주세요."
)

# 승인·정정 화면의 수정 대상 2종 — prepare_account_alias_change,
# request_account_alias_approval, execute_account_alias_change가 공유한다.
_RESET_STEP_BY_TARGET = {
    "account": "reset_account_alias_target",
    "alias": "reset_account_alias_value",
}


def extract_account_alias_slots_from_text(message: str) -> Mapping[str, Any]:
    """테스트와 장애 폴백용 결정적 계좌 별칭 변경 Slot 추출."""

    return extract_account_alias_slots_by_rule(message)


def _correction_route_key(prefix: str, correction_view: Any) -> str | None:
    """수정 대상이 정확히 하나일 때만 route_key를 만들고, 아니면 None(계약 오류)."""

    targets = list(
        (correction_view if isinstance(correction_view, Mapping) else {}).get(
            "allowed_change_targets"
        )
        or []
    )
    valid_targets = [target for target in targets if target in _RESET_STEP_BY_TARGET]
    if len(valid_targets) != 1 or len(valid_targets) != len(targets):
        return None
    return f"{prefix}:{valid_targets[0]}"


@dataclass(frozen=True, slots=True)
class AccountAliasChangeDependencies:
    """계좌 별칭 변경 Workflow가 공유 기반에서 주입받는 외부 의존성."""

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
        default=extract_account_alias_slots_llm_first
    )


def build_set_account_alias_graph(
    dependencies: AccountAliasChangeDependencies,
    *,
    checkpointer: Any = None,
) -> Any:
    """계좌 별칭 변경 Step과 Route를 관리시트 순서대로 컴파일한다."""

    async def extract_account_alias_slots(state: AgentState) -> dict[str, Any]:
        user_input = str(state.get("user_input") or "")
        extracted = await dependencies.slot_extractor(user_input)
        return {
            "workflow_id": WORKFLOW_ID,
            "current_step_id": "extract_account_alias_slots",
            "route_key": "always",
            "data": {
                "account_hint": extracted.get("account_hint"),
                "alias": extracted.get("alias"),
            },
        }

    async def resolve_account_alias_target(
        state: AgentState, config: RunnableConfig
    ) -> dict[str, Any]:
        data = _data(state)
        try:
            result = await dependencies.tool_registry.invoke_by_tool(
                "fetch_accounts",
                _tool_call(
                    config,
                    dependencies=dependencies,
                    step_id="resolve_account_alias_target",
                    arguments={
                        "account_hint": data.get("account_hint"),
                        "account_capability": "settings",
                        "resolve_selection": True,
                    },
                ),
            )
        except (AgentToolIntegrationError, ContractToolInputError) as error:
            return _tool_error_update("resolve_account_alias_target", error)

        outcome = result.get("account_resolution_outcome")
        if outcome not in {"resolved", "selection_required", "no_accounts"}:
            return _tool_error_update(
                "resolve_account_alias_target",
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
                    "resolve_account_alias_target",
                    ValueError("resolved 응답의 계좌가 정확히 하나가 아닙니다."),
                )
            update["account_id"] = account_ids[0]
        elif outcome == "selection_required":
            update["input_request_id"] = dependencies.input_request_id_factory()
        return {
            "current_step_id": "resolve_account_alias_target",
            "route_key": outcome,
            "data": update,
        }

    async def request_account_alias_selection(
        state: AgentState, config: RunnableConfig
    ) -> dict[str, Any]:
        data = _data(state)
        input_request_id = data.get("input_request_id")
        if not isinstance(input_request_id, str) or not input_request_id:
            return _tool_error_update(
                "request_account_alias_selection",
                ValueError("입력 요청 ID가 없습니다."),
            )
        event = dependencies.webhook_builder.need_input(
            chat_session_id=_config_context(config, "chat_session_id"),
            workflow_id=WORKFLOW_ID,
            step_id="request_account_alias_selection",
            input_request_id=input_request_id,
            ui_contract_id="UI-ACCOUNT-ALIAS-SELECTION",
            ui_type="account_card_list",
            content="별칭을 변경할 계좌를 선택해 주세요.",
            payload={
                "title": "별칭을 변경할 계좌를 선택해 주세요.",
                "accounts": _account_options(data.get("accounts")),
                "actions": ["select", "cancel"],
            },
        )
        resumed = _resume_data(state, dependencies.interaction_runtime, event)
        outcome = resumed.get("account_selection_outcome")
        if outcome == "selected":
            account_id = resumed.get("account_id")
            if not isinstance(account_id, str) or not account_id:
                return _tool_error_update(
                    "request_account_alias_selection",
                    ValueError("selected 응답에 account_id가 없습니다."),
                )
            return {
                "current_step_id": "request_account_alias_selection",
                "route_key": "selected",
                "data": _resume_update(resumed, input_request_id=None),
            }
        if outcome == "cancelled":
            return {
                "current_step_id": "request_account_alias_selection",
                "route_key": "cancelled",
                "status": "completed",
                "data": _resume_update(resumed, input_request_id=None),
            }
        return _tool_error_update(
            "request_account_alias_selection",
            ValueError("계좌 선택 재개 결과가 올바르지 않습니다."),
        )

    async def emit_account_alias_selection_empty(
        state: AgentState, config: RunnableConfig
    ) -> dict[str, Any]:
        event = dependencies.webhook_builder.component(
            chat_session_id=_config_context(config, "chat_session_id"),
            workflow_id=WORKFLOW_ID,
            step_id="emit_account_alias_selection_empty",
            ui_contract_id="UI-ACCOUNT-ALIAS-SELECTION",
            ui_type="account_card_list",
            content="별칭을 변경할 수 있는 계좌가 없습니다.",
            payload={
                "title": "별칭을 변경할 수 있는 계좌가 없습니다.",
                "accounts": [],
                "actions": [],
            },
        )
        await _publish(dependencies, event, config)
        return _terminal_update("emit_account_alias_selection_empty")

    async def check_account_alias_value(state: AgentState) -> dict[str, Any]:
        alias = _data(state).get("alias")
        valid = isinstance(alias, str) and 0 < len(alias.strip()) <= 30
        return {
            "current_step_id": "check_account_alias_value",
            "route_key": "present" if valid else "missing",
        }

    async def request_account_alias_input(
        state: AgentState, config: RunnableConfig
    ) -> dict[str, Any]:
        input_request_id = dependencies.input_request_id_factory()
        event = dependencies.webhook_builder.need_input(
            chat_session_id=_config_context(config, "chat_session_id"),
            workflow_id=WORKFLOW_ID,
            step_id="request_account_alias_input",
            input_request_id=input_request_id,
            ui_contract_id="UI-ACCOUNT-ALIAS-INPUT",
            ui_type="text_input",
            content="새 계좌 별칭을 입력해 주세요.",
            payload={
                "title": "새 계좌 별칭을 입력해 주세요.",
                "description": "계좌를 구분하기 쉬운 이름을 입력해 주세요.",
                "value": None,
                "validation": {"required": True, "max_length": 30},
                "actions": ["submit", "cancel"],
            },
        )
        resumed = _resume_data(state, dependencies.interaction_runtime, event)
        outcome = resumed.get("alias_input_outcome")
        if outcome == "submitted":
            alias = resumed.get("alias")
            if not isinstance(alias, str) or not (0 < len(alias.strip()) <= 30):
                return _tool_error_update(
                    "request_account_alias_input",
                    ValueError("제출된 별칭이 계약과 일치하지 않습니다."),
                )
            return {
                "current_step_id": "request_account_alias_input",
                "route_key": "submitted",
                "data": _resume_update(resumed, input_request_id=None),
            }
        if outcome == "cancelled":
            return {
                "current_step_id": "request_account_alias_input",
                "route_key": "cancelled",
                "status": "completed",
                "data": _resume_update(resumed, input_request_id=None),
            }
        return _tool_error_update(
            "request_account_alias_input",
            ValueError("별칭 입력 재개 결과가 올바르지 않습니다."),
        )

    async def start_account_alias_prepare(state: AgentState) -> dict[str, Any]:
        attempt = int(_data(state).get("prepare_attempt") or 0) + 1
        return {
            "current_step_id": "start_account_alias_prepare",
            "route_key": "always",
            "data": {"prepare_attempt": attempt, "correction_view": None},
        }

    async def prepare_account_alias_change(
        state: AgentState, config: RunnableConfig
    ) -> dict[str, Any]:
        data = _data(state)
        idempotency_key = (
            f"account_alias_prepare:"
            f"{_config_context(config, 'execution_context_id')}:"
            f"{data.get('prepare_attempt')}"
        )
        try:
            result = await dependencies.tool_registry.invoke_by_tool(
                "prepare_account_alias_change",
                _tool_call(
                    config,
                    dependencies=dependencies,
                    step_id="prepare_account_alias_change",
                    arguments={
                        "account_id": data.get("account_id"),
                        "alias": data.get("alias"),
                    },
                    idempotency_key=idempotency_key,
                ),
            )
        except (AgentToolIntegrationError, ContractToolInputError) as error:
            return _tool_error_update("prepare_account_alias_change", error)

        outcome = result.get("outcome")
        if outcome == "ready_for_confirmation":
            return {
                "current_step_id": "prepare_account_alias_change",
                "route_key": outcome,
                "data": {
                    "confirmation_id": result.get("confirmation_id"),
                    "confirmation_view": result.get("confirmation_view"),
                },
            }
        if outcome == "unchanged":
            return {
                "current_step_id": "prepare_account_alias_change",
                "route_key": outcome,
                "data": {},
            }
        if outcome == "correction_required":
            route_key = _correction_route_key(
                "correction_required", result.get("correction_view")
            )
            if route_key is None:
                return _tool_error_update(
                    "prepare_account_alias_change",
                    ValueError("수정 대상이 계약과 일치하지 않습니다."),
                )
            return {
                "current_step_id": "prepare_account_alias_change",
                "route_key": route_key,
                "data": {"correction_view": result.get("correction_view")},
            }
        if outcome == "blocked":
            return {
                "current_step_id": "prepare_account_alias_change",
                "route_key": outcome,
                "data": {"blocked_view": result.get("blocked_view")},
            }
        return _tool_error_update(
            "prepare_account_alias_change",
            ValueError("Prepare 응답 outcome이 계약과 일치하지 않습니다."),
        )

    async def emit_account_alias_unchanged(
        state: AgentState, config: RunnableConfig
    ) -> dict[str, Any]:
        data = _data(state)
        event = dependencies.webhook_builder.component(
            chat_session_id=_config_context(config, "chat_session_id"),
            workflow_id=WORKFLOW_ID,
            step_id="emit_account_alias_unchanged",
            ui_contract_id="UI-ACCOUNT-ALIAS-RESULT",
            ui_type="setting_result",
            content="이미 같은 별칭으로 설정되어 있습니다.",
            payload={
                "purpose": "account_alias",
                "outcome": "unchanged",
                "account": {"account_id": data.get("account_id")},
                "alias": data.get("alias"),
            },
        )
        await _publish(dependencies, event, config)
        return _terminal_update("emit_account_alias_unchanged")

    async def emit_account_alias_blocked(
        state: AgentState, config: RunnableConfig
    ) -> dict[str, Any]:
        view = _data(state).get("blocked_view") or {}
        event = dependencies.webhook_builder.blocked(
            chat_session_id=_config_context(config, "chat_session_id"),
            workflow_id=WORKFLOW_ID,
            step_id="emit_account_alias_blocked",
            ui_contract_id="UI-SETTING-BLOCKED",
            content=str(view.get("title") or "계좌 별칭을 변경할 수 없습니다."),
            payload=dict(view),
        )
        await _publish(dependencies, event, config)
        return _terminal_update("emit_account_alias_blocked", status="workflow_failed")

    async def request_account_alias_approval(
        state: AgentState, config: RunnableConfig
    ) -> dict[str, Any]:
        data = _data(state)
        confirmation_id = data.get("confirmation_id")
        if not isinstance(confirmation_id, str) or not confirmation_id:
            return _tool_error_update(
                "request_account_alias_approval",
                ValueError("Confirmation ID가 없습니다."),
            )
        event = dependencies.webhook_builder.need_approval(
            chat_session_id=_config_context(config, "chat_session_id"),
            workflow_id=WORKFLOW_ID,
            step_id="request_account_alias_approval",
            confirmation_id=confirmation_id,
            ui_contract_id="UI-ACCOUNT-ALIAS-CONFIRMATION",
            content="계좌 별칭 변경 내용을 확인하고 승인해 주세요.",
            payload=_confirmation_payload(data.get("confirmation_view")),
        )
        resumed = _resume_data(state, dependencies.interaction_runtime, event)
        outcome = resumed.get("approval_outcome")
        if outcome == "approved":
            return {
                "current_step_id": "request_account_alias_approval",
                "route_key": "approved",
                "data": _resume_update(resumed),
            }
        if outcome == "change_requested":
            target = resumed.get("change_target")
            if target not in _RESET_STEP_BY_TARGET:
                return _tool_error_update(
                    "request_account_alias_approval",
                    ValueError("수정 대상이 허용 목록과 일치하지 않습니다."),
                )
            return {
                "current_step_id": "request_account_alias_approval",
                "route_key": f"change_requested:{target}",
                "data": _resume_update(resumed),
            }
        if outcome == "cancelled":
            return {
                "current_step_id": "request_account_alias_approval",
                "route_key": "cancelled",
                "status": "completed",
                "data": _resume_update(resumed),
            }
        return _tool_error_update(
            "request_account_alias_approval",
            ValueError("승인 재개 결과가 올바르지 않습니다."),
        )

    def _make_reset_node(step_id: str, *, clears: tuple[str, ...]):
        """수정 대상별 초기화 Step 공통 팩토리.

        두 초기화 Step 공통으로 승인 관련 State를 전부 지우고, 수정 대상에
        한정된 State만 추가로 지운다. correction_view는 여기서 지우지 않는다
        — start_account_alias_prepare가 이미 지운다(관리시트 확인).
        """

        common_clears = (
            "confirmation_id",
            "confirmation_view",
            "approval_outcome",
            "change_target",
            "input_request_id",
            "alias_input_outcome",
        )

        async def node(state: AgentState) -> dict[str, Any]:
            update: dict[str, Any] = {key: None for key in common_clears}
            update.update({key: None for key in clears})
            return {
                "current_step_id": step_id,
                "route_key": "always",
                "data": update,
            }

        return node

    reset_account_alias_target = _make_reset_node(
        "reset_account_alias_target",
        clears=(
            "account_hint",
            "account_resolution_outcome",
            "accounts",
            "account_id",
            "account_selection_outcome",
        ),
    )
    reset_account_alias_value = _make_reset_node(
        "reset_account_alias_value",
        clears=("alias",),
    )

    async def execute_account_alias_change(
        state: AgentState, config: RunnableConfig
    ) -> dict[str, Any]:
        data = _data(state)
        idempotency_key = f"account_alias_execute:{data.get('confirmation_id')}"
        try:
            result = await dependencies.tool_registry.invoke_by_tool(
                "execute_account_alias_change",
                _tool_call(
                    config,
                    dependencies=dependencies,
                    step_id="execute_account_alias_change",
                    arguments={"confirmation_id": data.get("confirmation_id")},
                    idempotency_key=idempotency_key,
                ),
            )
        except (AgentToolIntegrationError, ContractToolInputError) as error:
            return _tool_error_update("execute_account_alias_change", error)

        outcome = result.get("outcome")
        if outcome == "completed":
            return {
                "current_step_id": "execute_account_alias_change",
                "route_key": outcome,
                "data": {
                    "account_id": result.get("account_id"),
                    "alias": result.get("alias"),
                    "completed_at": result.get("completed_at"),
                },
            }
        if outcome == "correction_required":
            route_key = _correction_route_key(
                "correction_required", result.get("correction_view")
            )
            if route_key is None:
                return _tool_error_update(
                    "execute_account_alias_change",
                    ValueError("수정 대상이 계약과 일치하지 않습니다."),
                )
            return {
                "current_step_id": "execute_account_alias_change",
                "route_key": route_key,
                "data": {
                    "correction_view": result.get("correction_view"),
                    "confirmation_id": None,
                },
            }
        if outcome == "blocked":
            return {
                "current_step_id": "execute_account_alias_change",
                "route_key": outcome,
                "data": {"blocked_view": result.get("blocked_view")},
            }
        return _tool_error_update(
            "execute_account_alias_change",
            ValueError("Execute 응답 outcome이 계약과 일치하지 않습니다."),
        )

    async def emit_account_alias_result(
        state: AgentState, config: RunnableConfig
    ) -> dict[str, Any]:
        data = _data(state)
        view = data.get("confirmation_view") or {}
        event = dependencies.webhook_builder.component(
            chat_session_id=_config_context(config, "chat_session_id"),
            workflow_id=WORKFLOW_ID,
            step_id="emit_account_alias_result",
            ui_contract_id="UI-ACCOUNT-ALIAS-RESULT",
            ui_type="setting_result",
            content="계좌 별칭을 변경했습니다.",
            payload={
                "purpose": "account_alias",
                "outcome": "completed",
                "account": view.get("account")
                or {"account_id": data.get("account_id")},
                "alias": data.get("alias"),
                "completed_at": data.get("completed_at"),
            },
        )
        await _publish(dependencies, event, config)
        return _terminal_update("emit_account_alias_result")

    async def emit_account_alias_error(
        state: AgentState, config: RunnableConfig
    ) -> dict[str, Any]:
        message = str(
            _data(state).get("safe_error_message")
            or "설정을 변경하지 못했습니다. 잠시 후 다시 시도해 주세요."
        )
        event = dependencies.webhook_builder.error(
            chat_session_id=_config_context(config, "chat_session_id"),
            workflow_id=WORKFLOW_ID,
            step_id="emit_account_alias_error",
            ui_contract_id="UI-COMMON-ERROR",
            content=message,
            payload={"message": message},
        )
        await _publish(dependencies, event, config)
        return _terminal_update("emit_account_alias_error", status="workflow_failed")

    graph = StateGraph(AgentState)
    graph.add_node("extract_account_alias_slots", extract_account_alias_slots)
    graph.add_node("resolve_account_alias_target", resolve_account_alias_target)
    graph.add_node("request_account_alias_selection", request_account_alias_selection)
    graph.add_node(
        "emit_account_alias_selection_empty", emit_account_alias_selection_empty
    )
    graph.add_node("check_account_alias_value", check_account_alias_value)
    graph.add_node("request_account_alias_input", request_account_alias_input)
    graph.add_node("start_account_alias_prepare", start_account_alias_prepare)
    graph.add_node("prepare_account_alias_change", prepare_account_alias_change)
    graph.add_node("emit_account_alias_unchanged", emit_account_alias_unchanged)
    graph.add_node("emit_account_alias_blocked", emit_account_alias_blocked)
    graph.add_node("request_account_alias_approval", request_account_alias_approval)
    graph.add_node("reset_account_alias_target", reset_account_alias_target)
    graph.add_node("reset_account_alias_value", reset_account_alias_value)
    graph.add_node("execute_account_alias_change", execute_account_alias_change)
    graph.add_node("emit_account_alias_result", emit_account_alias_result)
    graph.add_node("emit_account_alias_error", emit_account_alias_error)

    graph.set_entry_point("extract_account_alias_slots")
    graph.add_edge("extract_account_alias_slots", "resolve_account_alias_target")

    graph.add_conditional_edges(
        "resolve_account_alias_target",
        _route_key,
        {
            "resolved": "check_account_alias_value",
            "selection_required": "request_account_alias_selection",
            "no_accounts": "emit_account_alias_selection_empty",
            "error": "emit_account_alias_error",
        },
    )
    graph.add_conditional_edges(
        "request_account_alias_selection",
        _route_key,
        {
            "selected": "check_account_alias_value",
            "cancelled": END,
            "error": "emit_account_alias_error",
        },
    )
    graph.add_edge("emit_account_alias_selection_empty", END)

    graph.add_conditional_edges(
        "check_account_alias_value",
        _route_key,
        {
            "present": "start_account_alias_prepare",
            "missing": "request_account_alias_input",
        },
    )
    graph.add_conditional_edges(
        "request_account_alias_input",
        _route_key,
        {
            "submitted": "start_account_alias_prepare",
            "cancelled": END,
            "error": "emit_account_alias_error",
        },
    )
    graph.add_edge("start_account_alias_prepare", "prepare_account_alias_change")

    graph.add_conditional_edges(
        "prepare_account_alias_change",
        _route_key,
        {
            "ready_for_confirmation": "request_account_alias_approval",
            "unchanged": "emit_account_alias_unchanged",
            "correction_required:account": "reset_account_alias_target",
            "correction_required:alias": "reset_account_alias_value",
            "blocked": "emit_account_alias_blocked",
            "error": "emit_account_alias_error",
        },
    )
    graph.add_edge("emit_account_alias_unchanged", END)
    graph.add_edge("emit_account_alias_blocked", END)

    graph.add_conditional_edges(
        "request_account_alias_approval",
        _route_key,
        {
            "approved": "execute_account_alias_change",
            "change_requested:account": "reset_account_alias_target",
            "change_requested:alias": "reset_account_alias_value",
            "cancelled": END,
            "error": "emit_account_alias_error",
        },
    )
    graph.add_edge("reset_account_alias_target", "resolve_account_alias_target")
    graph.add_edge("reset_account_alias_value", "request_account_alias_input")

    graph.add_conditional_edges(
        "execute_account_alias_change",
        _route_key,
        {
            "completed": "emit_account_alias_result",
            "correction_required:account": "reset_account_alias_target",
            "correction_required:alias": "reset_account_alias_value",
            "blocked": "emit_account_alias_blocked",
            "error": "emit_account_alias_error",
        },
    )
    graph.add_edge("emit_account_alias_result", END)
    graph.add_edge("emit_account_alias_error", END)

    return graph.compile(checkpointer=checkpointer)


def _confirmation_payload(raw_view: Any) -> dict[str, Any]:
    view = raw_view if isinstance(raw_view, Mapping) else {}
    return {
        "account": view.get("account"),
        "alias": view.get("alias"),
        "expires_at": view.get("expires_at"),
        "actions": ["approve", "modify_account", "modify_alias", "cancel"],
    }
