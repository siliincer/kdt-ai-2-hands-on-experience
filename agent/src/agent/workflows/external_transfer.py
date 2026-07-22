"""관리시트 계약 기반 타인송금(wf_external_transfer) Workflow.

`wf_internal_transfer`와 구조가 거의 같다(계좌 확정→금액 확인→Prepare→승인→
인증→실행). 다른 부분은 딱 하나 — 맨 앞에 수취인을 확정하는 절차가
붙는다(`resolve_recipient_hint`/`request_recipient_selection`). Agent Route
매핑은 agent-tools-api-spec.md §13.5·§14.8·§16.9 표를 그대로 옮긴 것이다.
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
from agent.workflows.transfer_slot_extraction import (
    TransferSlotExtractor,
    extract_external_transfer_slots_by_rule,
    extract_external_transfer_slots_llm_first,
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

WORKFLOW_ID = "wf_external_transfer"
_tool_error_update = build_tool_error_update("송금을 완료하지 못했습니다. 잠시 후 다시 시도해 주세요.")

# 승인·수정 화면의 정정 대상 3종 — route_external_transfer_correction,
# request_external_transfer_approval, request_external_transfer_correction이 공유한다.
_RESET_STEP_BY_TARGET = {
    "from_account": "reset_external_from_account",
    "recipient": "reset_external_recipient",
    "amount": "reset_external_transfer_amount",
}


def extract_external_transfer_slots_from_text(message: str) -> Mapping[str, Any]:
    """테스트와 장애 폴백용 결정적 타인송금 Slot 추출."""

    return extract_external_transfer_slots_by_rule(message)


@dataclass(frozen=True, slots=True)
class ExternalTransferDependencies:
    """타인송금 Workflow가 공유 기반에서 주입받는 외부 의존성."""

    tool_registry: ContractToolRegistry
    webhook_client: BackendWebhookClient
    interaction_runtime: InteractionPauseRuntime
    webhook_builder: InteractionWebhookBuilder
    input_request_id_factory: Callable[[], str] = field(default=_default_input_request_id)
    tool_request_id_factory: Callable[[str, str], str] = field(default=_default_tool_request_id)
    slot_extractor: TransferSlotExtractor = field(default=extract_external_transfer_slots_llm_first)


def build_external_transfer_graph(
    dependencies: ExternalTransferDependencies,
    *,
    checkpointer: Any = None,
) -> Any:
    """타인송금 Step과 Route를 관리시트 순서대로 컴파일한다."""

    async def extract_external_transfer_slots(state: AgentState) -> dict[str, Any]:
        user_input = str(state.get("user_input") or "")
        extracted = await dependencies.slot_extractor(user_input)
        recipient_name_hint = extracted.get("recipient_name_hint")
        return {
            "workflow_id": WORKFLOW_ID,
            "current_step_id": "extract_external_transfer_slots",
            "route_key": "has_recipient_hint" if recipient_name_hint else "no_recipient_hint",
            "data": {
                "recipient_name_hint": recipient_name_hint,
                "from_account_hint": extracted.get("from_account_hint"),
                "amount": extracted.get("amount"),
            },
        }

    async def resolve_recipient_hint(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        data = _data(state)
        try:
            result = await dependencies.tool_registry.invoke_by_tool(
                "resolve_recipient_hint",
                _tool_call(
                    config,
                    dependencies=dependencies,
                    step_id="resolve_recipient_hint",
                    arguments={"recipient_name_hint": data.get("recipient_name_hint")},
                ),
            )
        except (AgentToolIntegrationError, ContractToolInputError) as error:
            return _tool_error_update("resolve_recipient_hint", error)

        outcome = result.get("outcome")
        if outcome == "resolved":
            to_recipient_id = result.get("to_recipient_id")
            if not isinstance(to_recipient_id, str) or not to_recipient_id:
                return _tool_error_update(
                    "resolve_recipient_hint",
                    ValueError("resolved 응답에 to_recipient_id가 없습니다."),
                )
            return {
                "current_step_id": "resolve_recipient_hint",
                "route_key": "resolved",
                "data": {
                    "recipient_resolution_outcome": outcome,
                    "to_recipient_id": to_recipient_id,
                },
            }
        if outcome == "selection_required":
            return {
                "current_step_id": "resolve_recipient_hint",
                "route_key": "selection_required",
                "data": {
                    "recipient_resolution_outcome": outcome,
                    "recipient_selection_reason": result.get("selection_reason"),
                },
            }
        return _tool_error_update(
            "resolve_recipient_hint",
            ValueError("수취인 확정 결과가 계약과 일치하지 않습니다."),
        )

    async def request_recipient_selection(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        data = _data(state)
        input_request_id = dependencies.input_request_id_factory()
        reason = data.get("recipient_selection_reason") or "no_match"
        ui_state = "name_candidates" if reason == "multiple_matches" else "initial"
        payload: dict[str, Any] = {
            "state": ui_state,
            "title": "받는 분을 선택해 주세요.",
            "recipient_selection_reason": reason,
            "actions": ["select", "manual_input", "cancel"],
        }
        if data.get("recipient_name_hint"):
            payload["recipient_name_hint"] = data["recipient_name_hint"]
        event = dependencies.webhook_builder.need_input(
            chat_session_id=_config_context(config, "chat_session_id"),
            workflow_id=WORKFLOW_ID,
            step_id="request_recipient_selection",
            input_request_id=input_request_id,
            ui_contract_id="UI-RECIPIENT-SELECT",
            ui_type="recipient_select",
            content="받는 분을 선택해 주세요.",
            payload=payload,
        )
        resumed = _resume_data(state, dependencies.interaction_runtime, event)
        outcome = resumed.get("recipient_selection_outcome")
        if outcome == "selected":
            to_recipient_id = resumed.get("to_recipient_id")
            to_recipient_candidate_id = resumed.get("to_recipient_candidate_id")
            references = [to_recipient_id, to_recipient_candidate_id]
            if sum(ref is not None for ref in references) != 1:
                return _tool_error_update(
                    "request_recipient_selection",
                    ValueError("selected 응답의 수취인 참조가 정확히 하나가 아닙니다."),
                )
            return {
                "current_step_id": "request_recipient_selection",
                "route_key": "selected",
                "data": _resume_update(resumed, input_request_id=None),
            }
        if outcome == "cancelled":
            return {
                "current_step_id": "request_recipient_selection",
                "route_key": "cancelled",
                "status": "completed",
                "data": _resume_update(resumed, input_request_id=None),
            }
        return _tool_error_update(
            "request_recipient_selection",
            ValueError("수취인 선택 재개 결과가 올바르지 않습니다."),
        )

    async def resolve_external_from_account(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        data = _data(state)
        try:
            result = await dependencies.tool_registry.invoke_by_tool(
                "fetch_accounts",
                _tool_call(
                    config,
                    dependencies=dependencies,
                    step_id="resolve_external_from_account",
                    arguments={
                        "account_hint": data.get("from_account_hint"),
                        "account_capability": "withdraw",
                        "resolve_selection": True,
                    },
                ),
            )
        except (AgentToolIntegrationError, ContractToolInputError) as error:
            return _tool_error_update("resolve_external_from_account", error)

        outcome = result.get("account_resolution_outcome")
        if outcome not in {"resolved", "selection_required", "no_accounts"}:
            return _tool_error_update(
                "resolve_external_from_account",
                ValueError("출금 계좌 확인 결과가 올바르지 않습니다."),
            )
        account_ids = list(result.get("account_ids") or [])
        update: dict[str, Any] = {
            "account_resolution_outcome": outcome,
            "accounts": list(result.get("accounts") or []),
        }
        if outcome == "resolved":
            if len(account_ids) != 1:
                return _tool_error_update(
                    "resolve_external_from_account",
                    ValueError("resolved 응답의 계좌가 정확히 하나가 아닙니다."),
                )
            update["from_account_id"] = account_ids[0]
        elif outcome == "selection_required":
            update["input_request_id"] = dependencies.input_request_id_factory()
        return {
            "current_step_id": "resolve_external_from_account",
            "route_key": outcome,
            "data": update,
        }

    async def request_external_from_account_selection(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        data = _data(state)
        input_request_id = data.get("input_request_id")
        if not isinstance(input_request_id, str) or not input_request_id:
            return _tool_error_update(
                "request_external_from_account_selection",
                ValueError("입력 요청 ID가 없습니다."),
            )
        event = dependencies.webhook_builder.need_input(
            chat_session_id=_config_context(config, "chat_session_id"),
            workflow_id=WORKFLOW_ID,
            step_id="request_external_from_account_selection",
            input_request_id=input_request_id,
            ui_contract_id="UI-EXTERNAL-TRANSFER-FROM-ACCOUNT",
            ui_type="account_card_list",
            content="출금할 계좌를 선택해 주세요.",
            payload={
                "title": "출금할 계좌를 선택해 주세요.",
                "accounts": _account_options(data.get("accounts")),
                "actions": ["select", "cancel"],
            },
        )
        # ResumeStateMapper가 resume.value.account_ids[0]을 from_account_id로
        # 이미 추출해서 넣어준다 — 배열을 다시 받아 검증하지 않는다.
        resumed = _resume_data(state, dependencies.interaction_runtime, event)
        outcome = resumed.get("account_selection_outcome")
        if outcome == "selected":
            from_account_id = resumed.get("from_account_id")
            if not isinstance(from_account_id, str) or not from_account_id:
                return _tool_error_update(
                    "request_external_from_account_selection",
                    ValueError("selected 응답에 from_account_id가 없습니다."),
                )
            return {
                "current_step_id": "request_external_from_account_selection",
                "route_key": "selected",
                "data": _resume_update(resumed, input_request_id=None),
            }
        if outcome == "cancelled":
            return {
                "current_step_id": "request_external_from_account_selection",
                "route_key": "cancelled",
                "status": "completed",
                "data": _resume_update(resumed, input_request_id=None),
            }
        return _tool_error_update(
            "request_external_from_account_selection",
            ValueError("계좌 선택 재개 결과가 올바르지 않습니다."),
        )

    async def emit_external_from_accounts_empty(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        event = dependencies.webhook_builder.component(
            chat_session_id=_config_context(config, "chat_session_id"),
            workflow_id=WORKFLOW_ID,
            step_id="emit_external_from_accounts_empty",
            ui_contract_id="UI-EXTERNAL-TRANSFER-FROM-ACCOUNT",
            ui_type="account_card_list",
            content="출금 가능한 계좌가 없습니다.",
            payload={
                "title": "출금 가능한 계좌가 없습니다.",
                "accounts": [],
                "actions": [],
            },
        )
        await _publish(dependencies, event, config)
        return _terminal_update("emit_external_from_accounts_empty")

    async def check_external_transfer_amount(state: AgentState) -> dict[str, Any]:
        amount = _data(state).get("amount")
        valid = isinstance(amount, int) and not isinstance(amount, bool) and amount > 0
        return {
            "current_step_id": "check_external_transfer_amount",
            "route_key": "valid" if valid else "invalid",
        }

    async def request_external_transfer_amount(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        input_request_id = dependencies.input_request_id_factory()
        event = dependencies.webhook_builder.need_input(
            chat_session_id=_config_context(config, "chat_session_id"),
            workflow_id=WORKFLOW_ID,
            step_id="request_external_transfer_amount",
            input_request_id=input_request_id,
            ui_contract_id="UI-TRANSFER-AMOUNT-INPUT",
            ui_type="number_input",
            content="송금할 금액을 입력해 주세요.",
            payload={
                "title": "송금할 금액을 입력해 주세요.",
                "actions": ["submit", "cancel"],
            },
        )
        resumed = _resume_data(state, dependencies.interaction_runtime, event)
        outcome = resumed.get("amount_input_outcome")
        if outcome == "submitted":
            amount = resumed.get("amount")
            if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0:
                return _tool_error_update(
                    "request_external_transfer_amount",
                    ValueError("제출된 금액이 계약과 일치하지 않습니다."),
                )
            return {
                "current_step_id": "request_external_transfer_amount",
                "route_key": "submitted",
                "data": _resume_update(resumed, input_request_id=None),
            }
        if outcome == "cancelled":
            return {
                "current_step_id": "request_external_transfer_amount",
                "route_key": "cancelled",
                "status": "completed",
                "data": _resume_update(resumed, input_request_id=None),
            }
        return _tool_error_update(
            "request_external_transfer_amount",
            ValueError("금액 입력 재개 결과가 올바르지 않습니다."),
        )

    async def start_external_transfer_prepare(state: AgentState) -> dict[str, Any]:
        attempt = int(_data(state).get("prepare_attempt") or 0) + 1
        return {
            "current_step_id": "start_external_transfer_prepare",
            "route_key": "always",
            "data": {"prepare_attempt": attempt},
        }

    async def prepare_external_transfer(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        data = _data(state)
        idempotency_key = (
            f"external_transfer_prepare:{_config_context(config, 'execution_context_id')}:{data.get('prepare_attempt')}"
        )
        arguments: dict[str, Any] = {
            "from_account_id": data.get("from_account_id"),
            "amount": data.get("amount"),
            "currency": data.get("currency") or "KRW",
        }
        if data.get("to_recipient_id"):
            arguments["to_recipient_id"] = data["to_recipient_id"]
        else:
            arguments["to_recipient_candidate_id"] = data.get("to_recipient_candidate_id")
        try:
            result = await dependencies.tool_registry.invoke_by_tool(
                "prepare_external_transfer",
                _tool_call(
                    config,
                    dependencies=dependencies,
                    step_id="prepare_external_transfer",
                    arguments=arguments,
                    idempotency_key=idempotency_key,
                ),
            )
        except (AgentToolIntegrationError, ContractToolInputError) as error:
            return _tool_error_update("prepare_external_transfer", error)

        outcome = result.get("outcome")
        update: dict[str, Any] = {}
        if outcome == "ready_for_confirmation":
            update["confirmation_id"] = result.get("confirmation_id")
            update["confirmation_view"] = result.get("confirmation_view")
        elif outcome == "correction_required":
            update["correction_view"] = result.get("correction_view")
        elif outcome == "blocked":
            update["blocked_view"] = result.get("blocked_view")
        else:
            return _tool_error_update(
                "prepare_external_transfer",
                ValueError("Prepare 응답 outcome이 계약과 일치하지 않습니다."),
            )
        return {
            "current_step_id": "prepare_external_transfer",
            "route_key": outcome,
            "data": update,
        }

    async def request_external_transfer_approval(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        data = _data(state)
        confirmation_id = data.get("confirmation_id")
        if not isinstance(confirmation_id, str) or not confirmation_id:
            return _tool_error_update(
                "request_external_transfer_approval",
                ValueError("Confirmation ID가 없습니다."),
            )
        event = dependencies.webhook_builder.need_approval(
            chat_session_id=_config_context(config, "chat_session_id"),
            workflow_id=WORKFLOW_ID,
            step_id="request_external_transfer_approval",
            confirmation_id=confirmation_id,
            ui_contract_id="UI-EXTERNAL-TRANSFER-CONFIRMATION",
            content="송금 내용을 확인하고 승인해 주세요.",
            payload=_confirmation_payload(data.get("confirmation_view")),
        )
        resumed = _resume_data(state, dependencies.interaction_runtime, event)
        outcome = resumed.get("approval_outcome")
        if outcome == "approved":
            return {
                "current_step_id": "request_external_transfer_approval",
                "route_key": "approved",
                "data": _resume_update(resumed),
            }
        if outcome == "change_requested":
            target = resumed.get("change_target")
            if target not in _RESET_STEP_BY_TARGET:
                return _tool_error_update(
                    "request_external_transfer_approval",
                    ValueError("수정 대상이 허용 목록과 일치하지 않습니다."),
                )
            return {
                "current_step_id": "request_external_transfer_approval",
                "route_key": f"change_requested:{target}",
                "data": _resume_update(resumed),
            }
        if outcome == "cancelled":
            return {
                "current_step_id": "request_external_transfer_approval",
                "route_key": "cancelled",
                "status": "completed",
                "data": _resume_update(resumed),
            }
        return _tool_error_update(
            "request_external_transfer_approval",
            ValueError("승인 재개 결과가 올바르지 않습니다."),
        )

    def _make_reset_node(step_id: str, *, clears: tuple[str, ...]):
        """수정 대상별 초기화 Step 공통 팩토리 (roadmap §2691 표 그대로)."""

        common_clears = (
            "confirmation_id",
            "confirmation_view",
            "approval_outcome",
            "change_target",
            "correction_view",
            "correction_selection_outcome",
            "blocked_view",
            "auth_context_id",
            "auth_request_view",
            "auth_status",
            "auth_retry_outcome",
            "input_request_id",
        )

        async def node(state: AgentState) -> dict[str, Any]:
            update: dict[str, Any] = {key: None for key in common_clears}
            update.update({key: None for key in clears})
            update["auth_attempt"] = 0
            return {
                "current_step_id": step_id,
                "route_key": "always",
                "data": update,
            }

        return node

    reset_external_from_account = _make_reset_node(
        "reset_external_from_account",
        clears=(
            "from_account_hint",
            "from_account_id",
            "account_resolution_outcome",
            "accounts",
            "account_selection_outcome",
        ),
    )
    # 수취인 수정은 항상 request_recipient_selection(초기 화면)으로 간다 — 같은
    # 이름 힌트로는 자동 재확정만 반복되므로 resolve_recipient_hint로 되돌아가지
    # 않는다(roadmap §2691 그대로).
    reset_external_recipient = _make_reset_node(
        "reset_external_recipient",
        clears=(
            "recipient_name_hint",
            "recipient_resolution_outcome",
            "recipient_selection_reason",
            "recipient_selection_outcome",
            "to_recipient_id",
            "to_recipient_candidate_id",
        ),
    )
    reset_external_transfer_amount = _make_reset_node(
        "reset_external_transfer_amount",
        clears=("amount", "amount_input_outcome"),
    )

    async def route_external_transfer_correction(state: AgentState) -> dict[str, Any]:
        view = _data(state).get("correction_view") or {}
        targets = list(view.get("allowed_change_targets") or [])
        valid_targets = [t for t in targets if t in _RESET_STEP_BY_TARGET]
        if not valid_targets or len(valid_targets) != len(targets):
            return {
                "current_step_id": "route_external_transfer_correction",
                "route_key": "invalid",
            }
        if len(valid_targets) == 1:
            return {
                "current_step_id": "route_external_transfer_correction",
                "route_key": f"single:{valid_targets[0]}",
            }
        return {
            "current_step_id": "route_external_transfer_correction",
            "route_key": "multiple",
        }

    async def request_external_transfer_correction(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        data = _data(state)
        input_request_id = dependencies.input_request_id_factory()
        view = data.get("correction_view") or {}
        targets = list(view.get("allowed_change_targets") or [])
        event = dependencies.webhook_builder.need_input(
            chat_session_id=_config_context(config, "chat_session_id"),
            workflow_id=WORKFLOW_ID,
            step_id="request_external_transfer_correction",
            input_request_id=input_request_id,
            ui_contract_id="UI-EXTERNAL-TRANSFER-CORRECTION",
            ui_type="option_select",
            content="무엇을 수정할지 선택해 주세요.",
            payload={
                "title": view.get("title") or "수정할 항목을 선택해 주세요.",
                "options": targets,
            },
        )
        resumed = _resume_data(state, dependencies.interaction_runtime, event)
        outcome = resumed.get("correction_selection_outcome")
        if outcome == "selected":
            target = resumed.get("change_target")
            if target not in _RESET_STEP_BY_TARGET or target not in targets:
                return _tool_error_update(
                    "request_external_transfer_correction",
                    ValueError("선택 결과가 허용 목록과 일치하지 않습니다."),
                )
            return {
                "current_step_id": "request_external_transfer_correction",
                "route_key": f"selected:{target}",
                "data": _resume_update(resumed),
            }
        if outcome == "cancelled":
            return {
                "current_step_id": "request_external_transfer_correction",
                "route_key": "cancelled",
                "status": "completed",
                "data": _resume_update(resumed),
            }
        return _tool_error_update(
            "request_external_transfer_correction",
            ValueError("수정 대상 선택 재개 결과가 올바르지 않습니다."),
        )

    async def start_external_auth(state: AgentState) -> dict[str, Any]:
        attempt = int(_data(state).get("auth_attempt") or 0) + 1
        return {
            "current_step_id": "start_external_auth",
            "route_key": "always",
            "data": {
                "auth_context_id": None,
                "auth_request_view": None,
                "auth_status": None,
                "auth_retry_outcome": None,
                "auth_attempt": attempt,
            },
        }

    async def create_external_auth_context(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        data = _data(state)
        idempotency_key = f"external_transfer_auth:{data.get('confirmation_id')}:{data.get('auth_attempt')}"
        try:
            result = await dependencies.tool_registry.invoke_by_tool(
                "create_auth_context",
                _tool_call(
                    config,
                    dependencies=dependencies,
                    step_id="create_external_auth_context",
                    arguments={"confirmation_id": data.get("confirmation_id")},
                    idempotency_key=idempotency_key,
                ),
            )
        except (AgentToolIntegrationError, ContractToolInputError) as error:
            return _tool_error_update("create_external_auth_context", error)

        outcome = result.get("outcome")
        if outcome == "authentication_required":
            return {
                "current_step_id": "create_external_auth_context",
                "route_key": outcome,
                "data": {
                    "auth_context_id": result.get("auth_context_id"),
                    "auth_request_view": result.get("auth_request_view"),
                },
            }
        if outcome == "blocked":
            return {
                "current_step_id": "create_external_auth_context",
                "route_key": outcome,
                "data": {"blocked_view": result.get("blocked_view")},
            }
        return _tool_error_update(
            "create_external_auth_context",
            ValueError("Auth Context 응답 outcome이 계약과 일치하지 않습니다."),
        )

    async def request_external_authentication(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        data = _data(state)
        auth_context_id = data.get("auth_context_id")
        if not isinstance(auth_context_id, str) or not auth_context_id:
            return _tool_error_update(
                "request_external_authentication",
                ValueError("Auth Context ID가 없습니다."),
            )
        view = data.get("auth_request_view") or {}
        event = dependencies.webhook_builder.authentication_required(
            chat_session_id=_config_context(config, "chat_session_id"),
            workflow_id=WORKFLOW_ID,
            step_id="request_external_authentication",
            auth_context_id=auth_context_id,
            ui_contract_id="UI-EXTERNAL-TRANSFER-AUTH",
            content=str(view.get("title") or "추가 인증이 필요합니다."),
            payload=dict(view),
        )
        resumed = _resume_data(state, dependencies.interaction_runtime, event)
        status = resumed.get("auth_status")
        if status == "verified":
            return {
                "current_step_id": "request_external_authentication",
                "route_key": "verified",
                "data": _resume_update(resumed),
            }
        if status in {"failed", "expired"}:
            return {
                "current_step_id": "request_external_authentication",
                "route_key": "retriable",
                "data": _resume_update(resumed),
            }
        if status == "cancelled":
            return {
                "current_step_id": "request_external_authentication",
                "route_key": "cancelled",
                "status": "completed",
                "data": _resume_update(resumed),
            }
        return _tool_error_update(
            "request_external_authentication",
            ValueError("인증 재개 결과가 올바르지 않습니다."),
        )

    async def request_external_auth_retry(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        input_request_id = dependencies.input_request_id_factory()
        event = dependencies.webhook_builder.need_input(
            chat_session_id=_config_context(config, "chat_session_id"),
            workflow_id=WORKFLOW_ID,
            step_id="request_external_auth_retry",
            input_request_id=input_request_id,
            ui_contract_id="UI-EXTERNAL-TRANSFER-AUTH-RETRY",
            ui_type="option_select",
            content="인증에 실패했습니다. 다시 시도하시겠어요?",
            payload={
                "title": "인증을 다시 시도하시겠어요?",
                "options": ["retry", "cancel"],
            },
        )
        resumed = _resume_data(state, dependencies.interaction_runtime, event)
        outcome = resumed.get("auth_retry_outcome")
        if outcome == "retry":
            return {
                "current_step_id": "request_external_auth_retry",
                "route_key": "retry",
                "data": _resume_update(resumed, input_request_id=None),
            }
        if outcome == "cancelled":
            return {
                "current_step_id": "request_external_auth_retry",
                "route_key": "cancelled",
                "status": "completed",
                "data": _resume_update(resumed, input_request_id=None),
            }
        return _tool_error_update(
            "request_external_auth_retry",
            ValueError("재인증 선택 재개 결과가 올바르지 않습니다."),
        )

    async def execute_external_transfer(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        data = _data(state)
        idempotency_key = f"external_transfer_execute:{data.get('confirmation_id')}:{data.get('auth_attempt')}"
        try:
            result = await dependencies.tool_registry.invoke_by_tool(
                "execute_external_transfer",
                _tool_call(
                    config,
                    dependencies=dependencies,
                    step_id="execute_external_transfer",
                    arguments={
                        "confirmation_id": data.get("confirmation_id"),
                        "auth_context_id": data.get("auth_context_id"),
                    },
                    idempotency_key=idempotency_key,
                ),
            )
        except (AgentToolIntegrationError, ContractToolInputError) as error:
            return _tool_error_update("execute_external_transfer", error)

        outcome = result.get("outcome")
        if outcome == "completed":
            return {
                "current_step_id": "execute_external_transfer",
                "route_key": outcome,
                "data": {
                    "transaction_id": result.get("transaction_id"),
                    "completed_at": result.get("completed_at"),
                },
            }
        if outcome == "correction_required":
            return {
                "current_step_id": "execute_external_transfer",
                "route_key": outcome,
                "data": {
                    "correction_view": result.get("correction_view"),
                    "confirmation_id": None,
                    "auth_context_id": None,
                },
            }
        if outcome == "reauthentication_required":
            return {
                "current_step_id": "execute_external_transfer",
                "route_key": outcome,
                "data": {
                    "auth_context_id": None,
                    "auth_request_view": None,
                    "auth_status": None,
                    "auth_retry_outcome": None,
                },
            }
        if outcome == "blocked":
            return {
                "current_step_id": "execute_external_transfer",
                "route_key": outcome,
                "data": {"blocked_view": result.get("blocked_view")},
            }
        return _tool_error_update(
            "execute_external_transfer",
            ValueError("Execute 응답 outcome이 계약과 일치하지 않습니다."),
        )

    async def emit_external_transfer_result(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        data = _data(state)
        view = data.get("confirmation_view") or {}
        event = dependencies.webhook_builder.component(
            chat_session_id=_config_context(config, "chat_session_id"),
            workflow_id=WORKFLOW_ID,
            step_id="emit_external_transfer_result",
            ui_contract_id="UI-EXTERNAL-TRANSFER-RESULT",
            ui_type="transfer_result",
            content="송금이 완료되었습니다.",
            payload={
                "transaction_id": data.get("transaction_id"),
                "completed_at": data.get("completed_at"),
                "from_account": view.get("from_account"),
                "recipient": view.get("recipient"),
                "amount": view.get("amount"),
                "currency": view.get("currency"),
            },
        )
        await _publish(dependencies, event, config)
        return _terminal_update("emit_external_transfer_result")

    async def emit_external_transfer_blocked(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        view = _data(state).get("blocked_view") or {}
        event = dependencies.webhook_builder.blocked(
            chat_session_id=_config_context(config, "chat_session_id"),
            workflow_id=WORKFLOW_ID,
            step_id="emit_external_transfer_blocked",
            ui_contract_id="UI-TRANSFER-BLOCKED",
            content=str(view.get("title") or "송금을 진행할 수 없습니다."),
            payload=dict(view),
        )
        await _publish(dependencies, event, config)
        return _terminal_update("emit_external_transfer_blocked", status="workflow_failed")

    async def emit_external_transfer_error(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        message = str(
            _data(state).get("safe_error_message") or "송금을 완료하지 못했습니다. 잠시 후 다시 시도해 주세요."
        )
        event = dependencies.webhook_builder.error(
            chat_session_id=_config_context(config, "chat_session_id"),
            workflow_id=WORKFLOW_ID,
            step_id="emit_external_transfer_error",
            ui_contract_id="UI-COMMON-ERROR",
            content=message,
            payload={"message": message},
        )
        await _publish(dependencies, event, config)
        return _terminal_update("emit_external_transfer_error", status="workflow_failed")

    graph = StateGraph(AgentState)
    graph.add_node("extract_external_transfer_slots", extract_external_transfer_slots)
    graph.add_node("resolve_recipient_hint", resolve_recipient_hint)
    graph.add_node("request_recipient_selection", request_recipient_selection)
    graph.add_node("resolve_external_from_account", resolve_external_from_account)
    graph.add_node(
        "request_external_from_account_selection",
        request_external_from_account_selection,
    )
    graph.add_node("emit_external_from_accounts_empty", emit_external_from_accounts_empty)
    graph.add_node("check_external_transfer_amount", check_external_transfer_amount)
    graph.add_node("request_external_transfer_amount", request_external_transfer_amount)
    graph.add_node("start_external_transfer_prepare", start_external_transfer_prepare)
    graph.add_node("prepare_external_transfer", prepare_external_transfer)
    graph.add_node("request_external_transfer_approval", request_external_transfer_approval)
    graph.add_node("reset_external_from_account", reset_external_from_account)
    graph.add_node("reset_external_recipient", reset_external_recipient)
    graph.add_node("reset_external_transfer_amount", reset_external_transfer_amount)
    graph.add_node("route_external_transfer_correction", route_external_transfer_correction)
    graph.add_node("request_external_transfer_correction", request_external_transfer_correction)
    graph.add_node("start_external_auth", start_external_auth)
    graph.add_node("create_external_auth_context", create_external_auth_context)
    graph.add_node("request_external_authentication", request_external_authentication)
    graph.add_node("request_external_auth_retry", request_external_auth_retry)
    graph.add_node("execute_external_transfer", execute_external_transfer)
    graph.add_node("emit_external_transfer_result", emit_external_transfer_result)
    graph.add_node("emit_external_transfer_blocked", emit_external_transfer_blocked)
    graph.add_node("emit_external_transfer_error", emit_external_transfer_error)

    graph.set_entry_point("extract_external_transfer_slots")
    graph.add_conditional_edges(
        "extract_external_transfer_slots",
        _route_key,
        {
            "has_recipient_hint": "resolve_recipient_hint",
            "no_recipient_hint": "request_recipient_selection",
        },
    )
    graph.add_conditional_edges(
        "resolve_recipient_hint",
        _route_key,
        {
            "resolved": "resolve_external_from_account",
            "selection_required": "request_recipient_selection",
            "error": "emit_external_transfer_error",
        },
    )
    graph.add_conditional_edges(
        "request_recipient_selection",
        _route_key,
        {
            "selected": "resolve_external_from_account",
            "cancelled": END,
            "error": "emit_external_transfer_error",
        },
    )

    graph.add_conditional_edges(
        "resolve_external_from_account",
        _route_key,
        {
            "resolved": "check_external_transfer_amount",
            "selection_required": "request_external_from_account_selection",
            "no_accounts": "emit_external_from_accounts_empty",
            "error": "emit_external_transfer_error",
        },
    )
    graph.add_conditional_edges(
        "request_external_from_account_selection",
        _route_key,
        {
            "selected": "check_external_transfer_amount",
            "cancelled": END,
            "error": "emit_external_transfer_error",
        },
    )
    graph.add_edge("emit_external_from_accounts_empty", END)

    graph.add_conditional_edges(
        "check_external_transfer_amount",
        _route_key,
        {
            "valid": "start_external_transfer_prepare",
            "invalid": "request_external_transfer_amount",
        },
    )
    graph.add_conditional_edges(
        "request_external_transfer_amount",
        _route_key,
        {
            "submitted": "start_external_transfer_prepare",
            "cancelled": END,
            "error": "emit_external_transfer_error",
        },
    )
    graph.add_edge("start_external_transfer_prepare", "prepare_external_transfer")

    graph.add_conditional_edges(
        "prepare_external_transfer",
        _route_key,
        {
            "ready_for_confirmation": "request_external_transfer_approval",
            "correction_required": "route_external_transfer_correction",
            "blocked": "emit_external_transfer_blocked",
            "error": "emit_external_transfer_error",
        },
    )
    graph.add_conditional_edges(
        "request_external_transfer_approval",
        _route_key,
        {
            "approved": "start_external_auth",
            "change_requested:from_account": "reset_external_from_account",
            "change_requested:recipient": "reset_external_recipient",
            "change_requested:amount": "reset_external_transfer_amount",
            "cancelled": END,
            "error": "emit_external_transfer_error",
        },
    )
    graph.add_edge("reset_external_from_account", "resolve_external_from_account")
    graph.add_edge("reset_external_recipient", "request_recipient_selection")
    graph.add_edge("reset_external_transfer_amount", "request_external_transfer_amount")

    graph.add_conditional_edges(
        "route_external_transfer_correction",
        _route_key,
        {
            "single:from_account": "reset_external_from_account",
            "single:recipient": "reset_external_recipient",
            "single:amount": "reset_external_transfer_amount",
            "multiple": "request_external_transfer_correction",
            "invalid": "emit_external_transfer_error",
        },
    )
    graph.add_conditional_edges(
        "request_external_transfer_correction",
        _route_key,
        {
            "selected:from_account": "reset_external_from_account",
            "selected:recipient": "reset_external_recipient",
            "selected:amount": "reset_external_transfer_amount",
            "cancelled": END,
            "error": "emit_external_transfer_error",
        },
    )

    graph.add_edge("start_external_auth", "create_external_auth_context")
    graph.add_conditional_edges(
        "create_external_auth_context",
        _route_key,
        {
            "authentication_required": "request_external_authentication",
            "blocked": "emit_external_transfer_blocked",
            "error": "emit_external_transfer_error",
        },
    )
    graph.add_conditional_edges(
        "request_external_authentication",
        _route_key,
        {
            "verified": "execute_external_transfer",
            "retriable": "request_external_auth_retry",
            "cancelled": END,
            "error": "emit_external_transfer_error",
        },
    )
    graph.add_conditional_edges(
        "request_external_auth_retry",
        _route_key,
        {
            "retry": "start_external_auth",
            "cancelled": END,
            "error": "emit_external_transfer_error",
        },
    )

    graph.add_conditional_edges(
        "execute_external_transfer",
        _route_key,
        {
            "completed": "emit_external_transfer_result",
            "correction_required": "route_external_transfer_correction",
            "reauthentication_required": "start_external_auth",
            "blocked": "emit_external_transfer_blocked",
            "error": "emit_external_transfer_error",
        },
    )
    graph.add_edge("emit_external_transfer_result", END)
    graph.add_edge("emit_external_transfer_blocked", END)
    graph.add_edge("emit_external_transfer_error", END)

    return graph.compile(checkpointer=checkpointer)


def _confirmation_payload(raw_view: Any) -> dict[str, Any]:
    view = raw_view if isinstance(raw_view, Mapping) else {}
    return {
        "from_account": view.get("from_account"),
        "recipient": view.get("recipient"),
        "amount": view.get("amount"),
        "fee": view.get("fee"),
        "total_debit": view.get("total_debit"),
        "currency": view.get("currency"),
        "variant": view.get("variant"),
        "warning_codes": view.get("warning_codes"),
        "expires_at": view.get("expires_at"),
        "actions": [
            "approve",
            "modify_from_account",
            "modify_recipient",
            "modify_amount",
            "cancel",
        ],
    }
