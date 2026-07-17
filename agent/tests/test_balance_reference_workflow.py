"""잔액 조회 기준 Workflow의 Mock Backend End-to-End 테스트."""

from __future__ import annotations

import json

import pytest
from pydantic import SecretStr

from agent.clients.backend import BackendClientConfig
from agent.testing import MockBackend
from agent.testing.balance_inquiry import create_balance_mock_testbed


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
        "bank_name": "신한은행",
        "account_alias": "생활비 통장",
        "account_type": "checking",
        "masked_account_number": "110-***-123456",
        "currency": "KRW",
        "is_default": True,
        "status": "active",
    }


def _balance(account_id: str = "acc_001") -> dict[str, object]:
    return {
        "account_id": account_id,
        "bank_name": "신한은행",
        "account_alias": "생활비 통장",
        "masked_account_number": "110-***-123456",
        "balance": 1200000,
        "available_balance": 1180000,
        "currency": "KRW",
        "as_of": "2026-07-16T10:00:00+09:00",
    }


@pytest.mark.asyncio
async def test_balance_reference_workflow_auto_resolves_and_emits_result() -> None:
    backend = MockBackend()
    backend.add_success(
        "GET",
        "/api/v1/agent-tools/accounts",
        {
            "account_resolution_outcome": "resolved",
            "accounts": [_account()],
            "account_ids": ["acc_001"],
        },
    )
    backend.add_success(
        "POST",
        "/api/v1/agent-tools/accounts/balances:query",
        {"balance_results": [_balance()]},
    )
    backend.add_success(
        "POST",
        "/api/v1/webhooks/agent",
        {"message_id": "message_result_123"},
    )

    async with create_balance_mock_testbed(
        backend,
        _config(),
        thread_id="thread_auto",
    ) as testbed:
        result = await testbed.start(
            message="내 계좌 잔액을 전부 보여줘",
            request_id="req_auto_123",
            chat_session_id="chat_123",
            execution_context_id="exec_123",
        )
        timeline = testbed.request_timeline()
        exchanges = backend.exchange_timeline(include_payload=True)

    assert result.status == "completed"
    assert [entry["path"] for entry in timeline] == [
        "/api/v1/agent-tools/accounts",
        "/api/v1/agent-tools/accounts/balances:query",
        "/api/v1/webhooks/agent",
    ]
    assert "payload" not in timeline[-1]
    assert exchanges[0]["request"]["all_accounts_requested"] == "true"
    assert exchanges[1]["request"]["account_ids"] == ["acc_001"]
    assert exchanges[-1]["response"]["data"]["message_id"] == "message_result_123"
    assert [request.url.path for request in backend.requests] == [
        "/api/v1/agent-tools/accounts",
        "/api/v1/agent-tools/accounts/balances:query",
        "/api/v1/webhooks/agent",
    ]
    assert backend.requests[0].headers["authorization"] == "Bearer agent-service-token"
    assert backend.requests[1].headers["x-execution-context-id"] == "exec_123"
    result_event = json.loads(backend.requests[2].content)
    assert result_event["event_type"] == "component"
    assert result_event["metadata"]["step_id"] == "emit_balance_result"
    assert result_event["metadata"]["ui"]["type"] == "balance_result"
    assert result_event["metadata"]["ui"]["payload"]["accounts"] == [
        {
            "account_id": "acc_001",
            "account_alias": "생활비 통장",
            "masked_account_number": "110-***-123456",
            "balance": 1200000,
            "available_amount": 1180000,
            "currency": "KRW",
        }
    ]


@pytest.mark.asyncio
async def test_balance_reference_workflow_resumes_without_revalidating_selection(
) -> None:
    backend = MockBackend()
    backend.add_success(
        "GET",
        "/api/v1/agent-tools/accounts",
        {
            "account_resolution_outcome": "selection_required",
            "accounts": [_account("acc_001"), _account("acc_002")],
            "account_ids": [],
        },
    )
    backend.add_success(
        "POST",
        "/api/v1/webhooks/agent",
        {"message_id": "message_input_123"},
    )
    backend.add_success(
        "POST",
        "/api/v1/agent-tools/accounts/balances:query",
        {"balance_results": [_balance("acc_002")]},
    )
    backend.add_success(
        "POST",
        "/api/v1/webhooks/agent",
        {"message_id": "message_result_123"},
    )

    async with create_balance_mock_testbed(
        backend,
        _config(),
        thread_id="thread_selection",
        input_request_id="input_balance_123",
    ) as testbed:
        interrupted = await testbed.start(
            message="내 계좌 잔액을 전부 보여줘",
            request_id="req_selection_123",
            chat_session_id="chat_123",
            execution_context_id="exec_123",
        )
        completed = await testbed.resume_input(
            agent_thread_id="thread_selection",
            request_id="req_resume_123",
            chat_session_id="chat_123",
            execution_context_id="exec_123",
            input_request_id="input_balance_123",
            value={
                "account_selection_outcome": "selected",
                "account_ids": ["acc_002"],
            },
        )
        state = await testbed.state("thread_selection")

    assert interrupted.status == "waiting"
    assert interrupted.pending_interaction is not None
    assert interrupted.pending_interaction["input_request_id"] == "input_balance_123"
    assert completed.status == "completed"
    assert len(
        backend.requests_to("GET", "/api/v1/agent-tools/accounts")
    ) == 1
    assert len(
        backend.requests_to(
            "POST",
            "/api/v1/agent-tools/accounts/balances:query",
        )
    ) == 1
    assert state["data"]["account_ids"] == ["acc_002"]
    assert state["data"]["input_request_id"] is None

    input_event = json.loads(
        backend.requests_to("POST", "/api/v1/webhooks/agent")[0].content
    )
    assert input_event["event_type"] == "need_input"
    assert input_event["metadata"]["ui"]["payload"]["accounts"][0] == {
        "account_id": "acc_001",
        "bank_name": "신한은행",
        "account_alias": "생활비 통장",
        "account_type": "checking",
        "masked_account_number": "110-***-123456",
        "currency": "KRW",
        "is_default": True,
    }
    backend.assert_all_responses_used()
