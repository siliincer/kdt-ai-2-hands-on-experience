"""Agent와 Backend가 주고받는 HTTP Payload 계약."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AgentToolErrorData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: str
    code: str
    message: str
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class AgentToolEnvelope(BaseModel):
    """Backend CommonResponse의 Agent Tool 공통 형태."""

    model_config = ConfigDict(extra="forbid")

    success: bool
    message: str | None = None
    data: dict[str, Any] | None = None
    error: AgentToolErrorData | None = None

    @model_validator(mode="after")
    def validate_result_shape(self) -> AgentToolEnvelope:
        if self.success and self.error is not None:
            raise ValueError("성공 응답에는 error를 포함할 수 없습니다.")
        if not self.success and self.error is None:
            raise ValueError("실패 응답에는 error가 필요합니다.")
        return self


WebhookEventType = Literal[
    "status",
    "token",
    "tool_call",
    "component",
    "need_input",
    "need_approval",
    "authentication_required",
    "done",
    "error",
    "blocked",
]
InputUiType = Literal[
    "text_input",
    "recipient_select",
    "account_card_list",
    "number_input",
    "period_input",
    "option_select",
]
NonEmptyString = Annotated[str, Field(min_length=1)]


class NeedInputUi(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: InputUiType
    payload: dict[str, Any]


class ApprovalUi(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["confirm_modal"]
    payload: dict[str, Any]


class AuthenticationUi(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["auth_request"]
    payload: dict[str, Any]


class NeedInputWebhookMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workflow_id: NonEmptyString
    step_id: NonEmptyString
    input_request_id: NonEmptyString
    ui_contract_id: NonEmptyString
    ui: NeedInputUi


class NeedApprovalWebhookMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workflow_id: NonEmptyString
    step_id: NonEmptyString
    ui_contract_id: NonEmptyString
    ui: ApprovalUi


class AuthenticationRequiredWebhookMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workflow_id: NonEmptyString
    step_id: NonEmptyString
    auth_context_id: NonEmptyString
    ui_contract_id: NonEmptyString
    ui: AuthenticationUi


class AgentWebhookRequest(BaseModel):
    """목표 계약 기준 Agent Webhook Payload."""

    model_config = ConfigDict(extra="forbid")

    chat_session_id: str
    event_type: WebhookEventType
    content: str
    confirmation_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_interaction_identifier(self) -> AgentWebhookRequest:
        if self.event_type == "need_input":
            NeedInputWebhookMetadata.model_validate(self.metadata)
            if self.confirmation_id is not None:
                raise ValueError("need_input에는 confirmation_id를 사용할 수 없습니다.")
        elif self.event_type == "need_approval":
            if not self.confirmation_id:
                raise ValueError("need_approval에는 confirmation_id가 필요합니다.")
            NeedApprovalWebhookMetadata.model_validate(self.metadata)
        elif self.event_type == "authentication_required":
            AuthenticationRequiredWebhookMetadata.model_validate(self.metadata)
            if self.confirmation_id is not None:
                raise ValueError(
                    "authentication_required에는 confirmation_id를 사용할 수 없습니다."
                )
        elif self.confirmation_id is not None:
            raise ValueError("confirmation_id는 need_approval에만 사용할 수 있습니다.")
        return self
