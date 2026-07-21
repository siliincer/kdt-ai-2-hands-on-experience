"""기간 거래 합계 Workflow의 Mock Backend End-to-End 테스트."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from pydantic import SecretStr

from agent.clients.backend import BackendClientConfig
from agent.testing.mock_backend import MockBackend
from agent.testing.period_amount_summary import (
    create_period_amount_summary_mock_testbed,
)
from agent.workflows.inquiry_support import extract_account_hint

NOW = datetime(2026, 7, 19, 3, 0, tzinfo=timezone.utc)


def test_shared_account_hint_preserves_alias_and_ignores_generic_account() -> None:
    assert extract_account_hint("생활비 계좌 거래내역") == "생활비 계좌"
    assert extract_account_hint("내 계좌 이번 달 지출") is None


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


def _summary(
    *,
    summary_type: str = "spending",
    total_amount: int = 158000,
) -> dict[str, object]:
    return {
        "summary_type": summary_type,
        "total_amount": total_amount,
        "transaction_count": 7,
        "currency": "KRW",
        "start_date": "2026-07-01",
        "end_date": "2026-07-19",
    }


@pytest.mark.asyncio
async def test_period_summary_extracts_demo_slots_and_uses_backend_total() -> None:
    backend = MockBackend()
    _resolved_accounts(backend)
    backend.add_success(
        "POST",
        "/api/v1/agent-tools/transactions:summary",
        {"summary_result": _summary()},
    )
    backend.add_success(
        "POST",
        "/api/v1/webhooks/agent",
        {"message_id": "message_summary_123"},
    )

    async with create_period_amount_summary_mock_testbed(
        backend,
        _config(),
        thread_id="thread_summary",
        now=NOW,
    ) as testbed:
        result = await testbed.start(
            message="이번 달 나 배민에서 얼마 썼어?",
            request_id="req_summary_123",
            chat_session_id="chat_123",
            execution_context_id="exec_123",
        )
        state = await testbed.state("thread_summary")
        exchanges = backend.exchange_timeline(include_payload=True)

    assert result.status == "completed"
    assert exchanges[0]["request"]["all_accounts_requested"] == "true"
    assert exchanges[1]["request"] == {
        "account_ids": ["acc_living"],
        "start_date": "2026-07-01",
        "end_date": "2026-07-19",
        "summary_type": "spending",
        "keyword": "배민",
    }
    assert state["data"]["summary_result"] == _summary()
    assert not backend.requests_to(
        "POST",
        "/api/v1/agent-tools/transactions:query",
    )

    event = json.loads(backend.requests[-1].content)
    payload = event["metadata"]["ui"]["payload"]
    assert event["metadata"]["ui"]["type"] == "amount_summary"
    assert payload == {
        "account_ids": ["acc_living"],
        "keyword": "배민",
        "start_date": "2026-07-01",
        "end_date": "2026-07-19",
        "summary_type": "spending",
        "total_amount": 158000,
        "transaction_count": 7,
        "currency": "KRW",
    }
    backend.assert_all_responses_used()


@pytest.mark.asyncio
async def test_period_summary_requests_type_and_uses_verified_resume() -> None:
    backend = MockBackend()
    _resolved_accounts(backend)
    backend.add_success(
        "POST",
        "/api/v1/webhooks/agent",
        {"message_id": "message_summary_type_123"},
    )
    backend.add_success(
        "POST",
        "/api/v1/agent-tools/transactions:summary",
        {
            "summary_result": _summary(
                summary_type="income",
                total_amount=3200000,
            )
        },
    )
    backend.add_success(
        "POST",
        "/api/v1/webhooks/agent",
        {"message_id": "message_income_result_123"},
    )

    async with create_period_amount_summary_mock_testbed(
        backend,
        _config(),
        thread_id="thread_summary_type",
        input_request_ids=["input_summary_type_123"],
        now=NOW,
    ) as testbed:
        waiting = await testbed.start(
            message="이번 달 합계 알려줘",
            request_id="req_summary_type_123",
            chat_session_id="chat_123",
            execution_context_id="exec_123",
        )
        completed = await testbed.resume_input(
            agent_thread_id="thread_summary_type",
            request_id="req_summary_type_resume_123",
            chat_session_id="chat_123",
            execution_context_id="exec_123",
            input_request_id="input_summary_type_123",
            value={
                "summary_type_selection_outcome": "selected",
                "summary_type": "income",
            },
        )

    assert waiting.status == "waiting"
    assert waiting.pending_interaction is not None
    assert waiting.pending_interaction["step_id"] == "request_summary_type"
    assert completed.status == "completed"
    option_event = json.loads(
        backend.requests_to("POST", "/api/v1/webhooks/agent")[0].content
    )
    assert option_event["metadata"]["ui"]["type"] == "option_select"
    query = json.loads(
        backend.requests_to(
            "POST",
            "/api/v1/agent-tools/transactions:summary",
        )[0].content
    )
    assert query["summary_type"] == "income"
    backend.assert_all_responses_used()


@pytest.mark.asyncio
async def test_period_summary_resumes_account_selection_without_requery() -> None:
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
        "/api/v1/agent-tools/transactions:summary",
        {"summary_result": _summary()},
    )
    backend.add_success(
        "POST",
        "/api/v1/webhooks/agent",
        {"message_id": "message_selected_result_123"},
    )

    async with create_period_amount_summary_mock_testbed(
        backend,
        _config(),
        thread_id="thread_summary_account",
        input_request_ids=["input_summary_account_123"],
        now=NOW,
    ) as testbed:
        waiting = await testbed.start(
            message="생활비 계좌 이번 달 지출 합계 알려줘",
            request_id="req_summary_account_123",
            chat_session_id="chat_123",
            execution_context_id="exec_123",
        )
        completed = await testbed.resume_input(
            agent_thread_id="thread_summary_account",
            request_id="req_summary_account_resume_123",
            chat_session_id="chat_123",
            execution_context_id="exec_123",
            input_request_id="input_summary_account_123",
            value={
                "account_selection_outcome": "selected",
                "account_ids": ["acc_002"],
            },
        )

    assert waiting.status == "waiting"
    assert completed.status == "completed"
    assert len(
        backend.requests_to("GET", "/api/v1/agent-tools/accounts")
    ) == 1
    query = json.loads(
        backend.requests_to(
            "POST",
            "/api/v1/agent-tools/transactions:summary",
        )[0].content
    )
    assert query["account_ids"] == ["acc_002"]
    backend.assert_all_responses_used()


@pytest.mark.asyncio
async def test_period_summary_requests_unresolved_period_then_resumes() -> None:
    backend = MockBackend()
    _resolved_accounts(backend)
    backend.add_success(
        "POST",
        "/api/v1/webhooks/agent",
        {"message_id": "message_period_123"},
    )
    backend.add_success(
        "POST",
        "/api/v1/agent-tools/transactions:summary",
        {
            "summary_result": {
                **_summary(),
                "start_date": "2025-01-01",
                "end_date": "2025-12-31",
            }
        },
    )
    backend.add_success(
        "POST",
        "/api/v1/webhooks/agent",
        {"message_id": "message_period_result_123"},
    )

    async with create_period_amount_summary_mock_testbed(
        backend,
        _config(),
        thread_id="thread_summary_period",
        input_request_ids=["input_summary_period_123"],
        now=NOW,
    ) as testbed:
        waiting = await testbed.start(
            message="작년 지출 합계 알려줘",
            request_id="req_summary_period_123",
            chat_session_id="chat_123",
            execution_context_id="exec_123",
        )
        completed = await testbed.resume_input(
            agent_thread_id="thread_summary_period",
            request_id="req_summary_period_resume_123",
            chat_session_id="chat_123",
            execution_context_id="exec_123",
            input_request_id="input_summary_period_123",
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
    query = json.loads(
        backend.requests_to(
            "POST",
            "/api/v1/agent-tools/transactions:summary",
        )[0].content
    )
    assert query["start_date"] == "2025-01-01"
    assert query["end_date"] == "2025-12-31"
    backend.assert_all_responses_used()


@pytest.mark.asyncio
async def test_period_summary_cancel_stops_without_financial_query() -> None:
    backend = MockBackend()
    _resolved_accounts(backend)
    backend.add_success(
        "POST",
        "/api/v1/webhooks/agent",
        {"message_id": "message_cancel_123"},
    )

    async with create_period_amount_summary_mock_testbed(
        backend,
        _config(),
        thread_id="thread_summary_cancel",
        input_request_ids=["input_summary_cancel_123"],
        now=NOW,
    ) as testbed:
        waiting = await testbed.start(
            message="이번 달 합계 알려줘",
            request_id="req_summary_cancel_123",
            chat_session_id="chat_123",
            execution_context_id="exec_123",
        )
        completed = await testbed.resume_input(
            agent_thread_id="thread_summary_cancel",
            request_id="req_summary_cancel_resume_123",
            chat_session_id="chat_123",
            execution_context_id="exec_123",
            input_request_id="input_summary_cancel_123",
            value={
                "summary_type_selection_outcome": "cancelled",
                "summary_type": None,
            },
        )

    assert waiting.status == "waiting"
    assert completed.status == "completed"
    assert not backend.requests_to(
        "POST",
        "/api/v1/agent-tools/transactions:summary",
    )
    assert len(backend.requests_to("POST", "/api/v1/webhooks/agent")) == 1
    backend.assert_all_responses_used()


@pytest.mark.asyncio
async def test_period_summary_no_accounts_emits_empty_state() -> None:
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

    async with create_period_amount_summary_mock_testbed(
        backend,
        _config(),
        thread_id="thread_summary_empty",
        now=NOW,
    ) as testbed:
        result = await testbed.start(
            message="이번 달 지출 합계 알려줘",
            request_id="req_summary_empty_123",
            chat_session_id="chat_123",
            execution_context_id="exec_123",
        )

    assert result.status == "completed"
    assert not backend.requests_to(
        "POST",
        "/api/v1/agent-tools/transactions:summary",
    )
    event = json.loads(backend.requests[-1].content)
    assert event["metadata"]["step_id"] == "emit_summary_accounts_empty"
    assert event["metadata"]["ui"]["payload"]["accounts"] == []
    backend.assert_all_responses_used()


@pytest.mark.asyncio
async def test_period_summary_protocol_error_uses_common_error_ui() -> None:
    backend = MockBackend()
    _resolved_accounts(backend)
    backend.add_success(
        "POST",
        "/api/v1/agent-tools/transactions:summary",
        {"summary_result": {"total_amount": 1000}},
    )
    backend.add_success(
        "POST",
        "/api/v1/webhooks/agent",
        {"message_id": "message_protocol_error_123"},
    )

    async with create_period_amount_summary_mock_testbed(
        backend,
        _config(),
        thread_id="thread_summary_protocol_error",
        now=NOW,
    ) as testbed:
        result = await testbed.start(
            message="이번 달 지출 합계 알려줘",
            request_id="req_summary_protocol_error_123",
            chat_session_id="chat_123",
            execution_context_id="exec_123",
        )
        state = await testbed.state("thread_summary_protocol_error")

    assert result.status == "completed"
    assert state["status"] == "workflow_failed"
    event = json.loads(backend.requests[-1].content)
    assert event["event_type"] == "error"
    assert "total_amount" not in event["content"]
    backend.assert_all_responses_used()
