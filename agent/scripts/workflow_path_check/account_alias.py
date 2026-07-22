"""wf_set_account_alias(계좌 별칭 변경) 경로 검증 시나리오."""

from __future__ import annotations

import uuid
from typing import Any

from agent.testing.set_account_alias import create_account_alias_change_mock_testbed

from ._shared import (
    ACCOUNTS,
    AutoAckMockBackend,
    MockBackend,
    Scenario,
    config,
    final_outcome,
    next_answer,
    queue_account_resolved,
    queue_account_selection_required,
    queue_prepare,
    resume_account_selection,
    resume_request,
)

_PREPARE_PATH = "/api/v1/agent-tools/settings/account-alias:prepare"
_EXECUTE_PATH = "/api/v1/agent-tools/settings/account-alias"
_CONFIRMATION_VIEW = {
    # AliasTargetAccountView는 account_id/bank_name/masked_account_number
    # 3개뿐이라(account_alias 없음, extra=forbid) masked()를 그대로 못 쓴다.
    "account": {
        "account_id": ACCOUNTS[0]["account_id"],
        "bank_name": ACCOUNTS[0]["bank_name"],
        "masked_account_number": ACCOUNTS[0]["masked_account_number"],
    },
    "alias": "여행 자금",
    "expires_at": "2026-12-31T23:59:59+09:00",
}


def _queue_execute_completed(
    backend: MockBackend, account_index: int, alias: str
) -> None:
    backend.add_success(
        "POST",
        _EXECUTE_PATH,
        {
            "outcome": "completed",
            "account_id": ACCOUNTS[account_index]["account_id"],
            "alias": alias,
            "completed_at": "2026-12-31T23:59:59+09:00",
        },
    )


async def _resume_alias_input(testbed, thread_id: str, waiting, answer: str):
    input_request_id = waiting.pending_interaction["input_request_id"]
    if answer == "cancel":
        value = {"alias_input_outcome": "cancelled"}
    else:
        value = {"alias_input_outcome": "submitted", "alias": answer}
    return await testbed.resume_input(
        agent_thread_id=thread_id,
        request_id=f"req_{uuid.uuid4().hex[:8]}",
        chat_session_id="chat_path_check",
        execution_context_id="exec_path_check",
        input_request_id=input_request_id,
        value=value,
    )


async def _resume_approval(
    testbed, thread_id: str, waiting, backend: MockBackend, answer: str
):
    confirmation_id = waiting.pending_interaction["confirmation_id"]
    if answer == "approve":
        _queue_execute_completed(backend, 0, "여행 자금")
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
        return await testbed.resume(
            thread_id,
            resume_request(
                type="approval",
                confirmation_id=confirmation_id,
                approval_outcome="change_requested",
                change_target="account",
            ),
        )
    if answer == "alias":
        return await testbed.resume(
            thread_id,
            resume_request(
                type="approval",
                confirmation_id=confirmation_id,
                approval_outcome="change_requested",
                change_target="alias",
            ),
        )
    raise ValueError(f"알 수 없는 approval 답: {answer!r}")


async def run_scenario(scenario: Scenario) -> dict[str, Any]:
    backend = AutoAckMockBackend()
    thread_id = f"path_{uuid.uuid4().hex[:8]}"
    scenario.setup(backend)

    visited: list[str] = []
    visit_counts: dict[str, int] = {}

    async with create_account_alias_change_mock_testbed(
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

            if step == "request_account_alias_selection":
                # alias가 메시지에 이미 있었으면 계좌 선택 직후 곧장 Prepare로
                # 간다 — 미리 큐잉해둔다(alias가 없어 입력 화면으로 가는
                # 시나리오에서는 그냥 안 쓰이고 남을 뿐 문제 없다).
                queue_prepare(backend, _PREPARE_PATH, _CONFIRMATION_VIEW)
                result = await resume_account_selection(
                    testbed, thread_id, result, answer
                )
            elif step == "request_account_alias_input":
                # alias가 채워지면 곧장 Prepare로 간다 — 미리 큐잉해둔다.
                queue_prepare(backend, _PREPARE_PATH, _CONFIRMATION_VIEW)
                result = await _resume_alias_input(testbed, thread_id, result, answer)
            elif step == "request_account_alias_approval":
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
        name="account_alias_happy_resolved_with_alias",
        workflow="account_alias",
        message="생활비 통장 별칭을 여행 자금으로 바꿔줘",
        setup=lambda backend: (
            queue_account_resolved(backend, 0),
            queue_prepare(backend, _PREPARE_PATH, _CONFIRMATION_VIEW),
        ),
        plan={"request_account_alias_approval": "approve"},
        expected_path=["request_account_alias_approval", "__terminal__:completed"],
    ),
    Scenario(
        name="account_alias_missing_alias_prompts_input",
        workflow="account_alias",
        message="생활비 통장 별칭 바꾸고 싶어",
        setup=lambda backend: queue_account_resolved(backend, 0),
        plan={
            "request_account_alias_input": "여행 자금",
            "request_account_alias_approval": "approve",
        },
        expected_path=[
            "request_account_alias_input",
            "request_account_alias_approval",
            "__terminal__:completed",
        ],
    ),
    Scenario(
        name="account_alias_no_hint_selection_required",
        workflow="account_alias",
        message="별칭 바꾸고 싶어",
        setup=lambda backend: queue_account_selection_required(backend),
        plan={
            "request_account_alias_selection": "1",
            "request_account_alias_input": "여행 자금",
            "request_account_alias_approval": "approve",
        },
        expected_path=[
            "request_account_alias_selection",
            "request_account_alias_input",
            "request_account_alias_approval",
            "__terminal__:completed",
        ],
    ),
    Scenario(
        name="account_alias_change_requested_account_target",
        workflow="account_alias",
        message="생활비 통장 별칭을 여행 자금으로 바꿔줘",
        setup=lambda backend: (
            queue_account_resolved(backend, 0),
            queue_prepare(backend, _PREPARE_PATH, _CONFIRMATION_VIEW),
        ),
        plan={
            "request_account_alias_approval": ["account", "approve"],
            "request_account_alias_selection": "2",
        },
        expected_path=[
            "request_account_alias_approval",
            "request_account_alias_selection",
            "request_account_alias_approval",
            "__terminal__:completed",
        ],
    ),
    Scenario(
        name="account_alias_change_requested_alias_target",
        workflow="account_alias",
        message="생활비 통장 별칭을 여행 자금으로 바꿔줘",
        setup=lambda backend: (
            queue_account_resolved(backend, 0),
            queue_prepare(backend, _PREPARE_PATH, _CONFIRMATION_VIEW),
        ),
        plan={
            "request_account_alias_approval": ["alias", "approve"],
            "request_account_alias_input": "커피값",
        },
        expected_path=[
            "request_account_alias_approval",
            "request_account_alias_input",
            "request_account_alias_approval",
            "__terminal__:completed",
        ],
    ),
    Scenario(
        name="account_alias_cancelled_at_approval",
        workflow="account_alias",
        message="생활비 통장 별칭을 여행 자금으로 바꿔줘",
        setup=lambda backend: (
            queue_account_resolved(backend, 0),
            queue_prepare(backend, _PREPARE_PATH, _CONFIRMATION_VIEW),
        ),
        plan={"request_account_alias_approval": "cancel"},
        expected_path=["request_account_alias_approval", "__terminal__:completed"],
    ),
]
