"""타인송금 Workflow의 Mock Backend End-to-End 테스트."""

from __future__ import annotations

import json
import re

import pytest
from pydantic import SecretStr

from agent.clients.backend import BackendClientConfig
from agent.runtime.hitl import ExecutionResumeRequest
from agent.testing import MockBackend
from agent.testing.external_transfer import create_external_transfer_mock_testbed
from agent.workflows.external_transfer import (
    extract_external_transfer_slots_from_text,
)


def _config() -> BackendClientConfig:
    return BackendClientConfig(
        base_url="http://backend.test",
        agent_service_token=SecretStr("agent-service-token"),
        agent_webhook_secret=SecretStr("agent-webhook-secret"),
        retry_backoff_seconds=0,
    )


def _account(account_id: str, alias: str) -> dict[str, object]:
    return {
        "account_id": account_id,
        "bank_name": "신한은행",
        "account_alias": alias,
        "account_type": "checking",
        "masked_account_number": "110-***-123456",
        "currency": "KRW",
        "is_default": False,
        "status": "active",
    }


def _confirmation_view() -> dict[str, object]:
    return {
        "from_account": {
            "account_id": "acc_001",
            "bank_name": "신한은행",
            "account_alias": "생활비",
            "masked_account_number": "110-***-123456",
        },
        "recipient": {
            "name": "김철수",
            "bank_name": "국민은행",
            "masked_account_number": "222-***-456789",
        },
        "amount": 100000,
        "fee": 500,
        "total_debit": 100500,
        "currency": "KRW",
        "expires_at": "2026-07-17T10:05:00+09:00",
    }


@pytest.mark.asyncio
async def test_external_transfer_reference_workflow_completes_full_happy_path() -> None:
    backend = MockBackend()
    backend.add_success(
        "POST",
        "/api/v1/agent-tools/recipients:resolve",
        {"outcome": "resolved", "to_recipient_id": "recipient_001"},
    )
    backend.add_success(
        "GET",
        "/api/v1/agent-tools/accounts",
        {
            "account_resolution_outcome": "resolved",
            "accounts": [_account("acc_001", "생활비")],
            "account_ids": ["acc_001"],
        },
    )
    backend.add_success(
        "POST",
        "/api/v1/agent-tools/transfers/external:prepare",
        {
            "outcome": "ready_for_confirmation",
            "confirmation_id": "confirm_external_123",
            "confirmation_view": _confirmation_view(),
        },
    )
    backend.add_success(
        "POST", "/api/v1/webhooks/agent", {"message_id": "msg_approval"}
    )
    backend.add_success(
        "POST",
        "/api/v1/agent-tools/auth-contexts",
        {
            "outcome": "authentication_required",
            "auth_context_id": "auth_external_123",
            "auth_request_view": {
                "title": "본인 인증이 필요합니다.",
                "available_methods": ["biometric"],
                "expires_at": "2026-07-17T10:10:00+09:00",
            },
        },
    )
    backend.add_success("POST", "/api/v1/webhooks/agent", {"message_id": "msg_auth"})
    backend.add_success(
        "POST",
        "/api/v1/agent-tools/transfers/external",
        {
            "outcome": "completed",
            "transaction_id": "txn_external_123",
            "completed_at": "2026-07-17T10:11:00+09:00",
        },
    )
    backend.add_success("POST", "/api/v1/webhooks/agent", {"message_id": "msg_result"})

    async with create_external_transfer_mock_testbed(
        backend,
        _config(),
        thread_id="thread_external_happy",
    ) as testbed:
        waiting_for_approval = await testbed.start(
            message="김철수에게 10만원 송금해줘",
            request_id="req_1",
            chat_session_id="chat_1",
            execution_context_id="exec_1",
        )
        assert waiting_for_approval.status == "waiting"
        assert waiting_for_approval.pending_interaction is not None
        assert waiting_for_approval.pending_interaction["type"] == "approval"
        confirmation_id = waiting_for_approval.pending_interaction["confirmation_id"]
        assert confirmation_id == "confirm_external_123"

        waiting_for_auth = await testbed.resume(
            "thread_external_happy",
            ExecutionResumeRequest.model_validate(
                {
                    "request_id": "req_2",
                    "chat_session_id": "chat_1",
                    "execution_context_id": "exec_1",
                    "resume": {
                        "type": "approval",
                        "confirmation_id": confirmation_id,
                        "approval_outcome": "approved",
                    },
                }
            ),
        )
        assert waiting_for_auth.status == "waiting"
        assert waiting_for_auth.pending_interaction is not None
        assert waiting_for_auth.pending_interaction["type"] == "authentication"
        auth_context_id = waiting_for_auth.pending_interaction["auth_context_id"]
        assert auth_context_id == "auth_external_123"

        completed = await testbed.resume(
            "thread_external_happy",
            ExecutionResumeRequest.model_validate(
                {
                    "request_id": "req_3",
                    "chat_session_id": "chat_1",
                    "execution_context_id": "exec_1",
                    "resume": {
                        "type": "authentication",
                        "auth_context_id": auth_context_id,
                        "auth_status": "verified",
                    },
                }
            ),
        )
        state = await testbed.state("thread_external_happy")

    assert completed.status == "completed"
    assert state["data"]["transaction_id"] == "txn_external_123"

    result_event = json.loads(
        backend.requests_to("POST", "/api/v1/webhooks/agent")[-1].content
    )
    assert result_event["event_type"] == "component"
    assert result_event["metadata"]["step_id"] == "emit_external_transfer_result"
    assert (
        result_event["metadata"]["ui"]["payload"]["transaction_id"]
        == "txn_external_123"
    )

    prepare_request = json.loads(
        backend.requests_to("POST", "/api/v1/agent-tools/transfers/external:prepare")[
            0
        ].content
    )
    assert prepare_request["to_recipient_id"] == "recipient_001"
    assert "to_recipient_candidate_id" not in prepare_request

    backend.assert_all_responses_used()


@pytest.mark.asyncio
async def test_external_transfer_recipient_selection_required_then_cancelled() -> None:
    """수취인 후보가 여럿이면 선택 화면을 보여주고, 취소하면 추가 호출 없이 끝난다."""

    backend = MockBackend()
    backend.add_success(
        "POST",
        "/api/v1/agent-tools/recipients:resolve",
        {"outcome": "selection_required", "selection_reason": "multiple_matches"},
    )
    backend.add_success(
        "POST", "/api/v1/webhooks/agent", {"message_id": "msg_recipient_select"}
    )

    async with create_external_transfer_mock_testbed(
        backend, _config(), thread_id="thread_recipient_cancel"
    ) as testbed:
        waiting = await testbed.start(
            message="철수에게 송금해줘",
            request_id="req_1",
            chat_session_id="chat_1",
            execution_context_id="exec_1",
        )
        assert waiting.status == "waiting"
        assert waiting.pending_interaction is not None
        input_request_id = waiting.pending_interaction["input_request_id"]

        completed = await testbed.resume_input(
            agent_thread_id="thread_recipient_cancel",
            request_id="req_2",
            chat_session_id="chat_1",
            execution_context_id="exec_1",
            input_request_id=input_request_id,
            value={
                "recipient_selection_outcome": "cancelled",
                "to_recipient_id": None,
                "to_recipient_candidate_id": None,
            },
        )
        state = await testbed.state("thread_recipient_cancel")

    assert completed.status == "completed"
    assert state["status"] == "completed"
    backend.assert_all_responses_used()


@pytest.mark.asyncio
async def test_external_transfer_no_recipient_hint_skips_resolve_call() -> None:
    """이름 힌트가 없으면 resolve_recipient_hint 호출 없이 바로 선택 화면을 띄운다."""

    backend = MockBackend()
    backend.add_success(
        "POST", "/api/v1/webhooks/agent", {"message_id": "msg_no_hint_select"}
    )
    backend.add_success(
        "GET",
        "/api/v1/agent-tools/accounts",
        {
            "account_resolution_outcome": "resolved",
            "accounts": [_account("acc_001", "생활비")],
            "account_ids": ["acc_001"],
        },
    )
    backend.add_success(
        "POST",
        "/api/v1/agent-tools/transfers/external:prepare",
        {
            "outcome": "ready_for_confirmation",
            "confirmation_id": "confirm_no_hint",
            "confirmation_view": _confirmation_view(),
        },
    )
    backend.add_success(
        "POST", "/api/v1/webhooks/agent", {"message_id": "msg_approval_no_hint"}
    )

    async with create_external_transfer_mock_testbed(
        backend, _config(), thread_id="thread_no_hint"
    ) as testbed:
        waiting_selection = await testbed.start(
            message="10만원 송금해줘",
            request_id="req_1",
            chat_session_id="chat_1",
            execution_context_id="exec_1",
        )
        assert waiting_selection.pending_interaction is not None
        input_request_id = waiting_selection.pending_interaction["input_request_id"]

        waiting_approval = await testbed.resume_input(
            agent_thread_id="thread_no_hint",
            request_id="req_2",
            chat_session_id="chat_1",
            execution_context_id="exec_1",
            input_request_id=input_request_id,
            value={
                "recipient_selection_outcome": "selected",
                "to_recipient_id": "recipient_099",
                "to_recipient_candidate_id": None,
            },
        )

    assert waiting_approval.status == "waiting"
    assert waiting_approval.pending_interaction is not None
    assert waiting_approval.pending_interaction["type"] == "approval"
    selection_event = json.loads(
        backend.requests_to("POST", "/api/v1/webhooks/agent")[0].content
    )
    assert selection_event["metadata"]["step_id"] == "request_recipient_selection"
    assert (
        selection_event["metadata"]["ui"]["payload"]["recipient_selection_reason"]
        == "no_match"
    )
    assert backend.requests_to("POST", "/api/v1/agent-tools/recipients:resolve") == []
    backend.assert_all_responses_used()


@pytest.mark.asyncio
async def test_external_transfer_selection_required_for_recipient_and_account() -> None:
    """수취인·출금계좌 둘 다 선택이 필요해도 순서대로 처리해 완료한다."""

    backend = MockBackend()
    backend.add_success(
        "POST",
        "/api/v1/agent-tools/recipients:resolve",
        {"outcome": "selection_required", "selection_reason": "multiple_matches"},
    )
    backend.add_success(
        "POST", "/api/v1/webhooks/agent", {"message_id": "msg_recipient_select_2"}
    )
    backend.add_success(
        "GET",
        "/api/v1/agent-tools/accounts",
        {
            "account_resolution_outcome": "selection_required",
            "accounts": [_account("acc_001", "생활비"), _account("acc_002", "저축")],
            "account_ids": [],
        },
    )
    backend.add_success(
        "POST", "/api/v1/webhooks/agent", {"message_id": "msg_from_select"}
    )
    backend.add_success(
        "POST",
        "/api/v1/agent-tools/transfers/external:prepare",
        {
            "outcome": "ready_for_confirmation",
            "confirmation_id": "confirm_both_select",
            "confirmation_view": _confirmation_view(),
        },
    )
    backend.add_success(
        "POST", "/api/v1/webhooks/agent", {"message_id": "msg_approval_both"}
    )
    backend.add_success(
        "POST",
        "/api/v1/agent-tools/auth-contexts",
        {
            "outcome": "authentication_required",
            "auth_context_id": "auth_both",
            "auth_request_view": {
                "title": "본인 인증이 필요합니다.",
                "available_methods": ["biometric"],
                "expires_at": "2026-07-17T10:10:00+09:00",
            },
        },
    )
    backend.add_success(
        "POST", "/api/v1/webhooks/agent", {"message_id": "msg_auth_both"}
    )
    backend.add_success(
        "POST",
        "/api/v1/agent-tools/transfers/external",
        {
            "outcome": "completed",
            "transaction_id": "txn_both",
            "completed_at": "2026-07-17T10:11:00+09:00",
        },
    )
    backend.add_success(
        "POST", "/api/v1/webhooks/agent", {"message_id": "msg_result_both"}
    )

    async with create_external_transfer_mock_testbed(
        backend, _config(), thread_id="thread_both_select"
    ) as testbed:
        waiting_recipient = await testbed.start(
            message="철수에게 10만원 보내줘",
            request_id="req_1",
            chat_session_id="chat_1",
            execution_context_id="exec_1",
        )
        assert waiting_recipient.pending_interaction is not None
        recipient_input_id = waiting_recipient.pending_interaction["input_request_id"]

        waiting_from = await testbed.resume_input(
            agent_thread_id="thread_both_select",
            request_id="req_2",
            chat_session_id="chat_1",
            execution_context_id="exec_1",
            input_request_id=recipient_input_id,
            value={
                "recipient_selection_outcome": "selected",
                "to_recipient_id": None,
                "to_recipient_candidate_id": "candidate_555",
            },
        )
        assert waiting_from.pending_interaction is not None
        from_input_id = waiting_from.pending_interaction["input_request_id"]

        waiting_approval = await testbed.resume_input(
            agent_thread_id="thread_both_select",
            request_id="req_3",
            chat_session_id="chat_1",
            execution_context_id="exec_1",
            input_request_id=from_input_id,
            value={"account_selection_outcome": "selected", "account_ids": ["acc_001"]},
        )
        assert waiting_approval.pending_interaction is not None
        confirmation_id = waiting_approval.pending_interaction["confirmation_id"]

        waiting_auth = await testbed.resume(
            "thread_both_select",
            ExecutionResumeRequest.model_validate(
                {
                    "request_id": "req_4",
                    "chat_session_id": "chat_1",
                    "execution_context_id": "exec_1",
                    "resume": {
                        "type": "approval",
                        "confirmation_id": confirmation_id,
                        "approval_outcome": "approved",
                    },
                }
            ),
        )
        assert waiting_auth.pending_interaction is not None
        auth_context_id = waiting_auth.pending_interaction["auth_context_id"]

        completed = await testbed.resume(
            "thread_both_select",
            ExecutionResumeRequest.model_validate(
                {
                    "request_id": "req_5",
                    "chat_session_id": "chat_1",
                    "execution_context_id": "exec_1",
                    "resume": {
                        "type": "authentication",
                        "auth_context_id": auth_context_id,
                        "auth_status": "verified",
                    },
                }
            ),
        )
        state = await testbed.state("thread_both_select")

    assert completed.status == "completed"
    assert state["data"]["to_recipient_candidate_id"] == "candidate_555"
    assert state["data"]["from_account_id"] == "acc_001"
    prepare_request = json.loads(
        backend.requests_to("POST", "/api/v1/agent-tools/transfers/external:prepare")[
            0
        ].content
    )
    assert prepare_request["to_recipient_candidate_id"] == "candidate_555"
    assert "to_recipient_id" not in prepare_request
    backend.assert_all_responses_used()


@pytest.mark.asyncio
async def test_external_transfer_amount_missing_then_submitted() -> None:
    """금액이 없으면 되묻고, 제출된 금액으로 정상 완료까지 이어간다.

    차단(blocked) 케이스는 별도로 test_external_transfer_blocked_at_prepare가
    이미 다루므로 여기서는 엮지 않는다 — 이 시나리오의 관심사는 "금액
    재입력"이지 차단이 아니다.
    """

    backend = MockBackend()
    backend.add_success(
        "POST",
        "/api/v1/agent-tools/recipients:resolve",
        {"outcome": "resolved", "to_recipient_id": "recipient_001"},
    )
    backend.add_success(
        "GET",
        "/api/v1/agent-tools/accounts",
        {
            "account_resolution_outcome": "resolved",
            "accounts": [_account("acc_001", "생활비")],
            "account_ids": ["acc_001"],
        },
    )
    backend.add_success("POST", "/api/v1/webhooks/agent", {"message_id": "msg_amount"})
    backend.add_success(
        "POST",
        "/api/v1/agent-tools/transfers/external:prepare",
        {
            "outcome": "ready_for_confirmation",
            "confirmation_id": "confirm_amount_missing",
            "confirmation_view": _confirmation_view(),
        },
    )
    backend.add_success(
        "POST", "/api/v1/webhooks/agent", {"message_id": "msg_approval_amount"}
    )
    backend.add_success(
        "POST",
        "/api/v1/agent-tools/auth-contexts",
        {
            "outcome": "authentication_required",
            "auth_context_id": "auth_amount_missing",
            "auth_request_view": {
                "title": "본인 인증이 필요합니다.",
                "available_methods": ["biometric"],
                "expires_at": "2026-07-17T10:10:00+09:00",
            },
        },
    )
    backend.add_success(
        "POST", "/api/v1/webhooks/agent", {"message_id": "msg_auth_amount"}
    )
    backend.add_success(
        "POST",
        "/api/v1/agent-tools/transfers/external",
        {
            "outcome": "completed",
            "transaction_id": "txn_amount_missing",
            "completed_at": "2026-07-17T10:11:00+09:00",
        },
    )
    backend.add_success(
        "POST", "/api/v1/webhooks/agent", {"message_id": "msg_result_amount"}
    )

    async with create_external_transfer_mock_testbed(
        backend, _config(), thread_id="thread_amount_missing"
    ) as testbed:
        waiting_amount = await testbed.start(
            message="철수에게 송금해줘",
            request_id="req_1",
            chat_session_id="chat_1",
            execution_context_id="exec_1",
        )
        assert waiting_amount.pending_interaction is not None
        input_request_id = waiting_amount.pending_interaction["input_request_id"]

        waiting_approval = await testbed.resume_input(
            agent_thread_id="thread_amount_missing",
            request_id="req_2",
            chat_session_id="chat_1",
            execution_context_id="exec_1",
            input_request_id=input_request_id,
            value={"amount_input_outcome": "submitted", "amount": 70000},
        )
        assert waiting_approval.pending_interaction is not None
        confirmation_id = waiting_approval.pending_interaction["confirmation_id"]

        waiting_auth = await testbed.resume(
            "thread_amount_missing",
            ExecutionResumeRequest.model_validate(
                {
                    "request_id": "req_3",
                    "chat_session_id": "chat_1",
                    "execution_context_id": "exec_1",
                    "resume": {
                        "type": "approval",
                        "confirmation_id": confirmation_id,
                        "approval_outcome": "approved",
                    },
                }
            ),
        )
        assert waiting_auth.pending_interaction is not None
        auth_context_id = waiting_auth.pending_interaction["auth_context_id"]

        completed = await testbed.resume(
            "thread_amount_missing",
            ExecutionResumeRequest.model_validate(
                {
                    "request_id": "req_4",
                    "chat_session_id": "chat_1",
                    "execution_context_id": "exec_1",
                    "resume": {
                        "type": "authentication",
                        "auth_context_id": auth_context_id,
                        "auth_status": "verified",
                    },
                }
            ),
        )
        state = await testbed.state("thread_amount_missing")

    assert completed.status == "completed"
    assert state["status"] == "completed"
    assert state["data"]["transaction_id"] == "txn_amount_missing"
    prepare_request = json.loads(
        backend.requests_to("POST", "/api/v1/agent-tools/transfers/external:prepare")[
            0
        ].content
    )
    assert prepare_request["amount"] == 70000
    backend.assert_all_responses_used()


@pytest.mark.asyncio
async def test_external_transfer_correction_single_target_auto_routes() -> None:
    """수정 대상이 하나면 선택 화면 없이 바로 그 항목 재입력으로 간다."""

    backend = MockBackend()
    backend.add_success(
        "POST",
        "/api/v1/agent-tools/recipients:resolve",
        {"outcome": "resolved", "to_recipient_id": "recipient_001"},
    )
    backend.add_success(
        "GET",
        "/api/v1/agent-tools/accounts",
        {
            "account_resolution_outcome": "resolved",
            "accounts": [_account("acc_001", "생활비")],
            "account_ids": ["acc_001"],
        },
    )
    backend.add_success(
        "POST",
        "/api/v1/agent-tools/transfers/external:prepare",
        {
            "outcome": "correction_required",
            "reason": "insufficient_balance",
            "correction_view": {
                "title": "금액을 변경해 주세요.",
                "allowed_change_targets": ["amount"],
            },
        },
    )
    backend.add_success(
        "POST", "/api/v1/webhooks/agent", {"message_id": "msg_amount_2"}
    )

    async with create_external_transfer_mock_testbed(
        backend, _config(), thread_id="thread_correction_single"
    ) as testbed:
        waiting = await testbed.start(
            message="철수에게 10만원 보내줘",
            request_id="req_1",
            chat_session_id="chat_1",
            execution_context_id="exec_1",
        )

    assert waiting.status == "waiting"
    event = json.loads(backend.requests_to("POST", "/api/v1/webhooks/agent")[0].content)
    assert event["metadata"]["step_id"] == "request_external_transfer_amount"
    backend.assert_all_responses_used()


@pytest.mark.asyncio
async def test_external_transfer_correction_multiple_targets_user_selects() -> None:
    """수정 대상이 여럿이면 선택 화면을 먼저 보여준다(수취인 선택 시 초기화면 복귀)."""

    backend = MockBackend()
    backend.add_success(
        "POST",
        "/api/v1/agent-tools/recipients:resolve",
        {"outcome": "resolved", "to_recipient_id": "recipient_001"},
    )
    backend.add_success(
        "GET",
        "/api/v1/agent-tools/accounts",
        {
            "account_resolution_outcome": "resolved",
            "accounts": [_account("acc_001", "생활비")],
            "account_ids": ["acc_001"],
        },
    )
    backend.add_success(
        "POST",
        "/api/v1/agent-tools/transfers/external:prepare",
        {
            "outcome": "correction_required",
            "reason": "recipient_account_closed",
            "correction_view": {
                "title": "받는 분 또는 금액을 변경해 주세요.",
                "allowed_change_targets": ["recipient", "amount"],
            },
        },
    )
    backend.add_success(
        "POST", "/api/v1/webhooks/agent", {"message_id": "msg_correction_select"}
    )
    backend.add_success(
        "POST", "/api/v1/webhooks/agent", {"message_id": "msg_recipient_reselect"}
    )

    async with create_external_transfer_mock_testbed(
        backend, _config(), thread_id="thread_correction_multi"
    ) as testbed:
        waiting_selection = await testbed.start(
            message="철수에게 10만원 보내줘",
            request_id="req_1",
            chat_session_id="chat_1",
            execution_context_id="exec_1",
        )
        assert waiting_selection.pending_interaction is not None
        assert waiting_selection.pending_interaction["type"] == "input"
        input_request_id = waiting_selection.pending_interaction["input_request_id"]

        waiting_recipient = await testbed.resume_input(
            agent_thread_id="thread_correction_multi",
            request_id="req_2",
            chat_session_id="chat_1",
            execution_context_id="exec_1",
            input_request_id=input_request_id,
            value={
                "correction_selection_outcome": "selected",
                "change_target": "recipient",
            },
        )

    assert waiting_recipient.status == "waiting"
    events = [
        json.loads(r.content)
        for r in backend.requests_to("POST", "/api/v1/webhooks/agent")
    ]
    assert events[0]["metadata"]["step_id"] == "request_external_transfer_correction"
    assert events[1]["metadata"]["step_id"] == "request_recipient_selection"
    backend.assert_all_responses_used()


@pytest.mark.asyncio
async def test_external_transfer_blocked_at_prepare() -> None:
    """Prepare가 blocked를 반환하면 재시도 없이 차단 안내로 끝난다."""

    backend = MockBackend()
    backend.add_success(
        "POST",
        "/api/v1/agent-tools/recipients:resolve",
        {"outcome": "resolved", "to_recipient_id": "recipient_001"},
    )
    backend.add_success(
        "GET",
        "/api/v1/agent-tools/accounts",
        {
            "account_resolution_outcome": "resolved",
            "accounts": [_account("acc_001", "생활비")],
            "account_ids": ["acc_001"],
        },
    )
    backend.add_success(
        "POST",
        "/api/v1/agent-tools/transfers/external:prepare",
        {
            "outcome": "blocked",
            "reason": "transfer_restricted",
            "blocked_view": {
                "title": "송금을 진행할 수 없습니다.",
                "description": "고객센터에 문의해 주세요.",
            },
        },
    )
    backend.add_success(
        "POST", "/api/v1/webhooks/agent", {"message_id": "msg_blocked_2"}
    )

    async with create_external_transfer_mock_testbed(
        backend, _config(), thread_id="thread_blocked"
    ) as testbed:
        completed = await testbed.start(
            message="철수에게 10만원 보내줘",
            request_id="req_1",
            chat_session_id="chat_1",
            execution_context_id="exec_1",
        )
        state = await testbed.state("thread_blocked")

    assert completed.status == "completed"
    assert state["status"] == "workflow_failed"
    event = json.loads(backend.requests_to("POST", "/api/v1/webhooks/agent")[0].content)
    assert event["metadata"]["step_id"] == "emit_external_transfer_blocked"
    assert event["metadata"]["ui"]["payload"]["title"] == "송금을 진행할 수 없습니다."
    backend.assert_all_responses_used()


@pytest.mark.asyncio
async def test_external_transfer_cancel_at_approval() -> None:
    """승인 화면에서 취소하면 인증·실행 없이 바로 끝난다."""

    backend = MockBackend()
    backend.add_success(
        "POST",
        "/api/v1/agent-tools/recipients:resolve",
        {"outcome": "resolved", "to_recipient_id": "recipient_001"},
    )
    backend.add_success(
        "GET",
        "/api/v1/agent-tools/accounts",
        {
            "account_resolution_outcome": "resolved",
            "accounts": [_account("acc_001", "생활비")],
            "account_ids": ["acc_001"],
        },
    )
    backend.add_success(
        "POST",
        "/api/v1/agent-tools/transfers/external:prepare",
        {
            "outcome": "ready_for_confirmation",
            "confirmation_id": "confirm_cancel",
            "confirmation_view": _confirmation_view(),
        },
    )
    backend.add_success(
        "POST", "/api/v1/webhooks/agent", {"message_id": "msg_approval_2"}
    )

    async with create_external_transfer_mock_testbed(
        backend, _config(), thread_id="thread_cancel_approval"
    ) as testbed:
        waiting = await testbed.start(
            message="철수에게 10만원 보내줘",
            request_id="req_1",
            chat_session_id="chat_1",
            execution_context_id="exec_1",
        )
        assert waiting.pending_interaction is not None
        confirmation_id = waiting.pending_interaction["confirmation_id"]

        completed = await testbed.resume(
            "thread_cancel_approval",
            ExecutionResumeRequest.model_validate(
                {
                    "request_id": "req_2",
                    "chat_session_id": "chat_1",
                    "execution_context_id": "exec_1",
                    "resume": {
                        "type": "approval",
                        "confirmation_id": confirmation_id,
                        "approval_outcome": "cancelled",
                    },
                }
            ),
        )
        state = await testbed.state("thread_cancel_approval")

    assert completed.status == "completed"
    assert state["status"] == "completed"
    backend.assert_all_responses_used()


@pytest.mark.asyncio
async def test_external_transfer_auth_retry_then_verified() -> None:
    """인증 실패 후 재시도를 선택하면 새 Auth Context로 다시 인증한다."""

    backend = MockBackend()
    backend.add_success(
        "POST",
        "/api/v1/agent-tools/recipients:resolve",
        {"outcome": "resolved", "to_recipient_id": "recipient_001"},
    )
    backend.add_success(
        "GET",
        "/api/v1/agent-tools/accounts",
        {
            "account_resolution_outcome": "resolved",
            "accounts": [_account("acc_001", "생활비")],
            "account_ids": ["acc_001"],
        },
    )
    backend.add_success(
        "POST",
        "/api/v1/agent-tools/transfers/external:prepare",
        {
            "outcome": "ready_for_confirmation",
            "confirmation_id": "confirm_retry",
            "confirmation_view": _confirmation_view(),
        },
    )
    backend.add_success(
        "POST", "/api/v1/webhooks/agent", {"message_id": "msg_approval_3"}
    )
    backend.add_success(
        "POST",
        "/api/v1/agent-tools/auth-contexts",
        {
            "outcome": "authentication_required",
            "auth_context_id": "auth_attempt_1",
            "auth_request_view": {
                "title": "본인 인증이 필요합니다.",
                "available_methods": ["biometric"],
                "expires_at": "2026-07-17T10:10:00+09:00",
            },
        },
    )
    backend.add_success("POST", "/api/v1/webhooks/agent", {"message_id": "msg_auth_1"})
    backend.add_success(
        "POST", "/api/v1/webhooks/agent", {"message_id": "msg_auth_retry"}
    )
    backend.add_success(
        "POST",
        "/api/v1/agent-tools/auth-contexts",
        {
            "outcome": "authentication_required",
            "auth_context_id": "auth_attempt_2",
            "auth_request_view": {
                "title": "본인 인증이 필요합니다.",
                "available_methods": ["biometric"],
                "expires_at": "2026-07-17T10:20:00+09:00",
            },
        },
    )
    backend.add_success("POST", "/api/v1/webhooks/agent", {"message_id": "msg_auth_2"})
    backend.add_success(
        "POST",
        "/api/v1/agent-tools/transfers/external",
        {
            "outcome": "completed",
            "transaction_id": "txn_retry",
            "completed_at": "2026-07-17T10:21:00+09:00",
        },
    )
    backend.add_success(
        "POST", "/api/v1/webhooks/agent", {"message_id": "msg_result_2"}
    )

    async with create_external_transfer_mock_testbed(
        backend, _config(), thread_id="thread_auth_retry"
    ) as testbed:
        waiting_approval = await testbed.start(
            message="철수에게 10만원 보내줘",
            request_id="req_1",
            chat_session_id="chat_1",
            execution_context_id="exec_1",
        )
        assert waiting_approval.pending_interaction is not None
        confirmation_id = waiting_approval.pending_interaction["confirmation_id"]

        waiting_auth_1 = await testbed.resume(
            "thread_auth_retry",
            ExecutionResumeRequest.model_validate(
                {
                    "request_id": "req_2",
                    "chat_session_id": "chat_1",
                    "execution_context_id": "exec_1",
                    "resume": {
                        "type": "approval",
                        "confirmation_id": confirmation_id,
                        "approval_outcome": "approved",
                    },
                }
            ),
        )
        assert waiting_auth_1.pending_interaction is not None
        auth_context_id_1 = waiting_auth_1.pending_interaction["auth_context_id"]
        assert auth_context_id_1 == "auth_attempt_1"

        waiting_retry = await testbed.resume(
            "thread_auth_retry",
            ExecutionResumeRequest.model_validate(
                {
                    "request_id": "req_3",
                    "chat_session_id": "chat_1",
                    "execution_context_id": "exec_1",
                    "resume": {
                        "type": "authentication",
                        "auth_context_id": auth_context_id_1,
                        "auth_status": "failed",
                    },
                }
            ),
        )
        assert waiting_retry.pending_interaction is not None
        retry_input_id = waiting_retry.pending_interaction["input_request_id"]

        waiting_auth_2 = await testbed.resume_input(
            agent_thread_id="thread_auth_retry",
            request_id="req_4",
            chat_session_id="chat_1",
            execution_context_id="exec_1",
            input_request_id=retry_input_id,
            value={"auth_retry_outcome": "retry"},
        )
        assert waiting_auth_2.pending_interaction is not None
        auth_context_id_2 = waiting_auth_2.pending_interaction["auth_context_id"]
        assert auth_context_id_2 == "auth_attempt_2"

        completed = await testbed.resume(
            "thread_auth_retry",
            ExecutionResumeRequest.model_validate(
                {
                    "request_id": "req_5",
                    "chat_session_id": "chat_1",
                    "execution_context_id": "exec_1",
                    "resume": {
                        "type": "authentication",
                        "auth_context_id": auth_context_id_2,
                        "auth_status": "verified",
                    },
                }
            ),
        )

    assert completed.status == "completed"
    assert len(backend.requests_to("POST", "/api/v1/agent-tools/auth-contexts")) == 2
    backend.assert_all_responses_used()


@pytest.mark.asyncio
async def test_external_transfer_reauthentication_required_at_execute() -> None:
    """Execute가 reauthentication_required면 Prepare·승인 없이 인증만 다시 한다."""

    backend = MockBackend()
    backend.add_success(
        "POST",
        "/api/v1/agent-tools/recipients:resolve",
        {"outcome": "resolved", "to_recipient_id": "recipient_001"},
    )
    backend.add_success(
        "GET",
        "/api/v1/agent-tools/accounts",
        {
            "account_resolution_outcome": "resolved",
            "accounts": [_account("acc_001", "생활비")],
            "account_ids": ["acc_001"],
        },
    )
    backend.add_success(
        "POST",
        "/api/v1/agent-tools/transfers/external:prepare",
        {
            "outcome": "ready_for_confirmation",
            "confirmation_id": "confirm_reauth",
            "confirmation_view": _confirmation_view(),
        },
    )
    backend.add_success(
        "POST", "/api/v1/webhooks/agent", {"message_id": "msg_approval_4"}
    )
    backend.add_success(
        "POST",
        "/api/v1/agent-tools/auth-contexts",
        {
            "outcome": "authentication_required",
            "auth_context_id": "auth_first",
            "auth_request_view": {
                "title": "본인 인증이 필요합니다.",
                "available_methods": ["biometric"],
                "expires_at": "2026-07-17T10:10:00+09:00",
            },
        },
    )
    backend.add_success("POST", "/api/v1/webhooks/agent", {"message_id": "msg_auth_3"})
    backend.add_success(
        "POST",
        "/api/v1/agent-tools/transfers/external",
        {
            "outcome": "reauthentication_required",
            "reason": "auth_context_expired",
        },
    )
    backend.add_success(
        "POST",
        "/api/v1/agent-tools/auth-contexts",
        {
            "outcome": "authentication_required",
            "auth_context_id": "auth_second",
            "auth_request_view": {
                "title": "본인 인증이 필요합니다.",
                "available_methods": ["biometric"],
                "expires_at": "2026-07-17T10:20:00+09:00",
            },
        },
    )
    backend.add_success("POST", "/api/v1/webhooks/agent", {"message_id": "msg_auth_4"})
    backend.add_success(
        "POST",
        "/api/v1/agent-tools/transfers/external",
        {
            "outcome": "completed",
            "transaction_id": "txn_reauth",
            "completed_at": "2026-07-17T10:21:00+09:00",
        },
    )
    backend.add_success(
        "POST", "/api/v1/webhooks/agent", {"message_id": "msg_result_3"}
    )

    async with create_external_transfer_mock_testbed(
        backend, _config(), thread_id="thread_reauth"
    ) as testbed:
        waiting_approval = await testbed.start(
            message="철수에게 10만원 보내줘",
            request_id="req_1",
            chat_session_id="chat_1",
            execution_context_id="exec_1",
        )
        assert waiting_approval.pending_interaction is not None
        confirmation_id = waiting_approval.pending_interaction["confirmation_id"]

        waiting_auth_1 = await testbed.resume(
            "thread_reauth",
            ExecutionResumeRequest.model_validate(
                {
                    "request_id": "req_2",
                    "chat_session_id": "chat_1",
                    "execution_context_id": "exec_1",
                    "resume": {
                        "type": "approval",
                        "confirmation_id": confirmation_id,
                        "approval_outcome": "approved",
                    },
                }
            ),
        )
        assert waiting_auth_1.pending_interaction is not None
        auth_context_id_1 = waiting_auth_1.pending_interaction["auth_context_id"]

        waiting_auth_2 = await testbed.resume(
            "thread_reauth",
            ExecutionResumeRequest.model_validate(
                {
                    "request_id": "req_3",
                    "chat_session_id": "chat_1",
                    "execution_context_id": "exec_1",
                    "resume": {
                        "type": "authentication",
                        "auth_context_id": auth_context_id_1,
                        "auth_status": "verified",
                    },
                }
            ),
        )
        assert waiting_auth_2.pending_interaction is not None
        auth_context_id_2 = waiting_auth_2.pending_interaction["auth_context_id"]
        assert auth_context_id_2 == "auth_second"

        completed = await testbed.resume(
            "thread_reauth",
            ExecutionResumeRequest.model_validate(
                {
                    "request_id": "req_4",
                    "chat_session_id": "chat_1",
                    "execution_context_id": "exec_1",
                    "resume": {
                        "type": "authentication",
                        "auth_context_id": auth_context_id_2,
                        "auth_status": "verified",
                    },
                }
            ),
        )

    assert completed.status == "completed"
    assert (
        len(
            backend.requests_to(
                "POST", "/api/v1/agent-tools/transfers/external:prepare"
            )
        )
        == 1
    )
    assert (
        len(backend.requests_to("POST", "/api/v1/agent-tools/transfers/external")) == 2
    )
    backend.assert_all_responses_used()


@pytest.mark.asyncio
async def test_external_transfer_no_accounts_empty() -> None:
    """출금 가능 계좌가 없으면 빈 상태 안내로 끝난다."""

    backend = MockBackend()
    backend.add_success(
        "POST",
        "/api/v1/agent-tools/recipients:resolve",
        {"outcome": "resolved", "to_recipient_id": "recipient_001"},
    )
    backend.add_success(
        "GET",
        "/api/v1/agent-tools/accounts",
        {
            "account_resolution_outcome": "no_accounts",
            "accounts": [],
            "account_ids": [],
        },
    )
    backend.add_success("POST", "/api/v1/webhooks/agent", {"message_id": "msg_empty"})

    async with create_external_transfer_mock_testbed(
        backend, _config(), thread_id="thread_no_accounts"
    ) as testbed:
        completed = await testbed.start(
            message="철수에게 송금해줘",
            request_id="req_1",
            chat_session_id="chat_1",
            execution_context_id="exec_1",
        )

    assert completed.status == "completed"
    event = json.loads(backend.requests_to("POST", "/api/v1/webhooks/agent")[0].content)
    assert event["metadata"]["step_id"] == "emit_external_from_accounts_empty"
    backend.assert_all_responses_used()


def test_extract_external_transfer_slots_reads_from_account_hint() -> None:
    """출금 계좌 표현이 있으면 수취인 이름과 별개로 from_account_hint를 뽑는다."""

    with_hint = extract_external_transfer_slots_from_text(
        "국민은행 계좌에서 철수에게 10만원 보내줘"
    )
    assert with_hint["recipient_name_hint"] == "철수"
    assert with_hint["from_account_hint"] == "국민은행 계좌"
    assert with_hint["amount"] == 100000

    # 수취인 이름(에게/한테 앞)은 계좌 힌트로 잘못 잡히지 않는다.
    without_hint = extract_external_transfer_slots_from_text("철수에게 10만원 보내줘")
    assert without_hint["recipient_name_hint"] == "철수"
    assert without_hint["from_account_hint"] is None


@pytest.mark.asyncio
async def test_external_transfer_from_account_hint_reaches_backend() -> None:
    """추출한 from_account_hint가 출금 계좌 확인 API의 account_hint로 전달된다."""

    backend = MockBackend()
    backend.add_success(
        "POST",
        "/api/v1/agent-tools/recipients:resolve",
        {"outcome": "resolved", "to_recipient_id": "recipient_001"},
    )
    backend.add_success(
        "GET",
        "/api/v1/agent-tools/accounts",
        {
            "account_resolution_outcome": "resolved",
            "accounts": [_account("acc_001", "국민 통장")],
            "account_ids": ["acc_001"],
        },
    )
    backend.add_success(
        "POST",
        "/api/v1/agent-tools/transfers/external:prepare",
        {
            "outcome": "ready_for_confirmation",
            "confirmation_id": "confirm_hint",
            "confirmation_view": _confirmation_view(),
        },
    )
    backend.add_success(
        "POST", "/api/v1/webhooks/agent", {"message_id": "msg_approval_hint"}
    )

    async with create_external_transfer_mock_testbed(
        backend, _config(), thread_id="thread_from_hint"
    ) as testbed:
        waiting = await testbed.start(
            message="국민은행 계좌에서 철수에게 10만원 보내줘",
            request_id="req_1",
            chat_session_id="chat_1",
            execution_context_id="exec_1",
        )
        state = await testbed.state("thread_from_hint")

    assert waiting.status == "waiting"
    assert waiting.pending_interaction is not None
    assert waiting.pending_interaction["type"] == "approval"

    accounts_request = backend.requests_to("GET", "/api/v1/agent-tools/accounts")[0]
    assert accounts_request.url.params.get("account_hint") == "국민은행 계좌"
    assert state["data"]["from_account_hint"] == "국민은행 계좌"
    backend.assert_all_responses_used()


@pytest.mark.asyncio
async def test_external_transfer_correction_required_at_execute() -> None:
    """Execute가 correction_required면 정정 라우팅을 거쳐 재입력으로 돌아간다."""

    backend = MockBackend()
    backend.add_success(
        "POST",
        "/api/v1/agent-tools/recipients:resolve",
        {"outcome": "resolved", "to_recipient_id": "recipient_001"},
    )
    backend.add_success(
        "GET",
        "/api/v1/agent-tools/accounts",
        {
            "account_resolution_outcome": "resolved",
            "accounts": [_account("acc_001", "생활비")],
            "account_ids": ["acc_001"],
        },
    )
    backend.add_success(
        "POST",
        "/api/v1/agent-tools/transfers/external:prepare",
        {
            "outcome": "ready_for_confirmation",
            "confirmation_id": "confirm_exec_correction",
            "confirmation_view": _confirmation_view(),
        },
    )
    backend.add_success(
        "POST", "/api/v1/webhooks/agent", {"message_id": "msg_approval_exec"}
    )
    backend.add_success(
        "POST",
        "/api/v1/agent-tools/auth-contexts",
        {
            "outcome": "authentication_required",
            "auth_context_id": "auth_exec",
            "auth_request_view": {
                "title": "본인 인증이 필요합니다.",
                "available_methods": ["biometric"],
                "expires_at": "2026-07-17T10:10:00+09:00",
            },
        },
    )
    backend.add_success(
        "POST", "/api/v1/webhooks/agent", {"message_id": "msg_auth_exec"}
    )
    backend.add_success(
        "POST",
        "/api/v1/agent-tools/transfers/external",
        {
            "outcome": "correction_required",
            "reason": "limit_exceeded",
            "correction_view": {
                "title": "금액을 변경해 주세요.",
                "allowed_change_targets": ["amount"],
            },
        },
    )
    backend.add_success(
        "POST", "/api/v1/webhooks/agent", {"message_id": "msg_amount_reinput"}
    )

    async with create_external_transfer_mock_testbed(
        backend, _config(), thread_id="thread_exec_correction"
    ) as testbed:
        waiting_approval = await testbed.start(
            message="철수에게 10만원 보내줘",
            request_id="req_1",
            chat_session_id="chat_1",
            execution_context_id="exec_1",
        )
        assert waiting_approval.pending_interaction is not None
        confirmation_id = waiting_approval.pending_interaction["confirmation_id"]

        waiting_auth = await testbed.resume(
            "thread_exec_correction",
            ExecutionResumeRequest.model_validate(
                {
                    "request_id": "req_2",
                    "chat_session_id": "chat_1",
                    "execution_context_id": "exec_1",
                    "resume": {
                        "type": "approval",
                        "confirmation_id": confirmation_id,
                        "approval_outcome": "approved",
                    },
                }
            ),
        )
        assert waiting_auth.pending_interaction is not None
        auth_context_id = waiting_auth.pending_interaction["auth_context_id"]

        waiting_amount = await testbed.resume(
            "thread_exec_correction",
            ExecutionResumeRequest.model_validate(
                {
                    "request_id": "req_3",
                    "chat_session_id": "chat_1",
                    "execution_context_id": "exec_1",
                    "resume": {
                        "type": "authentication",
                        "auth_context_id": auth_context_id,
                        "auth_status": "verified",
                    },
                }
            ),
        )

    # Execute가 correction_required(amount) → route_correction(single) →
    # reset_external_transfer_amount → request_external_transfer_amount로 이어져
    # 금액 재입력에서 다시 멈춘다.
    assert waiting_amount.status == "waiting"
    events = [
        json.loads(r.content)
        for r in backend.requests_to("POST", "/api/v1/webhooks/agent")
    ]
    assert events[-1]["metadata"]["step_id"] == "request_external_transfer_amount"
    backend.assert_all_responses_used()


@pytest.mark.asyncio
async def test_external_transfer_state_has_no_sensitive_data() -> None:
    """완료된 State에 인증 토큰이나 마스킹 안 된 계좌번호가 남지 않는다."""

    backend = MockBackend()
    backend.add_success(
        "POST",
        "/api/v1/agent-tools/recipients:resolve",
        {"outcome": "resolved", "to_recipient_id": "recipient_sensitive"},
    )
    backend.add_success(
        "GET",
        "/api/v1/agent-tools/accounts",
        {
            "account_resolution_outcome": "resolved",
            "accounts": [_account("acc_001", "생활비")],
            "account_ids": ["acc_001"],
        },
    )
    backend.add_success(
        "POST",
        "/api/v1/agent-tools/transfers/external:prepare",
        {
            "outcome": "ready_for_confirmation",
            "confirmation_id": "confirm_sensitive",
            "confirmation_view": _confirmation_view(),
        },
    )
    backend.add_success(
        "POST", "/api/v1/webhooks/agent", {"message_id": "msg_approval_sensitive"}
    )
    backend.add_success(
        "POST",
        "/api/v1/agent-tools/auth-contexts",
        {
            "outcome": "authentication_required",
            "auth_context_id": "auth_sensitive",
            "auth_request_view": {
                "title": "본인 인증이 필요합니다.",
                "available_methods": ["biometric"],
                "expires_at": "2026-07-17T10:10:00+09:00",
            },
        },
    )
    backend.add_success(
        "POST", "/api/v1/webhooks/agent", {"message_id": "msg_auth_sensitive"}
    )
    backend.add_success(
        "POST",
        "/api/v1/agent-tools/transfers/external",
        {
            "outcome": "completed",
            "transaction_id": "txn_sensitive",
            "completed_at": "2026-07-17T10:11:00+09:00",
        },
    )
    backend.add_success(
        "POST", "/api/v1/webhooks/agent", {"message_id": "msg_result_sensitive"}
    )

    async with create_external_transfer_mock_testbed(
        backend, _config(), thread_id="thread_sensitive"
    ) as testbed:
        waiting_approval = await testbed.start(
            message="철수에게 10만원 보내줘",
            request_id="req_1",
            chat_session_id="chat_1",
            execution_context_id="exec_1",
        )
        assert waiting_approval.pending_interaction is not None
        confirmation_id = waiting_approval.pending_interaction["confirmation_id"]

        waiting_auth = await testbed.resume(
            "thread_sensitive",
            ExecutionResumeRequest.model_validate(
                {
                    "request_id": "req_2",
                    "chat_session_id": "chat_1",
                    "execution_context_id": "exec_1",
                    "resume": {
                        "type": "approval",
                        "confirmation_id": confirmation_id,
                        "approval_outcome": "approved",
                    },
                }
            ),
        )
        assert waiting_auth.pending_interaction is not None
        auth_context_id = waiting_auth.pending_interaction["auth_context_id"]

        completed = await testbed.resume(
            "thread_sensitive",
            ExecutionResumeRequest.model_validate(
                {
                    "request_id": "req_3",
                    "chat_session_id": "chat_1",
                    "execution_context_id": "exec_1",
                    "resume": {
                        "type": "authentication",
                        "auth_context_id": auth_context_id,
                        "auth_status": "verified",
                    },
                }
            ),
        )
        state = await testbed.state("thread_sensitive")

    assert completed.status == "completed"

    state_json = json.dumps(state, ensure_ascii=False, default=str)
    assert "agent-service-token" not in state_json
    assert "agent-webhook-secret" not in state_json

    masked_numbers: list[str] = []

    def _collect_masked_numbers(value: object) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key == "masked_account_number" and isinstance(item, str):
                    masked_numbers.append(item)
                else:
                    _collect_masked_numbers(item)
        elif isinstance(value, list):
            for item in value:
                _collect_masked_numbers(item)

    _collect_masked_numbers(state)
    assert masked_numbers, (
        "검증 대상 계좌번호가 State에 하나도 없으면 이 테스트는 의미가 없다."
    )
    for number in masked_numbers:
        assert "*" in number, f"마스킹되지 않은 계좌번호가 State에 남아있다: {number}"
    assert not re.search(r"\d{9,}", state_json), (
        "마스킹 없는 긴 숫자열(원문 계좌번호로 추정)이 State에 있다."
    )
