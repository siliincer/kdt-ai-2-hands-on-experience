"""HITL Webhook 이벤트 Builder 계약 테스트."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agent.contracts.backend import AgentWebhookRequest, InputUiType
from agent.runtime.webhook_events import (
    InteractionWebhookBuilder,
    WebhookEventContractError,
)
from agent.workflow_contracts import WorkflowContractStore


def _builder() -> InteractionWebhookBuilder:
    return InteractionWebhookBuilder(WorkflowContractStore())


def test_need_input_uses_manifest_step_and_input_request_id() -> None:
    event = _builder().need_input(
        chat_session_id="chat_123",
        workflow_id="wf_external_transfer",
        step_id="request_external_transfer_amount",
        input_request_id="input_amount_123",
        ui_contract_id="UI-TRANSFER-AMOUNT-INPUT",
        ui_type="number_input",
        content="송금 금액을 입력해 주세요.",
        payload={"currency": "KRW", "min": 1},
    )
    serialized = event.model_dump(mode="json")

    assert serialized == {
        "chat_session_id": "chat_123",
        "event_type": "need_input",
        "content": "송금 금액을 입력해 주세요.",
        "confirmation_id": None,
        "metadata": {
            "workflow_id": "wf_external_transfer",
            "step_id": "request_external_transfer_amount",
            "input_request_id": "input_amount_123",
            "ui_contract_id": "UI-TRANSFER-AMOUNT-INPUT",
            "ui": {
                "type": "number_input",
                "payload": {"currency": "KRW", "min": 1},
            },
        },
    }
    assert "prompt_for" not in str(serialized)


def test_need_approval_keeps_confirmation_id_at_webhook_root() -> None:
    event = _builder().need_approval(
        chat_session_id="chat_123",
        workflow_id="wf_external_transfer",
        step_id="request_external_transfer_approval",
        confirmation_id="confirm_123",
        ui_contract_id="UI-EXTERNAL-TRANSFER-CONFIRMATION",
        content="아래 정보로 송금할까요?",
        payload={"amount": 50000, "currency": "KRW"},
    )

    assert event.event_type == "need_approval"
    assert event.confirmation_id == "confirm_123"
    assert event.metadata["ui"] == {
        "type": "confirm_modal",
        "payload": {"amount": 50000, "currency": "KRW"},
    }
    assert "confirmation_id" not in event.metadata
    assert "input_request_id" not in event.metadata


def test_authentication_required_uses_auth_context_only() -> None:
    event = _builder().authentication_required(
        chat_session_id="chat_123",
        workflow_id="wf_external_transfer",
        step_id="request_external_authentication",
        auth_context_id="auth_123",
        ui_contract_id="UI-EXTERNAL-TRANSFER-AUTH",
        content="송금을 계속하려면 추가 인증이 필요합니다.",
        payload={
            "title": "추가 인증이 필요합니다.",
            "available_methods": ["biometric", "password"],
            "expires_at": "2026-07-16T10:08:00+09:00",
        },
    )

    assert event.event_type == "authentication_required"
    assert event.confirmation_id is None
    assert event.metadata["auth_context_id"] == "auth_123"
    assert event.metadata["ui_contract_id"] == "UI-EXTERNAL-TRANSFER-AUTH"
    assert event.metadata["ui"]["type"] == "auth_request"


@pytest.mark.parametrize(
    ("step_id", "ui_contract_id", "ui_type"),
    [
        (
            "request_external_transfer_amount",
            "UI-EXTERNAL-TRANSFER-FROM-ACCOUNT",
            "number_input",
        ),
        (
            "request_external_transfer_amount",
            "UI-TRANSFER-AMOUNT-INPUT",
            "account_card_list",
        ),
        (
            "prepare_external_transfer",
            "UI-TRANSFER-AMOUNT-INPUT",
            "number_input",
        ),
    ],
)
def test_need_input_rejects_manifest_mismatch(
    step_id: str,
    ui_contract_id: str,
    ui_type: InputUiType,
) -> None:
    with pytest.raises(WebhookEventContractError):
        _builder().need_input(
            chat_session_id="chat_123",
            workflow_id="wf_external_transfer",
            step_id=step_id,
            input_request_id="input_123",
            ui_contract_id=ui_contract_id,
            ui_type=ui_type,
            content="입력해 주세요.",
            payload={},
        )


def test_raw_interaction_webhook_rejects_incomplete_metadata() -> None:
    with pytest.raises(ValidationError):
        AgentWebhookRequest(
            chat_session_id="chat_123",
            event_type="need_input",
            content="입력해 주세요.",
            metadata={
                "workflow_id": "wf_external_transfer",
                "step_id": "request_external_transfer_amount",
                "input_request_id": "input_123",
                "ui_contract_id": "UI-TRANSFER-AMOUNT-INPUT",
            },
        )
