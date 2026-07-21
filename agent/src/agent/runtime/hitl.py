"""Backend가 검증한 사용자 입력으로 Agent Workflow를 재개하는 모델."""

from __future__ import annotations

from typing import Annotated, Any, Literal, Self, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator

InteractionType = Literal["input", "approval", "authentication"]


class ExecutionStartRequest(BaseModel):
    """Backend가 새 Agent Workflow 실행을 요청할 때 사용하는 값."""

    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1)
    chat_session_id: str = Field(min_length=1)
    execution_context_id: str = Field(min_length=1)
    message: str = Field(min_length=1)


class PendingInteraction(BaseModel):
    """한 Thread에서 현재 대기 중인 단일 HITL 상호작용."""

    model_config = ConfigDict(extra="forbid")

    type: InteractionType
    workflow_id: str
    step_id: str
    ui_contract_id: str
    input_request_id: str | None = None
    confirmation_id: str | None = None
    auth_context_id: str | None = None

    @model_validator(mode="after")
    def validate_identifier(self) -> PendingInteraction:
        identifiers = {
            "input": self.input_request_id,
            "approval": self.confirmation_id,
            "authentication": self.auth_context_id,
        }
        if not identifiers[self.type]:
            raise ValueError(f"{self.type} 대기 식별자가 필요합니다.")
        if sum(value is not None for value in identifiers.values()) != 1:
            raise ValueError("대기 상호작용 식별자는 정확히 하나만 사용합니다.")
        return self


class InputResume(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["input"]
    input_request_id: str
    value: dict[str, Any]


class ApprovalResume(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["approval"]
    confirmation_id: str
    approval_outcome: Literal["approved", "change_requested", "cancelled"]
    change_target: str | None = None

    @model_validator(mode="after")
    def validate_change_target(self) -> Self:
        if (
            self.approval_outcome != "change_requested"
            and self.change_target is not None
        ):
            raise ValueError(
                "change_target은 change_requested 승인 결과에만 사용할 수 있습니다."
            )
        return self


class AuthenticationResume(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["authentication"]
    auth_context_id: str
    auth_status: Literal["verified", "failed", "cancelled", "expired"]


ResumePayload = Annotated[
    Union[InputResume, ApprovalResume, AuthenticationResume],
    Field(discriminator="type"),
]


class ExecutionResumeRequest(BaseModel):
    """Backend가 중단된 Agent Workflow를 재개할 때 사용하는 요청."""

    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1)
    chat_session_id: str = Field(min_length=1)
    execution_context_id: str = Field(min_length=1)
    resume: ResumePayload
