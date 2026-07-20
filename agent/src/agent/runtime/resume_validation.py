"""Backend Resume 요청을 현재 Pending Interaction과 대조한다."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from agent.runtime.hitl import (
    ApprovalResume,
    AuthenticationResume,
    ExecutionResumeRequest,
    InputResume,
    PendingInteraction,
    ResumePayload,
)
from agent.runtime.interaction_pause import InteractionPauseEnvelope

ResumeValidationErrorCode = Literal[
    "AGENT_THREAD_MISMATCH",
    "CHAT_SESSION_MISMATCH",
    "EXECUTION_CONTEXT_MISMATCH",
    "PENDING_CHAT_SESSION_MISMATCH",
    "RESUME_TYPE_MISMATCH",
    "PENDING_IDENTIFIER_MISMATCH",
]


class ExecutionContextBinding(BaseModel):
    """최초 실행 시 Agent가 보관하는 세션·Checkpoint 연결 정보."""

    model_config = ConfigDict(extra="forbid")

    agent_thread_id: str = Field(min_length=1)
    chat_session_id: str = Field(min_length=1)
    execution_context_id: str = Field(min_length=1)


class ValidatedResume(BaseModel):
    """현재 Pending과 일치하여 LangGraph에 전달 가능한 Resume."""

    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1)
    agent_thread_id: str = Field(min_length=1)
    pending_interaction: PendingInteraction
    resume: ResumePayload

    def command_payload(self) -> dict[str, Any]:
        return self.resume.model_dump(mode="json")


class ResumeValidationError(ValueError):
    """현재 실행 Context 또는 Pending과 Resume 요청이 다른 경우."""

    def __init__(
        self,
        *,
        code: ResumeValidationErrorCode,
        reason: str,
    ) -> None:
        super().__init__(reason)
        self.code = code
        self.reason = reason


class ResumeValidationRuntime:
    """중단된 Thread의 Context와 대기 식별자를 Resume 요청에 대조한다."""

    @staticmethod
    def validate(
        *,
        agent_thread_id: str,
        request: ExecutionResumeRequest,
        binding: ExecutionContextBinding,
        interrupt_payload: Mapping[str, Any],
    ) -> ValidatedResume:
        if agent_thread_id != binding.agent_thread_id:
            raise ResumeValidationError(
                code="AGENT_THREAD_MISMATCH",
                reason="요청 Thread가 현재 실행 Thread와 일치하지 않습니다.",
            )
        if request.chat_session_id != binding.chat_session_id:
            raise ResumeValidationError(
                code="CHAT_SESSION_MISMATCH",
                reason="요청 Chat Session이 현재 실행과 일치하지 않습니다.",
            )
        if request.execution_context_id != binding.execution_context_id:
            raise ResumeValidationError(
                code="EXECUTION_CONTEXT_MISMATCH",
                reason="요청 Execution Context가 현재 실행과 일치하지 않습니다.",
            )

        envelope = InteractionPauseEnvelope.model_validate(interrupt_payload)
        if envelope.webhook_event.chat_session_id != binding.chat_session_id:
            raise ResumeValidationError(
                code="PENDING_CHAT_SESSION_MISMATCH",
                reason="Pending Interaction의 Chat Session 연결이 일치하지 않습니다.",
            )

        pending = envelope.pending_interaction
        resume = request.resume
        if resume.type != pending.type:
            raise ResumeValidationError(
                code="RESUME_TYPE_MISMATCH",
                reason="Resume 유형이 현재 대기 상호작용과 일치하지 않습니다.",
            )
        if not ResumeValidationRuntime._identifier_matches(resume, pending):
            raise ResumeValidationError(
                code="PENDING_IDENTIFIER_MISMATCH",
                reason="Resume 식별자가 현재 대기 식별자와 일치하지 않습니다.",
            )

        return ValidatedResume(
            request_id=request.request_id,
            agent_thread_id=agent_thread_id,
            pending_interaction=pending,
            resume=resume,
        )

    @staticmethod
    def _identifier_matches(
        resume: ResumePayload,
        pending: PendingInteraction,
    ) -> bool:
        if isinstance(resume, InputResume):
            return resume.input_request_id == pending.input_request_id
        if isinstance(resume, ApprovalResume):
            return resume.confirmation_id == pending.confirmation_id
        if isinstance(resume, AuthenticationResume):
            return resume.auth_context_id == pending.auth_context_id
        return False
