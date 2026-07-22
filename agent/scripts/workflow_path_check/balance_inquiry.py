"""wf_balance_inquiry(잔액조회) 경로 검증 시나리오."""

from __future__ import annotations

import uuid
from typing import Any

from agent.testing.balance_inquiry import create_balance_mock_testbed

from ._shared import (
    AutoAckMockBackend,
    MockBackend,
    Scenario,
    config,
    final_outcome,
    next_answer,
    queue_account_resolved,
    queue_account_selection_required,
    resume_account_selection,
)

_QUERY_PATH = "/api/v1/agent-tools/accounts/balances:query"


def _queue_query_success(backend: MockBackend) -> None:
    backend.add_success("POST", _QUERY_PATH, {"balance_results": []})


async def run_scenario(scenario: Scenario) -> dict[str, Any]:
    backend = AutoAckMockBackend()
    thread_id = f"path_{uuid.uuid4().hex[:8]}"
    scenario.setup(backend)

    visited: list[str] = []
    visit_counts: dict[str, int] = {}

    async with create_balance_mock_testbed(
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

            if step == "request_balance_account_selection":
                _queue_query_success(backend)
                result = await resume_account_selection(
                    testbed, thread_id, result, answer
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
        name="balance_inquiry_happy_no_pause",
        workflow="balance_inquiry",
        message="신한은행 계좌 잔액 얼마야",
        setup=lambda backend: (
            queue_account_resolved(backend, 0),
            _queue_query_success(backend),
        ),
        plan={},
        expected_path=["__terminal__:completed"],
    ),
    Scenario(
        name="balance_inquiry_no_hint_selection_required",
        workflow="balance_inquiry",
        message="잔액 알려줘",
        setup=lambda backend: queue_account_selection_required(backend),
        plan={"request_balance_account_selection": "1"},
        expected_path=[
            "request_balance_account_selection",
            "__terminal__:completed",
        ],
    ),
]
