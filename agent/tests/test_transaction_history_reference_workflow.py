"""거래내역 조회 Workflow의 Mock Backend End-to-End 테스트."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from pydantic import SecretStr

from agent.clients.backend import BackendClientConfig
from agent.testing.mock_backend import MockBackend
from agent.testing.transaction_history import (
    create_transaction_history_mock_testbed,
)

NOW = datetime(2026, 7, 19, 3, 0, tzinfo=timezone.utc)


def _config() -> BackendClientConfig:
    return BackendClientConfig(
        base_url="http://backend.test",
        agent_service_token=SecretStr("agent-service-token"),
        agent_webhook_secret=SecretStr("agent-webhook-secret"),
        retry_backoff_seconds=0,
    )


def _account(account_id: str = "acc_living") -> dict[str, object]:
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


def _transaction() -> dict[str, object]:
    return {
        "transaction_id": "txn_001",
        "account_id": "acc_living",
        "account_alias": "생활비 계좌",
        "occurred_at": "2026-07-18T12:30:00+09:00",
        "transaction_type": "card_payment",
        "amount": 18500,
        "currency": "KRW",
        "transaction_title": "배민",
        "category": "식비",
    }


def _resolved_accounts(backend: MockBackend) -> None:
    backend.add_success(
        "GET",
        "/api/v1/agent-tools/accounts",
        {
            "account_resolution_outcome": "resolved",
            "accounts": [_account()],
            "account_ids": ["acc_living"],
        },
    )


@pytest.mark.asyncio
async def test_transaction_history_defaults_period_and_emits_first_page() -> None:
    backend = MockBackend()
    _resolved_accounts(backend)
    backend.add_success(
        "POST",
        "/api/v1/agent-tools/transactions:query",
        {
            "transaction_results": [_transaction()],
            "transaction_query_id": "txq_123",
            "next_cursor": "cursor_002",
        },
    )
    backend.add_success(
        "POST",
        "/api/v1/webhooks/agent",
        {"message_id": "message_transactions_123"},
    )

    async with create_transaction_history_mock_testbed(
        backend,
        _config(),
        thread_id="thread_transactions",
        now=NOW,
    ) as testbed:
        result = await testbed.start(
            message="생활비 계좌의 최근 거래내역 확인해줘",
            request_id="req_transactions_123",
            chat_session_id="chat_123",
            execution_context_id="exec_123",
        )
        state = await testbed.state("thread_transactions")
        exchanges = backend.exchange_timeline(include_payload=True)

    assert result.status == "completed"
    assert exchanges[0]["request"]["account_hint"] == "생활비 계좌"
    assert exchanges[0]["request"]["resolve_selection"] == "true"
    assert exchanges[1]["request"] == {
        "account_ids": ["acc_living"],
        "start_date": "2026-06-19",
        "end_date": "2026-07-19",
        "keyword": None,
        "transaction_type": None,
        "limit": 10,
    }
    assert state["data"]["transaction_query_id"] == "txq_123"
    assert state["data"]["next_cursor"] == "cursor_002"

    event = json.loads(backend.requests[-1].content)
    payload = event["metadata"]["ui"]["payload"]
    assert event["event_type"] == "component"
    assert event["metadata"]["ui"]["type"] == "transaction_list"
    assert payload["period"] == {
        "start_date": "2026-06-19",
        "end_date": "2026-07-19",
    }
    assert payload["transactions"] == [_transaction()]
    assert payload["transaction_query_id"] == "txq_123"
    assert payload["pagination"]["next_cursor"] == "cursor_002"
    backend.assert_all_responses_used()


@pytest.mark.asyncio
async def test_transaction_history_resumes_account_selection_without_requery() -> None:
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
        {"message_id": "message_account_selection_123"},
    )
    backend.add_success(
        "POST",
        "/api/v1/agent-tools/transactions:query",
        {
            "transaction_results": [],
            "transaction_query_id": "txq_selected",
            "next_cursor": None,
        },
    )
    backend.add_success(
        "POST",
        "/api/v1/webhooks/agent",
        {"message_id": "message_empty_result_123"},
    )

    async with create_transaction_history_mock_testbed(
        backend,
        _config(),
        thread_id="thread_account_selection",
        input_request_ids=["input_account_123"],
        now=NOW,
    ) as testbed:
        waiting = await testbed.start(
            message="최근 거래내역 보여줘",
            request_id="req_account_selection_123",
            chat_session_id="chat_123",
            execution_context_id="exec_123",
        )
        completed = await testbed.resume_input(
            agent_thread_id="thread_account_selection",
            request_id="req_account_resume_123",
            chat_session_id="chat_123",
            execution_context_id="exec_123",
            input_request_id="input_account_123",
            value={
                "account_selection_outcome": "selected",
                "account_ids": ["acc_002"],
            },
        )
        state = await testbed.state("thread_account_selection")

    assert waiting.status == "waiting"
    assert waiting.pending_interaction is not None
    assert waiting.pending_interaction["step_id"] == ("request_transaction_account_selection")
    assert completed.status == "completed"
    assert len(backend.requests_to("GET", "/api/v1/agent-tools/accounts")) == 1
    query = json.loads(
        backend.requests_to(
            "POST",
            "/api/v1/agent-tools/transactions:query",
        )[0].content
    )
    assert query["account_ids"] == ["acc_002"]
    assert state["data"]["input_request_id"] is None
    backend.assert_all_responses_used()


@pytest.mark.asyncio
async def test_transaction_history_requests_unresolved_period_then_resumes() -> None:
    backend = MockBackend()
    _resolved_accounts(backend)
    backend.add_success(
        "POST",
        "/api/v1/webhooks/agent",
        {"message_id": "message_period_123"},
    )
    backend.add_success(
        "POST",
        "/api/v1/agent-tools/transactions:query",
        {
            "transaction_results": [],
            "transaction_query_id": "txq_period",
            "next_cursor": None,
        },
    )
    backend.add_success(
        "POST",
        "/api/v1/webhooks/agent",
        {"message_id": "message_period_result_123"},
    )

    async with create_transaction_history_mock_testbed(
        backend,
        _config(),
        thread_id="thread_period_selection",
        input_request_ids=["input_period_123"],
        now=NOW,
    ) as testbed:
        waiting = await testbed.start(
            message="생활비 계좌 작년 거래내역 보여줘",
            request_id="req_period_123",
            chat_session_id="chat_123",
            execution_context_id="exec_123",
        )
        completed = await testbed.resume_input(
            agent_thread_id="thread_period_selection",
            request_id="req_period_resume_123",
            chat_session_id="chat_123",
            execution_context_id="exec_123",
            input_request_id="input_period_123",
            value={
                "period_selection_outcome": "selected",
                "start_date": "2025-01-01",
                "end_date": "2025-12-31",
            },
        )

    assert waiting.status == "waiting"
    assert waiting.pending_interaction is not None
    assert waiting.pending_interaction["step_id"] == "request_period_selection"
    assert completed.status == "completed"
    period_event = json.loads(backend.requests_to("POST", "/api/v1/webhooks/agent")[0].content)
    assert period_event["metadata"]["ui"]["type"] == "period_input"
    query = json.loads(
        backend.requests_to(
            "POST",
            "/api/v1/agent-tools/transactions:query",
        )[0].content
    )
    assert query["start_date"] == "2025-01-01"
    assert query["end_date"] == "2025-12-31"
    backend.assert_all_responses_used()


@pytest.mark.asyncio
async def test_transaction_history_cancel_stops_without_query() -> None:
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
        {"message_id": "message_cancel_123"},
    )

    async with create_transaction_history_mock_testbed(
        backend,
        _config(),
        thread_id="thread_cancel",
        input_request_ids=["input_cancel_123"],
        now=NOW,
    ) as testbed:
        waiting = await testbed.start(
            message="거래내역 보여줘",
            request_id="req_cancel_123",
            chat_session_id="chat_123",
            execution_context_id="exec_123",
        )
        completed = await testbed.resume_input(
            agent_thread_id="thread_cancel",
            request_id="req_cancel_resume_123",
            chat_session_id="chat_123",
            execution_context_id="exec_123",
            input_request_id="input_cancel_123",
            value={
                "account_selection_outcome": "cancelled",
                "account_ids": [],
            },
        )

    assert waiting.status == "waiting"
    assert completed.status == "completed"
    assert not backend.requests_to(
        "POST",
        "/api/v1/agent-tools/transactions:query",
    )
    assert len(backend.requests_to("POST", "/api/v1/webhooks/agent")) == 1
    backend.assert_all_responses_used()


@pytest.mark.asyncio
async def test_transaction_history_no_accounts_emits_empty_state() -> None:
    backend = MockBackend()
    backend.add_success(
        "GET",
        "/api/v1/agent-tools/accounts",
        {
            "account_resolution_outcome": "no_accounts",
            "accounts": [],
            "account_ids": [],
        },
    )
    backend.add_success(
        "POST",
        "/api/v1/webhooks/agent",
        {"message_id": "message_no_accounts_123"},
    )

    async with create_transaction_history_mock_testbed(
        backend,
        _config(),
        thread_id="thread_no_accounts",
        now=NOW,
    ) as testbed:
        result = await testbed.start(
            message="생활비 계좌 거래내역 보여줘",
            request_id="req_no_accounts_123",
            chat_session_id="chat_123",
            execution_context_id="exec_123",
        )

    assert result.status == "completed"
    assert not backend.requests_to(
        "POST",
        "/api/v1/agent-tools/transactions:query",
    )
    event = json.loads(backend.requests[-1].content)
    assert event["metadata"]["step_id"] == "emit_transaction_accounts_empty"
    assert event["metadata"]["ui"]["payload"]["accounts"] == []
    backend.assert_all_responses_used()


@pytest.mark.asyncio
async def test_transaction_history_protocol_error_uses_common_error_ui() -> None:
    backend = MockBackend()
    _resolved_accounts(backend)
    backend.add_success(
        "POST",
        "/api/v1/agent-tools/transactions:query",
        {
            "transaction_results": [],
            "next_cursor": None,
        },
    )
    backend.add_success(
        "POST",
        "/api/v1/webhooks/agent",
        {"message_id": "message_protocol_error_123"},
    )

    async with create_transaction_history_mock_testbed(
        backend,
        _config(),
        thread_id="thread_protocol_error",
        now=NOW,
    ) as testbed:
        result = await testbed.start(
            message="생활비 계좌 거래내역 보여줘",
            request_id="req_protocol_error_123",
            chat_session_id="chat_123",
            execution_context_id="exec_123",
        )
        state = await testbed.state("thread_protocol_error")

    assert result.status == "completed"
    assert state["status"] == "workflow_failed"
    event = json.loads(backend.requests[-1].content)
    assert event["event_type"] == "error"
    assert "transaction_query_id" not in event["content"]
    backend.assert_all_responses_used()
