"""wf_set_default_account(기본 출금 계좌 변경) 경로 검증 시나리오."""

from __future__ import annotations

import uuid
from typing import Any

from agent.testing.set_default_account import (
    create_default_account_change_mock_testbed,
)

from ._shared import (
    ACCOUNTS,
    AutoAckMockBackend,
    MockBackend,
    Scenario,
    config,
    final_outcome,
    masked,
    next_answer,
    queue_account_resolved,
    queue_account_selection_required,
    queue_prepare,
    resume_account_selection,
    resume_request,
)

_PREPARE_PATH = "/api/v1/agent-tools/settings/default-account:prepare"
_EXECUTE_PATH = "/api/v1/agent-tools/settings/default-account"
_CONFIRMATION_VIEW = {
    "current_default_account": masked(ACCOUNTS[0]),
    "new_default_account": masked(ACCOUNTS[1]),
    "expires_at": "2026-12-31T23:59:59+09:00",
}


def _queue_execute_completed(backend: MockBackend, account_index: int) -> None:
    backend.add_success(
        "POST",
        _EXECUTE_PATH,
        {
            "outcome": "completed",
            "account_id": ACCOUNTS[account_index]["account_id"],
            "completed_at": "2026-12-31T23:59:59+09:00",
        },
    )


async def _resume_approval(
    testbed, thread_id: str, waiting, backend: MockBackend, answer: str
):
    """기본계좌 변경은 인증 단계가 없다 — approve 즉시 Execute가 이어진다."""

    confirmation_id = waiting.pending_interaction["confirmation_id"]
    if answer == "approve":
        _queue_execute_completed(backend, 1)
        return await testbed.resume(
            thread_id,
            resume_request(
                type="approval",
                confirmation_id=confirmation_id,
                approval_outcome="approved",
            ),
        )
    if answer == "cancel":
        return await testbed.resume(
            thread_id,
            resume_request(
                type="approval",
                confirmation_id=confirmation_id,
                approval_outcome="cancelled",
            ),
        )
    if answer == "account":
        queue_account_selection_required(backend)
        queue_prepare(backend, _PREPARE_PATH, _CONFIRMATION_VIEW)
        return await testbed.resume(
            thread_id,
            resume_request(
                type="approval",
                confirmation_id=confirmation_id,
                approval_outcome="change_requested",
            ),
        )
    raise ValueError(f"알 수 없는 approval 답: {answer!r}")


async def run_scenario(scenario: Scenario) -> dict[str, Any]:
    backend = AutoAckMockBackend()
    thread_id = f"path_{uuid.uuid4().hex[:8]}"
    scenario.setup(backend)

    visited: list[str] = []
    visit_counts: dict[str, int] = {}

    async with create_default_account_change_mock_testbed(
        backend, config(), thread_id=thread_id
    ) as testbed:
        result = await testbed.start(
            message=scenario.message,
            request_id="req_start",
            chat_session_id="chat_path_check",
            execution_context_id="exec_path_check",
        )

        while result.status == "waiting":
            step = result.pending_interaction["step_id"]  # type: ignore[index]
            visited.append(step)
            try:
                answer = next_answer(scenario.plan, visit_counts, step)
            except (KeyError, IndexError) as exc:
                return {
                    "path": visited,
                    "final_status": "plan_exhausted",
                    "error": str(exc),
                }

            if step == "request_default_account_selection":
                # 여기서 재개하면 Prepare가 곧장 이어진다 — 미리 큐잉해둔다.
                queue_prepare(backend, _PREPARE_PATH, _CONFIRMATION_VIEW)
                result = await resume_account_selection(
                    testbed, thread_id, result, answer
                )
            elif step == "request_default_account_approval":
                result = await _resume_approval(
                    testbed, thread_id, result, backend, answer
                )
            else:
                return {
                    "path": visited,
                    "final_status": "unhandled_step",
                    "error": f"드라이버가 못 다루는 step: {step}",
                }

        return await final_outcome(testbed, thread_id, visited, result)


SCENARIOS: list[Scenario] = [
    Scenario(
        name="default_account_happy_resolved",
        workflow="default_account",
        message="신한은행 계좌를 기본 출금 계좌로 설정해줘",
        setup=lambda backend: (
            queue_account_resolved(backend, 0),
            queue_prepare(backend, _PREPARE_PATH, _CONFIRMATION_VIEW),
        ),
        plan={"request_default_account_approval": "approve"},
        expected_path=["request_default_account_approval", "__terminal__:completed"],
    ),
    Scenario(
        name="default_account_no_hint_selection_required",
        workflow="default_account",
        message="기본계좌 바꾸고 싶어",
        setup=lambda backend: queue_account_selection_required(backend),
        plan={
            "request_default_account_selection": "2",
            "request_default_account_approval": "approve",
        },
        expected_path=[
            "request_default_account_selection",
            "request_default_account_approval",
            "__terminal__:completed",
        ],
    ),
    Scenario(
        name="default_account_change_requested_loop",
        workflow="default_account",
        message="신한은행 계좌를 기본 출금 계좌로 설정해줘",
        setup=lambda backend: (
            queue_account_resolved(backend, 0),
            queue_prepare(backend, _PREPARE_PATH, _CONFIRMATION_VIEW),
        ),
        plan={
            "request_default_account_approval": ["account", "approve"],
            "request_default_account_selection": "1",
        },
        expected_path=[
            "request_default_account_approval",
            "request_default_account_selection",
            "request_default_account_approval",
            "__terminal__:completed",
        ],
    ),
    Scenario(
        name="default_account_cancelled_at_approval",
        workflow="default_account",
        message="신한은행 계좌를 기본 출금 계좌로 설정해줘",
        setup=lambda backend: (
            queue_account_resolved(backend, 0),
            queue_prepare(backend, _PREPARE_PATH, _CONFIRMATION_VIEW),
        ),
        plan={"request_default_account_approval": "cancel"},
        expected_path=["request_default_account_approval", "__terminal__:completed"],
    ),
]
