"""wf_internal_transfer(본인이체) 경로 검증 시나리오."""

from __future__ import annotations

import uuid
from typing import Any

from agent.testing.internal_transfer import create_internal_transfer_mock_testbed

from ._shared import (
    ACCOUNTS,
    AutoAckMockBackend,
    Scenario,
    config,
    final_outcome,
    masked,
    next_answer,
    queue_account_resolved,
    queue_account_selection_required,
    queue_prepare,
    resume_account_selection,
    resume_amount,
    resume_approval,
    resume_authentication,
)

_PREPARE_PATH = "/api/v1/agent-tools/transfers/internal:prepare"
_EXECUTE_PATH = "/api/v1/agent-tools/transfers/internal"
_CONFIRMATION_VIEW = {
    "from_account": masked(ACCOUNTS[0]),
    "to_account": masked(ACCOUNTS[1]),
    "amount": 100000,
    "fee": 0,
    "total_debit": 100000,
    "currency": "KRW",
    "expires_at": "2026-12-31T23:59:59+09:00",
}


async def run_scenario(scenario: Scenario) -> dict[str, Any]:
    backend = AutoAckMockBackend()
    thread_id = f"path_{uuid.uuid4().hex[:8]}"
    scenario.setup(backend)

    visited: list[str] = []
    visit_counts: dict[str, int] = {}

    async with create_internal_transfer_mock_testbed(
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

            if step == "request_from_account_selection":
                # 여기서 재개하면 곧장 resolve_internal_to_account가 또
                # 계좌 조회를 한다 — 그 응답을 미리 큐잉해둬야 한다.
                queue_account_selection_required(backend)
                result = await resume_account_selection(
                    testbed, thread_id, result, answer
                )
            elif step == "request_to_account_selection":
                queue_prepare(backend, _PREPARE_PATH, _CONFIRMATION_VIEW)
                result = await resume_account_selection(
                    testbed, thread_id, result, answer
                )
            elif step == "request_internal_transfer_amount":
                result = await resume_amount(testbed, thread_id, result, answer)
            elif step == "request_internal_transfer_approval":
                result = await resume_approval(
                    testbed,
                    thread_id,
                    result,
                    backend,
                    answer,
                    targets=("from_account", "to_account", "amount"),
                    prepare_path=_PREPARE_PATH,
                    confirmation_view=_CONFIRMATION_VIEW,
                )
            elif step == "request_internal_authentication":
                result = await resume_authentication(
                    testbed, thread_id, result, backend, answer, _EXECUTE_PATH
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
        name="internal_happy_both_resolved",
        workflow="internal_transfer",
        message="생활비 통장에서 여행 적금으로 10만원 이체해줘",
        setup=lambda backend: (
            queue_account_resolved(backend, 0),
            queue_account_resolved(backend, 1),
            queue_prepare(backend, _PREPARE_PATH, _CONFIRMATION_VIEW),
        ),
        plan={
            "request_internal_transfer_approval": "approve",
            "request_internal_authentication": "verified",
        },
        expected_path=[
            "request_internal_transfer_approval",
            "request_internal_authentication",
            "__terminal__:completed",
        ],
    ),
    Scenario(
        name="internal_missing_amount_both_resolved",
        workflow="internal_transfer",
        message="생활비 통장에서 여행 적금으로 이체해줘",
        setup=lambda backend: (
            queue_account_resolved(backend, 0),
            queue_account_resolved(backend, 1),
            queue_prepare(backend, _PREPARE_PATH, _CONFIRMATION_VIEW),
        ),
        plan={
            "request_internal_transfer_amount": "100000",
            "request_internal_transfer_approval": "approve",
            "request_internal_authentication": "verified",
        },
        expected_path=[
            "request_internal_transfer_amount",
            "request_internal_transfer_approval",
            "request_internal_authentication",
            "__terminal__:completed",
        ],
    ),
    Scenario(
        name="internal_no_hints_selection_required",
        workflow="internal_transfer",
        message="이체해줘",
        setup=lambda backend: queue_account_selection_required(backend),
        plan={
            "request_from_account_selection": "1",
            "request_to_account_selection": "2",
            "request_internal_transfer_amount": "100000",
            "request_internal_transfer_approval": "approve",
            "request_internal_authentication": "verified",
        },
        expected_path=[
            "request_from_account_selection",
            "request_to_account_selection",
            "request_internal_transfer_amount",
            "request_internal_transfer_approval",
            "request_internal_authentication",
            "__terminal__:completed",
        ],
    ),
    Scenario(
        name="internal_change_requested_amount_loop",
        workflow="internal_transfer",
        message="생활비 통장에서 여행 적금으로 10만원 이체해줘",
        setup=lambda backend: (
            queue_account_resolved(backend, 0),
            queue_account_resolved(backend, 1),
            queue_prepare(backend, _PREPARE_PATH, _CONFIRMATION_VIEW),
        ),
        plan={
            "request_internal_transfer_approval": ["amount", "approve"],
            "request_internal_transfer_amount": "300000",
            "request_internal_authentication": "verified",
        },
        expected_path=[
            "request_internal_transfer_approval",
            "request_internal_transfer_amount",
            "request_internal_transfer_approval",
            "request_internal_authentication",
            "__terminal__:completed",
        ],
    ),
    Scenario(
        name="internal_cancelled_at_approval",
        workflow="internal_transfer",
        message="생활비 통장에서 여행 적금으로 10만원 이체해줘",
        setup=lambda backend: (
            queue_account_resolved(backend, 0),
            queue_account_resolved(backend, 1),
            queue_prepare(backend, _PREPARE_PATH, _CONFIRMATION_VIEW),
        ),
        plan={"request_internal_transfer_approval": "cancel"},
        expected_path=[
            "request_internal_transfer_approval",
            "__terminal__:completed",
        ],
    ),
]
