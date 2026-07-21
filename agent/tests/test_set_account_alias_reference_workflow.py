"""계좌 별칭 변경 Workflow의 Mock Backend End-to-End 테스트."""

from __future__ import annotations

import json
import re

import pytest
from pydantic import SecretStr

from agent.clients.backend import BackendClientConfig
from agent.runtime.hitl import ExecutionResumeRequest
from agent.testing import MockBackend
from agent.testing.set_account_alias import create_account_alias_change_mock_testbed


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


def _confirmation_view(alias: str) -> dict[str, object]:
    return {
        "account": {
            "account_id": "acc_001",
            "bank_name": "신한은행",
            "masked_account_number": "110-***-123456",
        },
        "alias": alias,
        "expires_at": "2026-07-19T10:05:00+09:00",
    }


@pytest.mark.asyncio
async def test_set_account_alias_reference_workflow_completes_full_happy_path() -> None:
    backend = MockBackend()
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
        "/api/v1/agent-tools/settings/account-alias:prepare",
        {
            "outcome": "ready_for_confirmation",
            "confirmation_id": "confirm_alias_123",
            "confirmation_view": _confirmation_view("여행 자금"),
        },
    )
    backend.add_success("POST", "/api/v1/webhooks/agent", {"message_id": "msg_approval"})
    backend.add_success(
        "POST",
        "/api/v1/agent-tools/settings/account-alias",
        {
            "outcome": "completed",
            "account_id": "acc_001",
            "alias": "여행 자금",
            "completed_at": "2026-07-19T10:06:00+09:00",
        },
    )
    backend.add_success("POST", "/api/v1/webhooks/agent", {"message_id": "msg_result"})

    async with create_account_alias_change_mock_testbed(backend, _config(), thread_id="thread_alias_happy") as testbed:
        waiting = await testbed.start(
            message="생활비 통장 별칭을 여행 자금으로 바꿔줘",
            request_id="req_1",
            chat_session_id="chat_1",
            execution_context_id="exec_1",
        )
        assert waiting.status == "waiting"
        assert waiting.pending_interaction is not None
        confirmation_id = waiting.pending_interaction["confirmation_id"]

        completed = await testbed.resume(
            "thread_alias_happy",
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
        state = await testbed.state("thread_alias_happy")

    assert completed.status == "completed"
    assert state["data"]["alias"] == "여행 자금"

    result_event = json.loads(backend.requests_to("POST", "/api/v1/webhooks/agent")[-1].content)
    assert result_event["metadata"]["step_id"] == "emit_account_alias_result"
    assert result_event["metadata"]["ui"]["payload"]["alias"] == "여행 자금"
    backend.assert_all_responses_used()


@pytest.mark.asyncio
async def test_set_account_alias_selection_required_then_selected() -> None:
    backend = MockBackend()
    backend.add_success(
        "GET",
        "/api/v1/agent-tools/accounts",
        {
            "account_resolution_outcome": "selection_required",
            "accounts": [_account("acc_001", "생활비"), _account("acc_002", "급여")],
            "account_ids": [],
        },
    )
    backend.add_success("POST", "/api/v1/webhooks/agent", {"message_id": "msg_select"})
    backend.add_success(
        "POST",
        "/api/v1/agent-tools/settings/account-alias:prepare",
        {
            "outcome": "ready_for_confirmation",
            "confirmation_id": "confirm_alias_select",
            "confirmation_view": _confirmation_view("여행 자금"),
        },
    )
    backend.add_success("POST", "/api/v1/webhooks/agent", {"message_id": "msg_approval"})
    backend.add_success(
        "POST",
        "/api/v1/agent-tools/settings/account-alias",
        {
            "outcome": "completed",
            "account_id": "acc_001",
            "alias": "여행 자금",
            "completed_at": "2026-07-19T10:06:00+09:00",
        },
    )
    backend.add_success("POST", "/api/v1/webhooks/agent", {"message_id": "msg_result"})

    async with create_account_alias_change_mock_testbed(backend, _config(), thread_id="thread_alias_select") as testbed:
        waiting_select = await testbed.start(
            message="별칭을 여행 자금으로 바꿔줘",
            request_id="req_1",
            chat_session_id="chat_1",
            execution_context_id="exec_1",
        )
        assert waiting_select.pending_interaction is not None
        input_request_id = waiting_select.pending_interaction["input_request_id"]

        waiting_approval = await testbed.resume_input(
            agent_thread_id="thread_alias_select",
            request_id="req_2",
            chat_session_id="chat_1",
            execution_context_id="exec_1",
            input_request_id=input_request_id,
            value={"account_selection_outcome": "selected", "account_ids": ["acc_001"]},
        )
        assert waiting_approval.pending_interaction is not None
        confirmation_id = waiting_approval.pending_interaction["confirmation_id"]

        completed = await testbed.resume(
            "thread_alias_select",
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

    assert completed.status == "completed"
    backend.assert_all_responses_used()


@pytest.mark.asyncio
async def test_set_account_alias_selection_required_then_cancelled() -> None:
    backend = MockBackend()
    backend.add_success(
        "GET",
        "/api/v1/agent-tools/accounts",
        {
            "account_resolution_outcome": "selection_required",
            "accounts": [_account("acc_001", "생활비"), _account("acc_002", "급여")],
            "account_ids": [],
        },
    )
    backend.add_success("POST", "/api/v1/webhooks/agent", {"message_id": "msg_select"})

    async with create_account_alias_change_mock_testbed(
        backend, _config(), thread_id="thread_alias_cancel_select"
    ) as testbed:
        waiting = await testbed.start(
            message="별칭 바꾸고 싶어",
            request_id="req_1",
            chat_session_id="chat_1",
            execution_context_id="exec_1",
        )
        assert waiting.pending_interaction is not None
        input_request_id = waiting.pending_interaction["input_request_id"]

        completed = await testbed.resume_input(
            agent_thread_id="thread_alias_cancel_select",
            request_id="req_2",
            chat_session_id="chat_1",
            execution_context_id="exec_1",
            input_request_id=input_request_id,
            value={"account_selection_outcome": "cancelled", "account_ids": []},
        )
        state = await testbed.state("thread_alias_cancel_select")

    assert completed.status == "completed"
    assert state["status"] == "completed"
    backend.assert_all_responses_used()


@pytest.mark.asyncio
async def test_set_account_alias_no_accounts_empty() -> None:
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
    backend.add_success("POST", "/api/v1/webhooks/agent", {"message_id": "msg_empty"})

    async with create_account_alias_change_mock_testbed(
        backend, _config(), thread_id="thread_alias_no_accounts"
    ) as testbed:
        completed = await testbed.start(
            message="별칭 바꿔줘",
            request_id="req_1",
            chat_session_id="chat_1",
            execution_context_id="exec_1",
        )

    assert completed.status == "completed"
    event = json.loads(backend.requests_to("POST", "/api/v1/webhooks/agent")[0].content)
    assert event["metadata"]["step_id"] == "emit_account_alias_selection_empty"
    backend.assert_all_responses_used()


@pytest.mark.asyncio
async def test_set_account_alias_missing_then_submitted() -> None:
    """발화에 별칭이 없으면 입력 화면을 거쳐 완료한다."""

    backend = MockBackend()
    backend.add_success(
        "GET",
        "/api/v1/agent-tools/accounts",
        {
            "account_resolution_outcome": "resolved",
            "accounts": [_account("acc_001", "생활비")],
            "account_ids": ["acc_001"],
        },
    )
    backend.add_success("POST", "/api/v1/webhooks/agent", {"message_id": "msg_alias_input"})
    backend.add_success(
        "POST",
        "/api/v1/agent-tools/settings/account-alias:prepare",
        {
            "outcome": "ready_for_confirmation",
            "confirmation_id": "confirm_alias_missing",
            "confirmation_view": _confirmation_view("여행 자금"),
        },
    )
    backend.add_success("POST", "/api/v1/webhooks/agent", {"message_id": "msg_approval"})
    backend.add_success(
        "POST",
        "/api/v1/agent-tools/settings/account-alias",
        {
            "outcome": "completed",
            "account_id": "acc_001",
            "alias": "여행 자금",
            "completed_at": "2026-07-19T10:06:00+09:00",
        },
    )
    backend.add_success("POST", "/api/v1/webhooks/agent", {"message_id": "msg_result"})

    async with create_account_alias_change_mock_testbed(
        backend, _config(), thread_id="thread_alias_missing"
    ) as testbed:
        waiting_input = await testbed.start(
            message="생활비 통장 별칭을 바꾸고 싶어",
            request_id="req_1",
            chat_session_id="chat_1",
            execution_context_id="exec_1",
        )
        assert waiting_input.pending_interaction is not None
        input_request_id = waiting_input.pending_interaction["input_request_id"]

        waiting_approval = await testbed.resume_input(
            agent_thread_id="thread_alias_missing",
            request_id="req_2",
            chat_session_id="chat_1",
            execution_context_id="exec_1",
            input_request_id=input_request_id,
            value={"alias_input_outcome": "submitted", "alias": "여행 자금"},
        )
        assert waiting_approval.pending_interaction is not None
        confirmation_id = waiting_approval.pending_interaction["confirmation_id"]

        completed = await testbed.resume(
            "thread_alias_missing",
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

    assert completed.status == "completed"
    events = [json.loads(r.content) for r in backend.requests_to("POST", "/api/v1/webhooks/agent")]
    assert events[0]["metadata"]["step_id"] == "request_account_alias_input"
    backend.assert_all_responses_used()


@pytest.mark.asyncio
async def test_set_account_alias_input_cancelled() -> None:
    backend = MockBackend()
    backend.add_success(
        "GET",
        "/api/v1/agent-tools/accounts",
        {
            "account_resolution_outcome": "resolved",
            "accounts": [_account("acc_001", "생활비")],
            "account_ids": ["acc_001"],
        },
    )
    backend.add_success("POST", "/api/v1/webhooks/agent", {"message_id": "msg_alias_input"})

    async with create_account_alias_change_mock_testbed(
        backend, _config(), thread_id="thread_alias_input_cancel"
    ) as testbed:
        waiting = await testbed.start(
            message="생활비 통장 별칭을 바꾸고 싶어",
            request_id="req_1",
            chat_session_id="chat_1",
            execution_context_id="exec_1",
        )
        assert waiting.pending_interaction is not None
        input_request_id = waiting.pending_interaction["input_request_id"]

        completed = await testbed.resume_input(
            agent_thread_id="thread_alias_input_cancel",
            request_id="req_2",
            chat_session_id="chat_1",
            execution_context_id="exec_1",
            input_request_id=input_request_id,
            value={"alias_input_outcome": "cancelled", "alias": None},
        )
        state = await testbed.state("thread_alias_input_cancel")

    assert completed.status == "completed"
    assert state["status"] == "completed"
    backend.assert_all_responses_used()


@pytest.mark.asyncio
async def test_set_account_alias_unchanged() -> None:
    backend = MockBackend()
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
        "/api/v1/agent-tools/settings/account-alias:prepare",
        {
            "outcome": "unchanged",
            "account_id": "acc_001",
            "alias": "생활비",
        },
    )
    backend.add_success("POST", "/api/v1/webhooks/agent", {"message_id": "msg_unchanged"})

    async with create_account_alias_change_mock_testbed(
        backend, _config(), thread_id="thread_alias_unchanged"
    ) as testbed:
        completed = await testbed.start(
            message="생활비 통장 별칭을 생활비로 바꿔줘",
            request_id="req_1",
            chat_session_id="chat_1",
            execution_context_id="exec_1",
        )
        state = await testbed.state("thread_alias_unchanged")

    assert completed.status == "completed"
    assert state["status"] == "completed"
    event = json.loads(backend.requests_to("POST", "/api/v1/webhooks/agent")[0].content)
    assert event["metadata"]["step_id"] == "emit_account_alias_unchanged"
    assert event["metadata"]["ui"]["payload"]["outcome"] == "unchanged"
    backend.assert_all_responses_used()


@pytest.mark.asyncio
async def test_set_account_alias_correction_required_target_account() -> None:
    """Prepare가 account 수정을 요구하면 계좌 확인부터 다시 시작해 완료한다."""

    backend = MockBackend()
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
        "/api/v1/agent-tools/settings/account-alias:prepare",
        {
            "outcome": "correction_required",
            "reason": "account_not_eligible",
            "correction_view": {"allowed_change_targets": ["account"]},
        },
    )
    backend.add_success(
        "GET",
        "/api/v1/agent-tools/accounts",
        {
            "account_resolution_outcome": "resolved",
            "accounts": [_account("acc_002", "급여")],
            "account_ids": ["acc_002"],
        },
    )
    backend.add_success(
        "POST",
        "/api/v1/agent-tools/settings/account-alias:prepare",
        {
            "outcome": "ready_for_confirmation",
            "confirmation_id": "confirm_correction_account",
            "confirmation_view": _confirmation_view("여행 자금"),
        },
    )
    backend.add_success("POST", "/api/v1/webhooks/agent", {"message_id": "msg_approval"})

    async with create_account_alias_change_mock_testbed(
        backend, _config(), thread_id="thread_alias_correction_account"
    ) as testbed:
        waiting = await testbed.start(
            message="생활비 통장 별칭을 여행 자금으로 바꿔줘",
            request_id="req_1",
            chat_session_id="chat_1",
            execution_context_id="exec_1",
        )
        assert waiting.status == "waiting"
        assert waiting.pending_interaction is not None
        assert waiting.pending_interaction["type"] == "approval"

    backend.assert_all_responses_used()


@pytest.mark.asyncio
async def test_set_account_alias_correction_required_target_alias() -> None:
    """Prepare가 alias 수정을 요구하면 별칭 입력부터 다시 시작해 완료한다."""

    backend = MockBackend()
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
        "/api/v1/agent-tools/settings/account-alias:prepare",
        {
            "outcome": "correction_required",
            "reason": "alias_not_allowed",
            "correction_view": {"allowed_change_targets": ["alias"]},
        },
    )
    backend.add_success("POST", "/api/v1/webhooks/agent", {"message_id": "msg_alias_retry"})
    backend.add_success(
        "POST",
        "/api/v1/agent-tools/settings/account-alias:prepare",
        {
            "outcome": "ready_for_confirmation",
            "confirmation_id": "confirm_correction_alias",
            "confirmation_view": _confirmation_view("커피값"),
        },
    )
    backend.add_success("POST", "/api/v1/webhooks/agent", {"message_id": "msg_approval"})

    async with create_account_alias_change_mock_testbed(
        backend, _config(), thread_id="thread_alias_correction_alias"
    ) as testbed:
        waiting_input = await testbed.start(
            message="생활비 통장 별칭을 여행 자금으로 바꿔줘",
            request_id="req_1",
            chat_session_id="chat_1",
            execution_context_id="exec_1",
        )
        assert waiting_input.status == "waiting"
        assert waiting_input.pending_interaction is not None
        assert waiting_input.pending_interaction["type"] == "input"
        input_request_id = waiting_input.pending_interaction["input_request_id"]

        waiting_approval = await testbed.resume_input(
            agent_thread_id="thread_alias_correction_alias",
            request_id="req_2",
            chat_session_id="chat_1",
            execution_context_id="exec_1",
            input_request_id=input_request_id,
            value={"alias_input_outcome": "submitted", "alias": "커피값"},
        )
        assert waiting_approval.status == "waiting"

    backend.assert_all_responses_used()


@pytest.mark.asyncio
async def test_set_account_alias_change_requested_target_alias() -> None:
    """승인 화면에서 별칭 수정을 요청하면 별칭 입력으로 돌아가 완료한다."""

    backend = MockBackend()
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
        "/api/v1/agent-tools/settings/account-alias:prepare",
        {
            "outcome": "ready_for_confirmation",
            "confirmation_id": "confirm_change_alias_1",
            "confirmation_view": _confirmation_view("여행 자금"),
        },
    )
    backend.add_success("POST", "/api/v1/webhooks/agent", {"message_id": "msg_approval_1"})
    backend.add_success("POST", "/api/v1/webhooks/agent", {"message_id": "msg_alias_retry"})
    backend.add_success(
        "POST",
        "/api/v1/agent-tools/settings/account-alias:prepare",
        {
            "outcome": "ready_for_confirmation",
            "confirmation_id": "confirm_change_alias_2",
            "confirmation_view": _confirmation_view("커피값"),
        },
    )
    backend.add_success("POST", "/api/v1/webhooks/agent", {"message_id": "msg_approval_2"})
    backend.add_success(
        "POST",
        "/api/v1/agent-tools/settings/account-alias",
        {
            "outcome": "completed",
            "account_id": "acc_001",
            "alias": "커피값",
            "completed_at": "2026-07-19T10:06:00+09:00",
        },
    )
    backend.add_success("POST", "/api/v1/webhooks/agent", {"message_id": "msg_result"})

    async with create_account_alias_change_mock_testbed(
        backend, _config(), thread_id="thread_alias_change_requested"
    ) as testbed:
        waiting_first = await testbed.start(
            message="생활비 통장 별칭을 여행 자금으로 바꿔줘",
            request_id="req_1",
            chat_session_id="chat_1",
            execution_context_id="exec_1",
        )
        assert waiting_first.pending_interaction is not None
        first_confirmation_id = waiting_first.pending_interaction["confirmation_id"]

        waiting_input = await testbed.resume(
            "thread_alias_change_requested",
            ExecutionResumeRequest.model_validate(
                {
                    "request_id": "req_2",
                    "chat_session_id": "chat_1",
                    "execution_context_id": "exec_1",
                    "resume": {
                        "type": "approval",
                        "confirmation_id": first_confirmation_id,
                        "approval_outcome": "change_requested",
                        "change_target": "alias",
                    },
                }
            ),
        )
        assert waiting_input.pending_interaction is not None
        assert waiting_input.pending_interaction["type"] == "input"
        input_request_id = waiting_input.pending_interaction["input_request_id"]

        waiting_second_approval = await testbed.resume_input(
            agent_thread_id="thread_alias_change_requested",
            request_id="req_3",
            chat_session_id="chat_1",
            execution_context_id="exec_1",
            input_request_id=input_request_id,
            value={"alias_input_outcome": "submitted", "alias": "커피값"},
        )
        assert waiting_second_approval.pending_interaction is not None
        second_confirmation_id = waiting_second_approval.pending_interaction["confirmation_id"]

        completed = await testbed.resume(
            "thread_alias_change_requested",
            ExecutionResumeRequest.model_validate(
                {
                    "request_id": "req_4",
                    "chat_session_id": "chat_1",
                    "execution_context_id": "exec_1",
                    "resume": {
                        "type": "approval",
                        "confirmation_id": second_confirmation_id,
                        "approval_outcome": "approved",
                    },
                }
            ),
        )

    assert completed.status == "completed"
    backend.assert_all_responses_used()


@pytest.mark.asyncio
async def test_set_account_alias_cancel_at_approval() -> None:
    backend = MockBackend()
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
        "/api/v1/agent-tools/settings/account-alias:prepare",
        {
            "outcome": "ready_for_confirmation",
            "confirmation_id": "confirm_cancel_1",
            "confirmation_view": _confirmation_view("여행 자금"),
        },
    )
    backend.add_success("POST", "/api/v1/webhooks/agent", {"message_id": "msg_approval"})

    async with create_account_alias_change_mock_testbed(
        backend, _config(), thread_id="thread_alias_cancel_approval"
    ) as testbed:
        waiting = await testbed.start(
            message="생활비 통장 별칭을 여행 자금으로 바꿔줘",
            request_id="req_1",
            chat_session_id="chat_1",
            execution_context_id="exec_1",
        )
        assert waiting.pending_interaction is not None
        confirmation_id = waiting.pending_interaction["confirmation_id"]

        completed = await testbed.resume(
            "thread_alias_cancel_approval",
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
        state = await testbed.state("thread_alias_cancel_approval")

    assert completed.status == "completed"
    assert state["status"] == "completed"
    backend.assert_all_responses_used()


@pytest.mark.asyncio
async def test_set_account_alias_correction_required_at_execute() -> None:
    """Execute가 alias 수정을 요구하면 별칭 입력으로 돌아가 완료한다."""

    backend = MockBackend()
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
        "/api/v1/agent-tools/settings/account-alias:prepare",
        {
            "outcome": "ready_for_confirmation",
            "confirmation_id": "confirm_exec_correction_1",
            "confirmation_view": _confirmation_view("여행 자금"),
        },
    )
    backend.add_success("POST", "/api/v1/webhooks/agent", {"message_id": "msg_approval_1"})
    backend.add_success(
        "POST",
        "/api/v1/agent-tools/settings/account-alias",
        {
            "outcome": "correction_required",
            "reason": "alias_not_allowed",
            "correction_view": {"allowed_change_targets": ["alias"]},
        },
    )
    backend.add_success("POST", "/api/v1/webhooks/agent", {"message_id": "msg_alias_retry"})
    backend.add_success(
        "POST",
        "/api/v1/agent-tools/settings/account-alias:prepare",
        {
            "outcome": "ready_for_confirmation",
            "confirmation_id": "confirm_exec_correction_2",
            "confirmation_view": _confirmation_view("커피값"),
        },
    )
    backend.add_success("POST", "/api/v1/webhooks/agent", {"message_id": "msg_approval_2"})
    backend.add_success(
        "POST",
        "/api/v1/agent-tools/settings/account-alias",
        {
            "outcome": "completed",
            "account_id": "acc_001",
            "alias": "커피값",
            "completed_at": "2026-07-19T10:06:00+09:00",
        },
    )
    backend.add_success("POST", "/api/v1/webhooks/agent", {"message_id": "msg_result"})

    async with create_account_alias_change_mock_testbed(
        backend, _config(), thread_id="thread_alias_execute_correction"
    ) as testbed:
        waiting_first = await testbed.start(
            message="생활비 통장 별칭을 여행 자금으로 바꿔줘",
            request_id="req_1",
            chat_session_id="chat_1",
            execution_context_id="exec_1",
        )
        assert waiting_first.pending_interaction is not None
        first_confirmation_id = waiting_first.pending_interaction["confirmation_id"]

        waiting_input = await testbed.resume(
            "thread_alias_execute_correction",
            ExecutionResumeRequest.model_validate(
                {
                    "request_id": "req_2",
                    "chat_session_id": "chat_1",
                    "execution_context_id": "exec_1",
                    "resume": {
                        "type": "approval",
                        "confirmation_id": first_confirmation_id,
                        "approval_outcome": "approved",
                    },
                }
            ),
        )
        assert waiting_input.pending_interaction is not None
        assert waiting_input.pending_interaction["type"] == "input"
        input_request_id = waiting_input.pending_interaction["input_request_id"]

        waiting_second_approval = await testbed.resume_input(
            agent_thread_id="thread_alias_execute_correction",
            request_id="req_3",
            chat_session_id="chat_1",
            execution_context_id="exec_1",
            input_request_id=input_request_id,
            value={"alias_input_outcome": "submitted", "alias": "커피값"},
        )
        assert waiting_second_approval.pending_interaction is not None
        second_confirmation_id = waiting_second_approval.pending_interaction["confirmation_id"]

        completed = await testbed.resume(
            "thread_alias_execute_correction",
            ExecutionResumeRequest.model_validate(
                {
                    "request_id": "req_4",
                    "chat_session_id": "chat_1",
                    "execution_context_id": "exec_1",
                    "resume": {
                        "type": "approval",
                        "confirmation_id": second_confirmation_id,
                        "approval_outcome": "approved",
                    },
                }
            ),
        )

    assert completed.status == "completed"
    backend.assert_all_responses_used()


@pytest.mark.asyncio
async def test_set_account_alias_blocked_at_prepare() -> None:
    """Prepare가 blocked를 반환하면 재시도 없이 차단 안내로 끝난다."""

    backend = MockBackend()
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
        "/api/v1/agent-tools/settings/account-alias:prepare",
        {
            "outcome": "blocked",
            "reason": "setting_restricted",
            "blocked_view": {
                "title": "계좌 별칭을 변경할 수 없습니다.",
                "description": "고객센터에 문의해 주세요.",
            },
        },
    )
    backend.add_success("POST", "/api/v1/webhooks/agent", {"message_id": "msg_blocked"})

    async with create_account_alias_change_mock_testbed(
        backend, _config(), thread_id="thread_alias_blocked"
    ) as testbed:
        completed = await testbed.start(
            message="생활비 통장 별칭을 여행 자금으로 바꿔줘",
            request_id="req_1",
            chat_session_id="chat_1",
            execution_context_id="exec_1",
        )
        state = await testbed.state("thread_alias_blocked")

    assert completed.status == "completed"
    assert state["status"] == "workflow_failed"
    event = json.loads(backend.requests_to("POST", "/api/v1/webhooks/agent")[0].content)
    assert event["metadata"]["step_id"] == "emit_account_alias_blocked"
    backend.assert_all_responses_used()


@pytest.mark.asyncio
async def test_set_account_alias_state_has_no_sensitive_data() -> None:
    """완료된 State에 인증 토큰이나 마스킹 안 된 계좌번호가 남지 않는다."""

    backend = MockBackend()
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
        "/api/v1/agent-tools/settings/account-alias:prepare",
        {
            "outcome": "ready_for_confirmation",
            "confirmation_id": "confirm_sensitive",
            "confirmation_view": _confirmation_view("여행 자금"),
        },
    )
    backend.add_success("POST", "/api/v1/webhooks/agent", {"message_id": "msg_approval"})
    backend.add_success(
        "POST",
        "/api/v1/agent-tools/settings/account-alias",
        {
            "outcome": "completed",
            "account_id": "acc_001",
            "alias": "여행 자금",
            "completed_at": "2026-07-19T10:06:00+09:00",
        },
    )
    backend.add_success("POST", "/api/v1/webhooks/agent", {"message_id": "msg_result"})

    async with create_account_alias_change_mock_testbed(
        backend, _config(), thread_id="thread_alias_sensitive"
    ) as testbed:
        waiting = await testbed.start(
            message="생활비 통장 별칭을 여행 자금으로 바꿔줘",
            request_id="req_1",
            chat_session_id="chat_1",
            execution_context_id="exec_1",
        )
        assert waiting.pending_interaction is not None
        confirmation_id = waiting.pending_interaction["confirmation_id"]

        completed = await testbed.resume(
            "thread_alias_sensitive",
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
        state = await testbed.state("thread_alias_sensitive")

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
    assert masked_numbers, "검증 대상 계좌번호가 State에 하나도 없으면 이 테스트는 의미가 없다."
    for number in masked_numbers:
        assert "*" in number, f"마스킹되지 않은 계좌번호가 State에 남아있다: {number}"
    assert not re.search(r"\d{9,}", state_json), "마스킹 없는 긴 숫자열(원문 계좌번호로 추정)이 State에 있다."
