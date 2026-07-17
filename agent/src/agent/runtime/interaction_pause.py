"""HITL Webhook과 LangGraph 중단 정보를 안전하게 연결한다."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal, Self

from langgraph.types import interrupt
from pydantic import BaseModel, ConfigDict, model_validator

from agent.clients.backend import BackendWebhookClient
from agent.contracts.backend import (
    AgentWebhookRequest,
    AuthenticationRequiredWebhookMetadata,
    NeedApprovalWebhookMetadata,
    NeedInputWebhookMetadata,
)
from agent.runtime.hitl import PendingInteraction


class InteractionPauseEnvelope(BaseModel):
    """LangGraph Checkpoint에 저장되는 단일 대기 상호작용 정보."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["interaction_pause"] = "interaction_pause"
    webhook_event: AgentWebhookRequest
    pending_interaction: PendingInteraction

    @model_validator(mode="after")
    def validate_event_matches_pending(self) -> Self:
        expected = pending_interaction_from_event(self.webhook_event)
        if self.pending_interaction != expected:
            raise ValueError("Webhook과 Pending Interaction 정보가 일치하지 않습니다.")
        return self


class PublishedInteraction(BaseModel):
    """실행 경계에서 Webhook 발행을 마친 대기 상호작용."""

    model_config = ConfigDict(extra="forbid")

    message_id: str
    pending_interaction: PendingInteraction


def pending_interaction_from_event(
    event: AgentWebhookRequest,
) -> PendingInteraction:
    """상호작용 Webhook에서 식별자 혼용 없는 Pending 정보를 만든다."""

    if event.event_type == "need_input":
        metadata = NeedInputWebhookMetadata.model_validate(event.metadata)
        return PendingInteraction(
            type="input",
            workflow_id=metadata.workflow_id,
            step_id=metadata.step_id,
            ui_contract_id=metadata.ui_contract_id,
            input_request_id=metadata.input_request_id,
        )
    if event.event_type == "need_approval":
        metadata = NeedApprovalWebhookMetadata.model_validate(event.metadata)
        if event.confirmation_id is None:
            raise ValueError("need_approval에는 confirmation_id가 필요합니다.")
        return PendingInteraction(
            type="approval",
            workflow_id=metadata.workflow_id,
            step_id=metadata.step_id,
            ui_contract_id=metadata.ui_contract_id,
            confirmation_id=event.confirmation_id,
        )
    if event.event_type == "authentication_required":
        metadata = AuthenticationRequiredWebhookMetadata.model_validate(event.metadata)
        return PendingInteraction(
            type="authentication",
            workflow_id=metadata.workflow_id,
            step_id=metadata.step_id,
            ui_contract_id=metadata.ui_contract_id,
            auth_context_id=metadata.auth_context_id,
        )
    raise ValueError(f"HITL 대기 Webhook 이벤트가 아닙니다: {event.event_type}")


class InteractionPauseRuntime:
    """Checkpoint 중단과 실행 경계의 Webhook 발행을 분리한다."""

    def __init__(self, webhook_client: BackendWebhookClient) -> None:
        self._webhook_client = webhook_client

    @staticmethod
    def create_envelope(event: AgentWebhookRequest) -> InteractionPauseEnvelope:
        return InteractionPauseEnvelope(
            webhook_event=event,
            pending_interaction=pending_interaction_from_event(event),
        )

    def pause(self, event: AgentWebhookRequest) -> Any:
        """상호작용 정보를 Checkpoint에 남기고 Workflow를 중단한다."""

        envelope = self.create_envelope(event)
        return interrupt(envelope.model_dump(mode="json"))

    async def publish_interrupted(
        self,
        payload: Mapping[str, Any],
        *,
        execution_context_id: str,
        request_id: str,
    ) -> PublishedInteraction:
        """중단이 확정된 Payload만 Backend Webhook으로 한 번 발행한다."""

        envelope = InteractionPauseEnvelope.model_validate(payload)
        message_id = await self._webhook_client.publish(
            envelope.webhook_event,
            execution_context_id=execution_context_id,
            request_id=request_id,
        )
        return PublishedInteraction(
            message_id=message_id,
            pending_interaction=envelope.pending_interaction,
        )
