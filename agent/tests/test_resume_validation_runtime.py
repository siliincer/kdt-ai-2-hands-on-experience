"""Backend Resume 요청과 현재 Pending Interaction 대조 테스트."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from agent.runtime.hitl import ExecutionResumeRequest
from agent.runtime.interaction_pause import InteractionPauseRuntime
from agent.runtime.resume_validation import (
    ExecutionContextBinding,
    ResumeValidationError,
    ResumeValidationRuntime,
)
from agent.runtime.webhook_events import InteractionWebhookBuilder
from agent.workflow_contracts import WorkflowContractStore


def _binding() -> ExecutionContextBinding:
    return ExecutionContextBinding(
        agent_thread_id="thread_123",
        chat_session_id="chat_123",
        execution_context_id="exec_123",
    )


def _input_interrupt() -> dict[str, Any]:
    event = InteractionWebhookBuilder(WorkflowContractStore()).need_input(
        chat_session_id="chat_123",
        workflow_id="wf_external_transfer",
        step_id="request_external_transfer_amount",
        input_request_id="input_123",
        ui_contract_id="UI-TRANSFER-AMOUNT-INPUT",
        ui_type="number_input",
        content="금액을 입력해 주세요.",
        payload={"currency": "KRW", "min": 1},
    )
    return InteractionPauseRuntime.create_envelope(event).model_dump(mode="json")


def _approval_interrupt() -> dict[str, Any]:
    event = InteractionWebhookBuilder(WorkflowContractStore()).need_approval(
        chat_session_id="chat_123",
        workflow_id="wf_external_transfer",
        step_id="request_external_transfer_approval",
        confirmation_id="confirm_123",
        ui_contract_id="UI-EXTERNAL-TRANSFER-CONFIRMATION",
        content="송금할까요?",
        payload={"amount": 50000, "currency": "KRW"},
    )
    return InteractionPauseRuntime.create_envelope(event).model_dump(mode="json")


def _authentication_interrupt() -> dict[str, Any]:
    event = InteractionWebhookBuilder(WorkflowContractStore()).authentication_required(
        chat_session_id="chat_123",
        workflow_id="wf_external_transfer",
        step_id="request_external_authentication",
        auth_context_id="auth_123",
        ui_contract_id="UI-EXTERNAL-TRANSFER-AUTH",
        content="추가 인증이 필요합니다.",
        payload={"available_methods": ["biometric"]},
    )
    return InteractionPauseRuntime.create_envelope(event).model_dump(mode="json")


@pytest.mark.parametrize(
    ("interrupt_payload", "resume_payload", "expected_identifier"),
    [
        (
            _input_interrupt(),
            {
                "type": "input",
                "input_request_id": "input_123",
                "value": {"amount_input_outcome": "submitted", "amount": 50000},
            },
            "input_123",
        ),
        (
            _approval_interrupt(),
            {
                "type": "approval",
                "confirmation_id": "confirm_123",
                "approval_outcome": "approved",
            },
            "confirm_123",
        ),
        (
            _authentication_interrupt(),
            {
                "type": "authentication",
                "auth_context_id": "auth_123",
                "auth_status": "verified",
            },
            "auth_123",
        ),
    ],
)
def test_validate_accepts_matching_pending_interaction(
    interrupt_payload: Mapping[str, Any],
    resume_payload: Mapping[str, Any],
    expected_identifier: str,
) -> None:
    request = ExecutionResumeRequest.model_validate(
        {
            "request_id": "req_resume_123",
            "chat_session_id": "chat_123",
            "execution_context_id": "exec_123",
            "resume": resume_payload,
        }
    )

    validated = ResumeValidationRuntime.validate(
        agent_thread_id="thread_123",
        request=request,
        binding=_binding(),
        interrupt_payload=interrupt_payload,
    )

    assert expected_identifier in str(validated.command_payload())
    assert "chat_session_id" not in validated.command_payload()
    assert validated.request_id == "req_resume_123"


@pytest.mark.parametrize(
    ("agent_thread_id", "chat_session_id", "execution_context_id", "expected_code"),
    [
        ("thread_other", "chat_123", "exec_123", "AGENT_THREAD_MISMATCH"),
        ("thread_123", "chat_other", "exec_123", "CHAT_SESSION_MISMATCH"),
        ("thread_123", "chat_123", "exec_other", "EXECUTION_CONTEXT_MISMATCH"),
    ],
)
def test_validate_rejects_execution_context_mismatch(
    agent_thread_id: str,
    chat_session_id: str,
    execution_context_id: str,
    expected_code: str,
) -> None:
    request = ExecutionResumeRequest.model_validate(
        {
            "request_id": "req_resume_123",
            "chat_session_id": chat_session_id,
            "execution_context_id": execution_context_id,
            "resume": {
                "type": "input",
                "input_request_id": "input_123",
                "value": {"amount_input_outcome": "submitted", "amount": 50000},
            },
        }
    )

    with pytest.raises(ResumeValidationError) as raised:
        ResumeValidationRuntime.validate(
            agent_thread_id=agent_thread_id,
            request=request,
            binding=_binding(),
            interrupt_payload=_input_interrupt(),
        )

    assert raised.value.code == expected_code


@pytest.mark.parametrize(
    ("resume_payload", "expected_code"),
    [
        (
            {
                "type": "approval",
                "confirmation_id": "confirm_123",
                "approval_outcome": "approved",
            },
            "RESUME_TYPE_MISMATCH",
        ),
        (
            {
                "type": "input",
                "input_request_id": "input_stale",
                "value": {"amount_input_outcome": "submitted", "amount": 50000},
            },
            "PENDING_IDENTIFIER_MISMATCH",
        ),
    ],
)
def test_validate_rejects_wrong_type_or_stale_identifier(
    resume_payload: Mapping[str, Any],
    expected_code: str,
) -> None:
    request = ExecutionResumeRequest.model_validate(
        {
            "request_id": "req_resume_123",
            "chat_session_id": "chat_123",
            "execution_context_id": "exec_123",
            "resume": resume_payload,
        }
    )

    with pytest.raises(ResumeValidationError) as raised:
        ResumeValidationRuntime.validate(
            agent_thread_id="thread_123",
            request=request,
            binding=_binding(),
            interrupt_payload=_input_interrupt(),
        )

    assert raised.value.code == expected_code


def test_validate_rejects_pending_bound_to_another_chat_session() -> None:
    interrupt_payload = _input_interrupt()
    interrupt_payload["webhook_event"]["chat_session_id"] = "chat_other"
    request = ExecutionResumeRequest.model_validate(
        {
            "request_id": "req_resume_123",
            "chat_session_id": "chat_123",
            "execution_context_id": "exec_123",
            "resume": {
                "type": "input",
                "input_request_id": "input_123",
                "value": {"amount_input_outcome": "submitted", "amount": 50000},
            },
        }
    )

    with pytest.raises(ResumeValidationError) as raised:
        ResumeValidationRuntime.validate(
            agent_thread_id="thread_123",
            request=request,
            binding=_binding(),
            interrupt_payload=interrupt_payload,
        )

    assert raised.value.code == "PENDING_CHAT_SESSION_MISMATCH"
