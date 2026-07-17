"""관리시트 계약과 일치하는 HITL Webhook 이벤트를 생성한다."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from agent.contracts.backend import (
    AgentWebhookRequest,
    ApprovalUi,
    AuthenticationRequiredWebhookMetadata,
    AuthenticationUi,
    InputUiType,
    NeedApprovalWebhookMetadata,
    NeedInputUi,
    NeedInputWebhookMetadata,
)
from agent.workflow_contracts import WorkflowContractStore


class WebhookEventContractError(ValueError):
    """Webhook 요청이 관리시트의 Workflow·UI 계약과 다른 경우."""


class InteractionWebhookBuilder:
    """입력·승인·인증 대기 Webhook을 공통 규칙으로 생성한다."""

    def __init__(self, contract_store: WorkflowContractStore) -> None:
        self._contract_store = contract_store

    def need_input(
        self,
        *,
        chat_session_id: str,
        workflow_id: str,
        step_id: str,
        input_request_id: str,
        ui_contract_id: str,
        ui_type: InputUiType,
        content: str,
        payload: Mapping[str, Any],
    ) -> AgentWebhookRequest:
        self._validate_step_contract(
            workflow_id=workflow_id,
            step_id=step_id,
            ui_contract_id=ui_contract_id,
            ui_type=ui_type,
        )
        metadata = NeedInputWebhookMetadata(
            workflow_id=workflow_id,
            step_id=step_id,
            input_request_id=input_request_id,
            ui_contract_id=ui_contract_id,
            ui=NeedInputUi(type=ui_type, payload=dict(payload)),
        )
        return AgentWebhookRequest(
            chat_session_id=chat_session_id,
            event_type="need_input",
            content=content,
            metadata=metadata.model_dump(mode="json"),
        )

    def need_approval(
        self,
        *,
        chat_session_id: str,
        workflow_id: str,
        step_id: str,
        confirmation_id: str,
        ui_contract_id: str,
        content: str,
        payload: Mapping[str, Any],
    ) -> AgentWebhookRequest:
        ui_type = "confirm_modal"
        self._validate_step_contract(
            workflow_id=workflow_id,
            step_id=step_id,
            ui_contract_id=ui_contract_id,
            ui_type=ui_type,
        )
        metadata = NeedApprovalWebhookMetadata(
            workflow_id=workflow_id,
            step_id=step_id,
            ui_contract_id=ui_contract_id,
            ui=ApprovalUi(type=ui_type, payload=dict(payload)),
        )
        return AgentWebhookRequest(
            chat_session_id=chat_session_id,
            event_type="need_approval",
            content=content,
            confirmation_id=confirmation_id,
            metadata=metadata.model_dump(mode="json"),
        )

    def authentication_required(
        self,
        *,
        chat_session_id: str,
        workflow_id: str,
        step_id: str,
        auth_context_id: str,
        ui_contract_id: str,
        content: str,
        payload: Mapping[str, Any],
    ) -> AgentWebhookRequest:
        ui_type = "auth_request"
        self._validate_step_contract(
            workflow_id=workflow_id,
            step_id=step_id,
            ui_contract_id=ui_contract_id,
            ui_type=ui_type,
        )
        metadata = AuthenticationRequiredWebhookMetadata(
            workflow_id=workflow_id,
            step_id=step_id,
            auth_context_id=auth_context_id,
            ui_contract_id=ui_contract_id,
            ui=AuthenticationUi(type=ui_type, payload=dict(payload)),
        )
        return AgentWebhookRequest(
            chat_session_id=chat_session_id,
            event_type="authentication_required",
            content=content,
            metadata=metadata.model_dump(mode="json"),
        )

    def component(
        self,
        *,
        chat_session_id: str,
        workflow_id: str,
        step_id: str,
        ui_contract_id: str,
        ui_type: str,
        content: str,
        payload: Mapping[str, Any],
    ) -> AgentWebhookRequest:
        """사용자 회신을 기다리지 않는 결과·빈 상태 UI 이벤트를 만든다."""

        return self._non_interactive_event(
            event_type="component",
            chat_session_id=chat_session_id,
            workflow_id=workflow_id,
            step_id=step_id,
            ui_contract_id=ui_contract_id,
            ui_type=ui_type,
            content=content,
            payload=payload,
        )

    def error(
        self,
        *,
        chat_session_id: str,
        workflow_id: str,
        step_id: str,
        ui_contract_id: str,
        content: str,
        payload: Mapping[str, Any],
    ) -> AgentWebhookRequest:
        """사용자 회신을 기다리지 않는 안전한 오류 UI 이벤트를 만든다."""

        return self._non_interactive_event(
            event_type="error",
            chat_session_id=chat_session_id,
            workflow_id=workflow_id,
            step_id=step_id,
            ui_contract_id=ui_contract_id,
            ui_type="error_message",
            content=content,
            payload=payload,
        )

    def _non_interactive_event(
        self,
        *,
        event_type: Literal["component", "error"],
        chat_session_id: str,
        workflow_id: str,
        step_id: str,
        ui_contract_id: str,
        ui_type: str,
        content: str,
        payload: Mapping[str, Any],
    ) -> AgentWebhookRequest:
        self._validate_non_interactive_step(
            event_type=event_type,
            workflow_id=workflow_id,
            step_id=step_id,
            ui_contract_id=ui_contract_id,
            ui_type=ui_type,
        )
        return AgentWebhookRequest(
            chat_session_id=chat_session_id,
            event_type=event_type,
            content=content,
            metadata={
                "workflow_id": workflow_id,
                "step_id": step_id,
                "ui_contract_id": ui_contract_id,
                "ui": {"type": ui_type, "payload": dict(payload)},
            },
        )

    def _validate_step_contract(
        self,
        *,
        workflow_id: str,
        step_id: str,
        ui_contract_id: str,
        ui_type: str,
    ) -> None:
        workflow = self._contract_store.get_workflow(workflow_id)
        step = next(
            (
                candidate
                for candidate in workflow["steps"]
                if candidate["step_id"] == step_id
            ),
            None,
        )
        if step is None:
            raise WebhookEventContractError(
                f"[{workflow_id}] 등록되지 않은 Webhook Step입니다: {step_id}"
            )
        if step["interaction_mode"] != "webhook_then_resume":
            raise WebhookEventContractError(
                f"[{workflow_id}/{step_id}] HITL 대기 Step이 아닙니다."
            )
        if step.get("contract_id") != ui_contract_id:
            raise WebhookEventContractError(
                f"[{workflow_id}/{step_id}] UI 계약이 일치하지 않습니다: "
                f"{ui_contract_id}"
            )

        contract = self._contract_store.get_contract(ui_contract_id)
        if contract["contract_type"] != "ui_hitl":
            raise WebhookEventContractError(
                f"UI·HITL 계약이 아닙니다: {ui_contract_id}"
            )

        external_action = str(step.get("external_action") or "")
        expected_ui_type = external_action.rpartition("·")[2].strip()
        if not expected_ui_type or expected_ui_type != ui_type:
            raise WebhookEventContractError(
                f"[{workflow_id}/{step_id}] UI 타입이 일치하지 않습니다: {ui_type}"
            )

    def _validate_non_interactive_step(
        self,
        *,
        event_type: Literal["component", "error"],
        workflow_id: str,
        step_id: str,
        ui_contract_id: str,
        ui_type: str,
    ) -> None:
        workflow = self._contract_store.get_workflow(workflow_id)
        step = next(
            (
                candidate
                for candidate in workflow["steps"]
                if candidate["step_id"] == step_id
            ),
            None,
        )
        if step is None:
            raise WebhookEventContractError(
                f"[{workflow_id}] 등록되지 않은 Webhook Step입니다: {step_id}"
            )
        if step["interaction_mode"] != "webhook":
            raise WebhookEventContractError(
                f"[{workflow_id}/{step_id}] 비대기 Webhook Step이 아닙니다."
            )
        if step.get("contract_id") != ui_contract_id:
            raise WebhookEventContractError(
                f"[{workflow_id}/{step_id}] UI 계약이 일치하지 않습니다: "
                f"{ui_contract_id}"
            )

        contract = self._contract_store.get_contract(ui_contract_id)
        if contract["contract_type"] != "ui_hitl":
            raise WebhookEventContractError(
                f"UI·HITL 계약이 아닙니다: {ui_contract_id}"
            )

        external_action = str(step.get("external_action") or "")
        expected_event_type, separator, expected_ui_type = external_action.partition(
            "·"
        )
        if (
            not separator
            or expected_event_type.strip() != event_type
            or expected_ui_type.strip() != ui_type
        ):
            raise WebhookEventContractError(
                f"[{workflow_id}/{step_id}] Webhook 이벤트 계약이 일치하지 않습니다."
            )
