"""계좌 목록 조회 Workflow의 Mock Backend End-to-End 테스트."""

from __future__ import annotations

import json

import pytest
from pydantic import SecretStr

from agent.clients.backend import BackendClientConfig
from agent.testing.account_list import create_account_list_mock_testbed
from agent.testing.mock_backend import MockBackend


def _config() -> BackendClientConfig:
    return BackendClientConfig(
        base_url="http://backend.test",
        agent_service_token=SecretStr("agent-service-token"),
        agent_webhook_secret=SecretStr("agent-webhook-secret"),
        retry_backoff_seconds=0,
    )


def _account(account_id: str = "acc_001") -> dict[str, object]:
    return {
        "account_id": account_id,
        "bank_name": "토스뱅크",
        "account_alias": "생활비 계좌",
        "account_type": "checking",
        "masked_account_number": "1000-***-1234",
        "currency": "KRW",
        "is_default": True,
        "status": "active",
    }


@pytest.mark.asyncio
async def test_account_list_queries_hint_and_emits_masked_accounts() -> None:
    backend = MockBackend()
    backend.add_success(
        "GET",
        "/api/v1/agent-tools/accounts",
        {"accounts": [_account()]},
    )
    backend.add_success(
        "POST",
        "/api/v1/webhooks/agent",
        {"message_id": "message_account_list_123"},
    )

    async with create_account_list_mock_testbed(
        backend,
        _config(),
        thread_id="thread_account_list",
    ) as testbed:
        result = await testbed.start(
            message="생활비 계좌 찾아줘",
            request_id="req_account_list_123",
            chat_session_id="chat_123",
            execution_context_id="exec_123",
        )
        state = await testbed.state("thread_account_list")
        timeline = backend.exchange_timeline(include_payload=True)

    assert result.status == "completed"
    assert timeline[0]["request"]["account_hint"] == "생활비 계좌"
    assert timeline[0]["request"]["limit"] == "20"
    assert "account_capability" not in timeline[0]["request"]
    assert state["data"]["account_results"] == [_account()]

    event = json.loads(backend.requests[-1].content)
    assert event["event_type"] == "component"
    assert event["metadata"]["step_id"] == "emit_account_list_result"
    assert event["metadata"]["ui"] == {
        "type": "account_list",
        "payload": {"accounts": [_account()]},
    }
    assert "balance" not in event["metadata"]["ui"]["payload"]["accounts"][0]
    backend.assert_all_responses_used()


@pytest.mark.asyncio
async def test_account_list_without_hint_emits_normal_empty_result() -> None:
    backend = MockBackend()
    backend.add_success(
        "GET",
        "/api/v1/agent-tools/accounts",
        {"accounts": []},
    )
    backend.add_success(
        "POST",
        "/api/v1/webhooks/agent",
        {"message_id": "message_empty_123"},
    )

    async with create_account_list_mock_testbed(
        backend,
        _config(),
        thread_id="thread_account_empty",
    ) as testbed:
        result = await testbed.start(
            message="내 계좌 보여줘",
            request_id="req_account_empty_123",
            chat_session_id="chat_123",
            execution_context_id="exec_123",
        )
        timeline = backend.exchange_timeline(include_payload=True)

    assert result.status == "completed"
    assert "account_hint" not in timeline[0]["request"]
    event = json.loads(backend.requests[-1].content)
    assert event["metadata"]["ui"]["payload"]["accounts"] == []
    backend.assert_all_responses_used()


@pytest.mark.asyncio
async def test_account_list_uses_backend_safe_error_message() -> None:
    backend = MockBackend()
    backend.add_json(
        "GET",
        "/api/v1/agent-tools/accounts",
        {
            "success": False,
            "message": "조회 실패",
            "data": None,
            "error": {
                "category": "permission_error",
                "code": "ACCOUNT_ACCESS_DENIED",
                "message": "계좌를 조회할 권한이 없습니다.",
                "retryable": False,
                "details": {},
            },
        },
        status_code=403,
    )
    backend.add_success(
        "POST",
        "/api/v1/webhooks/agent",
        {"message_id": "message_error_123"},
    )

    async with create_account_list_mock_testbed(
        backend,
        _config(),
        thread_id="thread_account_error",
    ) as testbed:
        result = await testbed.start(
            message="내 계좌 보여줘",
            request_id="req_account_error_123",
            chat_session_id="chat_123",
            execution_context_id="exec_123",
        )
        state = await testbed.state("thread_account_error")

    assert result.status == "failed"
    assert state["status"] == "workflow_failed"
    event = json.loads(backend.requests[-1].content)
    assert event["event_type"] == "error"
    assert event["content"] == "계좌를 조회할 권한이 없습니다."
    assert "ACCOUNT_ACCESS_DENIED" not in event["content"]
    backend.assert_all_responses_used()
