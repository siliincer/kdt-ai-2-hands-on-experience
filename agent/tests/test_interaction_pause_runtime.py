"""Webhook 발행과 LangGraph HITL 중단 Runtime 테스트."""

from __future__ import annotations

from typing import Any, TypedDict

import httpx
import pytest
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.types import Command
from pydantic import SecretStr, ValidationError

from agent.clients.backend import (
    BackendClientConfig,
    BackendWebhookClient,
)
from agent.runtime.interaction_pause import (
    InteractionPauseEnvelope,
    InteractionPauseRuntime,
)
from agent.runtime.webhook_events import InteractionWebhookBuilder
from agent.workflow_contracts import WorkflowContractStore


def _config() -> BackendClientConfig:
    return BackendClientConfig(
        base_url="http://backend.test",
        agent_service_token=SecretStr("service-token"),
        agent_webhook_secret=SecretStr("webhook-secret"),
        retry_backoff_seconds=0,
    )


def _webhook_response() -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "success": True,
            "message": "이벤트 발행 완료",
            "data": {"message_id": "message_123"},
        },
    )


def test_pause_envelope_maps_each_interaction_identifier() -> None:
    builder = InteractionWebhookBuilder(WorkflowContractStore())
    input_event = builder.need_input(
        chat_session_id="chat_123",
        workflow_id="wf_external_transfer",
        step_id="request_external_transfer_amount",
        input_request_id="input_123",
        ui_contract_id="UI-TRANSFER-AMOUNT-INPUT",
        ui_type="number_input",
        content="금액을 입력해 주세요.",
        payload={"currency": "KRW"},
    )
    approval_event = builder.need_approval(
        chat_session_id="chat_123",
        workflow_id="wf_external_transfer",
        step_id="request_external_transfer_approval",
        confirmation_id="confirm_123",
        ui_contract_id="UI-EXTERNAL-TRANSFER-CONFIRMATION",
        content="송금할까요?",
        payload={"amount": 50000},
    )
    auth_event = builder.authentication_required(
        chat_session_id="chat_123",
        workflow_id="wf_external_transfer",
        step_id="request_external_authentication",
        auth_context_id="auth_123",
        ui_contract_id="UI-EXTERNAL-TRANSFER-AUTH",
        content="추가 인증이 필요합니다.",
        payload={"available_methods": ["biometric"]},
    )

    input_pending = InteractionPauseRuntime.create_envelope(
        input_event
    ).pending_interaction
    approval_pending = InteractionPauseRuntime.create_envelope(
        approval_event
    ).pending_interaction
    auth_pending = InteractionPauseRuntime.create_envelope(
        auth_event
    ).pending_interaction

    assert input_pending.input_request_id == "input_123"
    assert input_pending.confirmation_id is None
    assert approval_pending.confirmation_id == "confirm_123"
    assert approval_pending.auth_context_id is None
    assert auth_pending.auth_context_id == "auth_123"
    assert auth_pending.input_request_id is None


def test_pause_envelope_rejects_tampered_pending_identifier() -> None:
    event = InteractionWebhookBuilder(WorkflowContractStore()).need_input(
        chat_session_id="chat_123",
        workflow_id="wf_external_transfer",
        step_id="request_external_transfer_amount",
        input_request_id="input_123",
        ui_contract_id="UI-TRANSFER-AMOUNT-INPUT",
        ui_type="number_input",
        content="금액을 입력해 주세요.",
        payload={"currency": "KRW"},
    )
    envelope = InteractionPauseRuntime.create_envelope(event).model_dump(mode="json")
    envelope["pending_interaction"]["input_request_id"] = "input_tampered"

    with pytest.raises(ValidationError):
        InteractionPauseEnvelope.model_validate(envelope)


class PauseState(TypedDict, total=False):
    resumed: dict[str, Any]


@pytest.mark.asyncio
async def test_webhook_is_published_once_after_checkpoint_interrupt() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return _webhook_response()

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
    node_calls = 0

    async with httpx.AsyncClient(
        base_url="http://backend.test",
        transport=httpx.MockTransport(handler),
    ) as http_client:
        webhook_client = BackendWebhookClient(_config(), client=http_client)
        runtime = InteractionPauseRuntime(webhook_client)

        def pause_node(state: PauseState) -> PauseState:
            nonlocal node_calls
            del state
            node_calls += 1
            resumed = runtime.pause(event)
            return {"resumed": resumed}

        graph_builder = StateGraph(PauseState)
        graph_builder.add_node("pause", pause_node)
        graph_builder.set_entry_point("pause")
        graph_builder.add_edge("pause", END)
        graph = graph_builder.compile(checkpointer=MemorySaver())
        config: RunnableConfig = {
            "configurable": {"thread_id": "thread_123"}
        }

        interrupted = graph.invoke({}, config=config)
        payload = interrupted["__interrupt__"][0].value
        published = await runtime.publish_interrupted(
            payload,
            execution_context_id="exec_123",
            request_id="req_123",
        )
        completed = graph.invoke(
            Command(
                resume={
                    "type": "input",
                    "input_request_id": "input_123",
                    "value": {"amount_input_outcome": "submitted", "amount": 50000},
                }
            ),
            config=config,
        )

    assert published.message_id == "message_123"
    assert published.pending_interaction.input_request_id == "input_123"
    assert completed["resumed"]["input_request_id"] == "input_123"
    assert node_calls == 2
    assert len(requests) == 1
    assert requests[0].headers["x-execution-context-id"] == "exec_123"
