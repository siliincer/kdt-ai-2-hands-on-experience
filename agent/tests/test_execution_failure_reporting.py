"""처리되지 않은 Workflow 오류의 공통 Webhook 보고 테스트."""

from __future__ import annotations

import json

import httpx
import pytest
from pydantic import SecretStr

from agent.clients.backend import BackendClientConfig, BackendWebhookClient
from agent.runtime import InteractionWebhookBuilder, WebhookExecutionFailureReporter
from agent.runtime.failure_reporting import SAFE_FAILURE_MESSAGE
from agent.workflow_contracts import WorkflowContractStore


def _config() -> BackendClientConfig:
    return BackendClientConfig(
        base_url="http://backend.test",
        agent_service_token=SecretStr("agent-service-token"),
        agent_webhook_secret=SecretStr("agent-webhook-secret"),
        retry_backoff_seconds=0,
    )


@pytest.mark.asyncio
async def test_failure_reporter_uses_safe_global_error_contract() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "success": True,
                "message": "이벤트 발행 완료",
                "data": {"message_id": "message_error_123"},
            },
        )

    async with httpx.AsyncClient(
        base_url="http://backend.test",
        transport=httpx.MockTransport(handler),
    ) as http_client:
        reporter = WebhookExecutionFailureReporter(
            BackendWebhookClient(_config(), client=http_client),
            InteractionWebhookBuilder(WorkflowContractStore()),
        )
        await reporter.report_failure(
            agent_thread_id="thread_123",
            chat_session_id="chat_123",
            execution_context_id="exec_123",
            request_id="req_start_123",
        )

    payload = json.loads(requests[0].content)
    assert requests[0].headers["x-execution-context-id"] == "exec_123"
    assert requests[0].headers["x-request-id"] == "req_start_123"
    assert payload["event_type"] == "error"
    assert payload["content"] == SAFE_FAILURE_MESSAGE
    assert payload["metadata"] == {
        "workflow_id": "wf_global_agent_entry",
        "step_id": "emit_workflow_dispatch_error",
        "ui_contract_id": "UI-COMMON-ERROR",
        "ui": {
            "type": "error_message",
            "payload": {
                "message": SAFE_FAILURE_MESSAGE,
            },
        },
    }
