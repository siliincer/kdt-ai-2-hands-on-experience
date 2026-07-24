"""기본 출금 계좌 변경 Workflow의 Mock Backend End-to-End 테스트."""

from __future__ import annotations

import json
import re

import pytest
from pydantic import SecretStr

from agent.clients.backend import BackendClientConfig
from agent.runtime.hitl import ExecutionResumeRequest
from agent.testing import MockBackend
from agent.testing.set_default_account import (
    create_default_account_change_mock_testbed,
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
        "bank_name": "카카오뱅크",
        "account_alias": alias,
        "account_type": "checking",
        "masked_account_number": "3333-**-1234567",
        "currency": "KRW",
        "is_default": False,
        "status": "active",
    }


def _confirmation_view() -> dict[str, object]:
    return {
        "current_default_account": {
            "account_id": "acc_001",
            "bank_name": "카카오뱅크",
            "account_alias": "생활비",
            "masked_account_number": "3333-**-1234567",
        },
        "new_default_account": {
            "account_id": "acc_002",
            "bank_name": "카카오뱅크",
            "account_alias": "급여",
            "masked_account_number": "3333-**-7654321",
        },
        "expires_at": "2026-07-19T10:05:00+09:00",
    }


@pytest.mark.asyncio
async def test_set_default_account_reference_workflow_completes_full_happy_path() -> None:
    backend = MockBackend()
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
        "/api/v1/agent-tools/settings/default-account:prepare",
        {
            "outcome": "ready_for_confirmation",
            "confirmation_id": "confirm_default_123",
            "confirmation_view": _confirmation_view(),
        },
    )
    backend.add_success("POST", "/api/v1/webhooks/agent", {"message_id": "msg_approval"})
    backend.add_success(
        "POST",
        "/api/v1/agent-tools/settings/default-account",
        {
            "outcome": "completed",
            "account_id": "acc_002",
            "completed_at": "2026-07-19T10:06:00+09:00",
        },
    )
    backend.add_success("POST", "/api/v1/webhooks/agent", {"message_id": "msg_result"})

    async with create_default_account_change_mock_testbed(
        backend, _config(), thread_id="thread_default_happy"
    ) as testbed:
        waiting = await testbed.start(
            message="급여 통장을 기본계좌로 바꿔줘",
            request_id="req_1",
            chat_session_id="chat_1",
            execution_context_id="exec_1",
        )
        assert waiting.status == "waiting"
        assert waiting.pending_interaction is not None
        confirmation_id = waiting.pending_interaction["confirmation_id"]
        assert confirmation_id == "confirm_default_123"

        completed = await testbed.resume(
            "thread_default_happy",
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
        state = await testbed.state("thread_default_happy")

    assert completed.status == "completed"
    assert state["data"]["account_id"] == "acc_002"

    result_event = json.loads(backend.requests_to("POST", "/api/v1/webhooks/agent")[-1].content)
    assert result_event["metadata"]["step_id"] == "emit_default_account_result"
    assert result_event["metadata"]["ui"]["payload"]["outcome"] == "completed"
    backend.assert_all_responses_used()


@pytest.mark.asyncio
async def test_set_default_account_selection_required_then_selected() -> None:
    """계좌 후보가 여럿이면 선택 화면을 보여주고, 선택 후 정상 완료한다."""

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
        "/api/v1/agent-tools/settings/default-account:prepare",
        {
            "outcome": "ready_for_confirmation",
            "confirmation_id": "confirm_select_1",
            "confirmation_view": _confirmation_view(),
        },
    )
    backend.add_success("POST", "/api/v1/webhooks/agent", {"message_id": "msg_approval"})
    backend.add_success(
        "POST",
        "/api/v1/agent-tools/settings/default-account",
        {
            "outcome": "completed",
            "account_id": "acc_002",
            "completed_at": "2026-07-19T10:06:00+09:00",
        },
    )
    backend.add_success("POST", "/api/v1/webhooks/agent", {"message_id": "msg_result"})

    async with create_default_account_change_mock_testbed(
        backend, _config(), thread_id="thread_default_select"
    ) as testbed:
        waiting_select = await testbed.start(
            message="기본계좌 바꾸고 싶어",
            request_id="req_1",
            chat_session_id="chat_1",
            execution_context_id="exec_1",
        )
        assert waiting_select.pending_interaction is not None
        input_request_id = waiting_select.pending_interaction["input_request_id"]

        waiting_approval = await testbed.resume_input(
            agent_thread_id="thread_default_select",
            request_id="req_2",
            chat_session_id="chat_1",
            execution_context_id="exec_1",
            input_request_id=input_request_id,
            value={"account_selection_outcome": "selected", "account_ids": ["acc_002"]},
        )
        assert waiting_approval.pending_interaction is not None
        confirmation_id = waiting_approval.pending_interaction["confirmation_id"]

        completed = await testbed.resume(
            "thread_default_select",
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
async def test_set_default_account_selection_required_then_cancelled() -> None:
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

    async with create_default_account_change_mock_testbed(
        backend, _config(), thread_id="thread_default_cancel_select"
    ) as testbed:
        waiting = await testbed.start(
            message="기본계좌 바꾸고 싶어",
            request_id="req_1",
            chat_session_id="chat_1",
            execution_context_id="exec_1",
        )
        assert waiting.pending_interaction is not None
        input_request_id = waiting.pending_interaction["input_request_id"]

        completed = await testbed.resume_input(
            agent_thread_id="thread_default_cancel_select",
            request_id="req_2",
            chat_session_id="chat_1",
            execution_context_id="exec_1",
            input_request_id=input_request_id,
            value={"account_selection_outcome": "cancelled", "account_ids": []},
        )
        state = await testbed.state("thread_default_cancel_select")

    assert completed.status == "completed"
    assert state["status"] == "completed"
    backend.assert_all_responses_used()


@pytest.mark.asyncio
async def test_set_default_account_no_accounts_empty() -> None:
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

    async with create_default_account_change_mock_testbed(
        backend, _config(), thread_id="thread_default_no_accounts"
    ) as testbed:
        completed = await testbed.start(
            message="기본계좌 바꿔줘",
            request_id="req_1",
            chat_session_id="chat_1",
            execution_context_id="exec_1",
        )

    assert completed.status == "completed"
    event = json.loads(backend.requests_to("POST", "/api/v1/webhooks/agent")[0].content)
    assert event["metadata"]["step_id"] == "emit_default_account_selection_empty"
    backend.assert_all_responses_used()


@pytest.mark.asyncio
async def test_set_default_account_unchanged() -> None:
    """대상 계좌가 이미 기본 출금 계좌면 오류가 아니라 unchanged로 끝난다."""

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
        "/api/v1/agent-tools/settings/default-account:prepare",
        {"outcome": "unchanged", "account_id": "acc_001"},
    )
    backend.add_success("POST", "/api/v1/webhooks/agent", {"message_id": "msg_unchanged"})

    async with create_default_account_change_mock_testbed(
        backend, _config(), thread_id="thread_default_unchanged"
    ) as testbed:
        completed = await testbed.start(
            message="생활비 통장을 기본계좌로 바꿔줘",
            request_id="req_1",
            chat_session_id="chat_1",
            execution_context_id="exec_1",
        )
        state = await testbed.state("thread_default_unchanged")

    assert completed.status == "completed"
    assert state["status"] == "completed"
    event = json.loads(backend.requests_to("POST", "/api/v1/webhooks/agent")[0].content)
    assert event["metadata"]["step_id"] == "emit_default_account_unchanged"
    assert event["metadata"]["ui"]["payload"]["outcome"] == "unchanged"
    backend.assert_all_responses_used()


@pytest.mark.asyncio
async def test_set_default_account_correction_required_at_prepare() -> None:
    """Prepare가 correction_required면 계좌 확인부터 다시 시작해 정상 완료한다."""

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
        "/api/v1/agent-tools/settings/default-account:prepare",
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
        "/api/v1/agent-tools/settings/default-account:prepare",
        {
            "outcome": "ready_for_confirmation",
            "confirmation_id": "confirm_retry_1",
            "confirmation_view": _confirmation_view(),
        },
    )
    backend.add_success("POST", "/api/v1/webhooks/agent", {"message_id": "msg_approval"})

    async with create_default_account_change_mock_testbed(
        backend, _config(), thread_id="thread_default_correction"
    ) as testbed:
        waiting = await testbed.start(
            message="생활비 통장을 기본계좌로 바꿔줘",
            request_id="req_1",
            chat_session_id="chat_1",
            execution_context_id="exec_1",
        )
        assert waiting.status == "waiting"
        assert waiting.pending_interaction is not None
        assert waiting.pending_interaction["type"] == "approval"

    backend.assert_all_responses_used()


@pytest.mark.asyncio
async def test_set_default_account_change_requested_at_approval() -> None:
    """승인 화면에서 수정을 요청하면 계좌 확인부터 다시 진행해 완료한다."""

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
        "/api/v1/agent-tools/settings/default-account:prepare",
        {
            "outcome": "ready_for_confirmation",
            "confirmation_id": "confirm_change_1",
            "confirmation_view": _confirmation_view(),
        },
    )
    backend.add_success("POST", "/api/v1/webhooks/agent", {"message_id": "msg_approval_1"})
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
        "/api/v1/agent-tools/settings/default-account:prepare",
        {
            "outcome": "ready_for_confirmation",
            "confirmation_id": "confirm_change_2",
            "confirmation_view": _confirmation_view(),
        },
    )
    backend.add_success("POST", "/api/v1/webhooks/agent", {"message_id": "msg_approval_2"})
    backend.add_success(
        "POST",
        "/api/v1/agent-tools/settings/default-account",
        {
            "outcome": "completed",
            "account_id": "acc_002",
            "completed_at": "2026-07-19T10:06:00+09:00",
        },
    )
    backend.add_success("POST", "/api/v1/webhooks/agent", {"message_id": "msg_result"})

    async with create_default_account_change_mock_testbed(
        backend, _config(), thread_id="thread_default_change_requested"
    ) as testbed:
        waiting_first = await testbed.start(
            message="생활비 통장을 기본계좌로 바꿔줘",
            request_id="req_1",
            chat_session_id="chat_1",
            execution_context_id="exec_1",
        )
        assert waiting_first.pending_interaction is not None
        first_confirmation_id = waiting_first.pending_interaction["confirmation_id"]

        waiting_second = await testbed.resume(
            "thread_default_change_requested",
            ExecutionResumeRequest.model_validate(
                {
                    "request_id": "req_2",
                    "chat_session_id": "chat_1",
                    "execution_context_id": "exec_1",
                    "resume": {
                        "type": "approval",
                        "confirmation_id": first_confirmation_id,
                        "approval_outcome": "change_requested",
                    },
                }
            ),
        )
        assert waiting_second.pending_interaction is not None
        second_confirmation_id = waiting_second.pending_interaction["confirmation_id"]

        completed = await testbed.resume(
            "thread_default_change_requested",
            ExecutionResumeRequest.model_validate(
                {
                    "request_id": "req_3",
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
async def test_set_default_account_cancel_at_approval() -> None:
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
        "/api/v1/agent-tools/settings/default-account:prepare",
        {
            "outcome": "ready_for_confirmation",
            "confirmation_id": "confirm_cancel_1",
            "confirmation_view": _confirmation_view(),
        },
    )
    backend.add_success("POST", "/api/v1/webhooks/agent", {"message_id": "msg_approval"})

    async with create_default_account_change_mock_testbed(
        backend, _config(), thread_id="thread_default_cancel_approval"
    ) as testbed:
        waiting = await testbed.start(
            message="생활비 통장을 기본계좌로 바꿔줘",
            request_id="req_1",
            chat_session_id="chat_1",
            execution_context_id="exec_1",
        )
        assert waiting.pending_interaction is not None
        confirmation_id = waiting.pending_interaction["confirmation_id"]

        completed = await testbed.resume(
            "thread_default_cancel_approval",
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
        state = await testbed.state("thread_default_cancel_approval")

    assert completed.status == "completed"
    assert state["status"] == "completed"
    backend.assert_all_responses_used()


@pytest.mark.asyncio
async def test_set_default_account_correction_required_at_execute() -> None:
    """Execute가 correction_required면 계좌 확인부터 다시 진행해 완료한다."""

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
        "/api/v1/agent-tools/settings/default-account:prepare",
        {
            "outcome": "ready_for_confirmation",
            "confirmation_id": "confirm_exec_correction_1",
            "confirmation_view": _confirmation_view(),
        },
    )
    backend.add_success("POST", "/api/v1/webhooks/agent", {"message_id": "msg_approval_1"})
    backend.add_success(
        "POST",
        "/api/v1/agent-tools/settings/default-account",
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
        "/api/v1/agent-tools/settings/default-account:prepare",
        {
            "outcome": "ready_for_confirmation",
            "confirmation_id": "confirm_exec_correction_2",
            "confirmation_view": _confirmation_view(),
        },
    )
    backend.add_success("POST", "/api/v1/webhooks/agent", {"message_id": "msg_approval_2"})
    backend.add_success(
        "POST",
        "/api/v1/agent-tools/settings/default-account",
        {
            "outcome": "completed",
            "account_id": "acc_002",
            "completed_at": "2026-07-19T10:06:00+09:00",
        },
    )
    backend.add_success("POST", "/api/v1/webhooks/agent", {"message_id": "msg_result"})

    async with create_default_account_change_mock_testbed(
        backend, _config(), thread_id="thread_default_execute_correction"
    ) as testbed:
        waiting_first = await testbed.start(
            message="생활비 통장을 기본계좌로 바꿔줘",
            request_id="req_1",
            chat_session_id="chat_1",
            execution_context_id="exec_1",
        )
        assert waiting_first.pending_interaction is not None
        first_confirmation_id = waiting_first.pending_interaction["confirmation_id"]

        waiting_second = await testbed.resume(
            "thread_default_execute_correction",
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
        assert waiting_second.pending_interaction is not None
        second_confirmation_id = waiting_second.pending_interaction["confirmation_id"]

        completed = await testbed.resume(
            "thread_default_execute_correction",
            ExecutionResumeRequest.model_validate(
                {
                    "request_id": "req_3",
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
async def test_set_default_account_blocked_at_prepare() -> None:
    """Prepare가 blocked를 반환하면 재시도 없이 차단 안내로 끝난다."""

    backend = MockBackend()
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
        "/api/v1/agent-tools/settings/default-account:prepare",
        {
            "outcome": "blocked",
            "reason": "setting_restricted",
            "blocked_view": {
                "title": "기본 출금 계좌를 변경할 수 없습니다.",
                "description": "고객센터에 문의해 주세요.",
            },
        },
    )
    backend.add_success("POST", "/api/v1/webhooks/agent", {"message_id": "msg_blocked"})

    async with create_default_account_change_mock_testbed(
        backend, _config(), thread_id="thread_default_blocked"
    ) as testbed:
        completed = await testbed.start(
            message="급여 통장을 기본계좌로 바꿔줘",
            request_id="req_1",
            chat_session_id="chat_1",
            execution_context_id="exec_1",
        )
        state = await testbed.state("thread_default_blocked")

    assert completed.status == "completed"
    assert state["status"] == "blocked"
    event = json.loads(backend.requests_to("POST", "/api/v1/webhooks/agent")[0].content)
    assert event["metadata"]["step_id"] == "emit_default_account_blocked"
    backend.assert_all_responses_used()


@pytest.mark.asyncio
async def test_set_default_account_state_has_no_sensitive_data() -> None:
    """완료된 State에 인증 토큰이나 마스킹 안 된 계좌번호가 남지 않는다."""

    backend = MockBackend()
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
        "/api/v1/agent-tools/settings/default-account:prepare",
        {
            "outcome": "ready_for_confirmation",
            "confirmation_id": "confirm_sensitive",
            "confirmation_view": _confirmation_view(),
        },
    )
    backend.add_success("POST", "/api/v1/webhooks/agent", {"message_id": "msg_approval"})
    backend.add_success(
        "POST",
        "/api/v1/agent-tools/settings/default-account",
        {
            "outcome": "completed",
            "account_id": "acc_002",
            "completed_at": "2026-07-19T10:06:00+09:00",
        },
    )
    backend.add_success("POST", "/api/v1/webhooks/agent", {"message_id": "msg_result"})

    async with create_default_account_change_mock_testbed(
        backend, _config(), thread_id="thread_default_sensitive"
    ) as testbed:
        waiting = await testbed.start(
            message="급여 통장을 기본계좌로 바꿔줘",
            request_id="req_1",
            chat_session_id="chat_1",
            execution_context_id="exec_1",
        )
        assert waiting.pending_interaction is not None
        confirmation_id = waiting.pending_interaction["confirmation_id"]

        completed = await testbed.resume(
            "thread_default_sensitive",
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
        state = await testbed.state("thread_default_sensitive")

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


@pytest.mark.asyncio
async def test_set_default_account_unset_skips_account_resolution() -> None:
    """해제 발화는 계좌 조회·선택을 건너뛰고 바로 승인 화면으로 간다."""

    backend = MockBackend()
    backend.add_success(
        "POST",
        "/api/v1/agent-tools/settings/default-account:prepare",
        {
            "outcome": "ready_for_confirmation",
            "confirmation_id": "confirm_unset_1",
            "confirmation_view": {
                "current_default_account": {
                    "account_id": "acc_001",
                    "bank_name": "카카오뱅크",
                    "account_alias": "생활비",
                    "masked_account_number": "3333-**-1234567",
                },
                "new_default_account": None,
                "expires_at": "2026-07-19T10:05:00+09:00",
            },
        },
    )
    backend.add_success("POST", "/api/v1/webhooks/agent", {"message_id": "msg_approval"})
    backend.add_success(
        "POST",
        "/api/v1/agent-tools/settings/default-account",
        {
            "outcome": "completed",
            "completed_at": "2026-07-19T10:06:00+09:00",
        },
    )
    backend.add_success("POST", "/api/v1/webhooks/agent", {"message_id": "msg_result"})

    async with create_default_account_change_mock_testbed(
        backend, _config(), thread_id="thread_default_unset"
    ) as testbed:
        waiting = await testbed.start(
            message="기본계좌 해제해줘",
            request_id="req_1",
            chat_session_id="chat_1",
            execution_context_id="exec_1",
        )
        assert waiting.status == "waiting"
        assert waiting.pending_interaction is not None
        confirmation_id = waiting.pending_interaction["confirmation_id"]
        assert confirmation_id == "confirm_unset_1"

        completed = await testbed.resume(
            "thread_default_unset",
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

    assert completed.status == "completed"
    assert backend.requests_to("GET", "/api/v1/agent-tools/accounts") == []
    prepare_body = json.loads(
        backend.requests_to("POST", "/api/v1/agent-tools/settings/default-account:prepare")[0].content
    )
    assert prepare_body == {"unset": True}

    result_event = json.loads(backend.requests_to("POST", "/api/v1/webhooks/agent")[-1].content)
    assert result_event["metadata"]["step_id"] == "emit_default_account_result"
    assert result_event["metadata"]["ui"]["payload"]["outcome"] == "completed"
    backend.assert_all_responses_used()


@pytest.mark.asyncio
async def test_set_default_account_unset_when_already_unset_is_unchanged() -> None:
    """이미 기본 계좌가 없으면 Confirmation 없이 바로 unchanged 로 끝난다."""

    backend = MockBackend()
    backend.add_success(
        "POST",
        "/api/v1/agent-tools/settings/default-account:prepare",
        {"outcome": "unchanged"},
    )
    backend.add_success("POST", "/api/v1/webhooks/agent", {"message_id": "msg_unchanged"})

    async with create_default_account_change_mock_testbed(
        backend, _config(), thread_id="thread_default_unset_unchanged"
    ) as testbed:
        completed = await testbed.start(
            message="기본계좌 해제해줘",
            request_id="req_1",
            chat_session_id="chat_1",
            execution_context_id="exec_1",
        )

    assert completed.status == "completed"
    result_event = json.loads(backend.requests_to("POST", "/api/v1/webhooks/agent")[-1].content)
    assert result_event["metadata"]["step_id"] == "emit_default_account_unchanged"
    assert result_event["content"] == "이미 기본 출금 계좌가 지정되어 있지 않습니다."
    backend.assert_all_responses_used()
