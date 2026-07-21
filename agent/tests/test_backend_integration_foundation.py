"""Backend Tool, Webhook과 HITL 공통 기반 테스트."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from agent.clients.backend import (
    AgentToolApiError,
    BackendClientConfig,
    BackendToolClient,
    BackendWebhookClient,
)
from agent.contracts.backend import AgentWebhookRequest
from agent.runtime.hitl import ExecutionResumeRequest, PendingInteraction


def _config() -> BackendClientConfig:
    return BackendClientConfig(
        base_url="http://backend.test",
        agent_service_token=SecretStr("service-token"),
        agent_webhook_secret=SecretStr("webhook-secret"),
        retry_backoff_seconds=0,
    )


@pytest.mark.asyncio
async def test_backend_client_context_preserves_injected_http_client() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(204)

    http_client = httpx.AsyncClient(
        base_url="http://backend.test",
        transport=httpx.MockTransport(handler),
    )
    tool_client = BackendToolClient(_config(), client=http_client)

    async with tool_client as entered_client:
        assert entered_client is tool_client

    response = await http_client.get("/health")
    assert response.status_code == 204
    await http_client.aclose()


@pytest.mark.asyncio
async def test_tool_client_retries_with_same_headers_and_body() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                503,
                json={
                    "success": False,
                    "error": {
                        "category": "technical_error",
                        "code": "BACKEND_TEMPORARY_ERROR",
                        "message": "일시적인 오류입니다.",
                        "retryable": True,
                        "details": {},
                    },
                },
            )
        return httpx.Response(
            200,
            json={
                "success": True,
                "message": "준비 완료",
                "data": {"outcome": "ready_for_confirmation"},
            },
        )

    async with httpx.AsyncClient(
        base_url="http://backend.test",
        transport=httpx.MockTransport(handler),
    ) as http_client:
        client = BackendToolClient(_config(), client=http_client)
        data = await client.request(
            "POST",
            "/api/v1/agent-tools/transfers/external:prepare",
            execution_context_id="exec_123",
            request_id="req_123",
            idempotency_key="idem_123",
            body={"amount": 50000},
        )

    assert data["outcome"] == "ready_for_confirmation"
    assert len(requests) == 2
    assert all(
        request.headers["authorization"] == "Bearer service-token"
        for request in requests
    )
    assert all(request.headers["x-request-id"] == "req_123" for request in requests)
    assert all(request.headers["idempotency-key"] == "idem_123" for request in requests)
    assert requests[0].content == requests[1].content


@pytest.mark.asyncio
async def test_tool_client_does_not_retry_contract_error() -> None:
    call_count = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(
            409,
            json={
                "success": False,
                "error": {
                    "category": "state_error",
                    "code": "IDEMPOTENCY_KEY_CONFLICT",
                    "message": "요청 조건이 다릅니다.",
                    "retryable": False,
                    "details": {},
                },
            },
        )

    async with httpx.AsyncClient(
        base_url="http://backend.test",
        transport=httpx.MockTransport(handler),
    ) as http_client:
        client = BackendToolClient(_config(), client=http_client)
        with pytest.raises(AgentToolApiError) as raised:
            await client.request(
                "POST",
                "/api/v1/agent-tools/settings/default-account:prepare",
                execution_context_id="exec_123",
                request_id="req_123",
                idempotency_key="idem_123",
                body={"account_id": "acc_001"},
            )

    assert raised.value.code == "IDEMPOTENCY_KEY_CONFLICT"
    assert call_count == 1


@pytest.mark.asyncio
async def test_webhook_client_sends_target_contract_headers() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(
            200,
            json={
                "success": True,
                "message": "이벤트 발행 완료",
                "data": {"message_id": "1720843200000-0"},
            },
        )

    event = AgentWebhookRequest(
        chat_session_id="chat_123",
        event_type="need_input",
        content="금액을 입력해 주세요.",
        metadata={
            "workflow_id": "wf_external_transfer",
            "step_id": "request_external_transfer_amount",
            "input_request_id": "input_123",
            "ui_contract_id": "UI-TRANSFER-AMOUNT-INPUT",
            "ui": {"type": "number_input", "payload": {"currency": "KRW"}},
        },
    )
    async with httpx.AsyncClient(
        base_url="http://backend.test",
        transport=httpx.MockTransport(handler),
    ) as http_client:
        client = BackendWebhookClient(_config(), client=http_client)
        message_id = await client.publish(
            event,
            execution_context_id="exec_123",
            request_id="req_123",
        )

    request = captured["request"]
    assert isinstance(request, httpx.Request)
    assert message_id == "1720843200000-0"
    assert request.headers["x-agent-secret"] == "webhook-secret"
    assert request.headers["x-execution-context-id"] == "exec_123"
    assert b"prompt_for" not in request.content


def test_pending_interaction_requires_exact_identifier() -> None:
    interaction = PendingInteraction(
        type="input",
        workflow_id="wf_balance_inquiry",
        step_id="request_balance_account_selection",
        ui_contract_id="UI-BALANCE-ACCOUNT-SELECTION",
        input_request_id="input_123",
    )
    assert interaction.input_request_id == "input_123"

    with pytest.raises(ValidationError):
        PendingInteraction(
            type="input",
            workflow_id="wf_balance_inquiry",
            step_id="request_balance_account_selection",
            ui_contract_id="UI-BALANCE-ACCOUNT-SELECTION",
            input_request_id="input_123",
            confirmation_id="confirm_123",
        )


def test_resume_contract_uses_validated_identifier_without_prompt_for() -> None:
    request = ExecutionResumeRequest.model_validate(
        {
            "request_id": "req_123",
            "chat_session_id": "chat_123",
            "execution_context_id": "exec_123",
            "resume": {
                "type": "input",
                "input_request_id": "input_123",
                "value": {
                    "amount_input_outcome": "submitted",
                    "amount": 50000,
                },
            },
        }
    )
    serialized = request.model_dump(mode="json")

    assert serialized["resume"]["input_request_id"] == "input_123"
    assert "prompt_for" not in serialized["resume"]
