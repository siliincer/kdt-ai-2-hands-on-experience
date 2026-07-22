"""wf_period_amount_summary(기간 합계 조회) 경로 검증 시나리오."""

from __future__ import annotations

import uuid
from typing import Any

from agent.testing.period_amount_summary import (
    create_period_amount_summary_mock_testbed,
)

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
    resume_period_selection,
)

_SUMMARY_PATH = "/api/v1/agent-tools/transactions:summary"


def _queue_query_success(backend: MockBackend) -> None:
    # TransactionSummaryResult는 summary_result(중첩 객체)가 필수다.
    backend.add_success(
        "POST",
        _SUMMARY_PATH,
        {
            "summary_result": {
                "summary_type": "spending",
                "total_amount": 100000,
                "transaction_count": 3,
                "currency": "KRW",
                "start_date": "2026-07-01",
                "end_date": "2026-07-21",
            }
        },
    )


async def _resume_summary_type_selection(testbed, thread_id: str, waiting, answer: str):
    input_request_id = waiting.pending_interaction["input_request_id"]
    if answer == "cancel":
        value = {"summary_type_selection_outcome": "cancelled"}
    else:
        value = {"summary_type_selection_outcome": "selected", "summary_type": answer}
    return await testbed.resume_input(
        agent_thread_id=thread_id,
        request_id=f"req_{uuid.uuid4().hex[:8]}",
        chat_session_id="chat_path_check",
        execution_context_id="exec_path_check",
        input_request_id=input_request_id,
        value=value,
    )


async def run_scenario(scenario: Scenario) -> dict[str, Any]:
    backend = AutoAckMockBackend()
    thread_id = f"path_{uuid.uuid4().hex[:8]}"
    scenario.setup(backend)

    visited: list[str] = []
    visit_counts: dict[str, int] = {}

    async with create_period_amount_summary_mock_testbed(
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

            if step == "request_summary_account_selection":
                _queue_query_success(backend)
                result = await resume_account_selection(
                    testbed, thread_id, result, answer
                )
            elif step == "request_period_selection":
                _queue_query_success(backend)
                result = await resume_period_selection(
                    testbed, thread_id, result, answer
                )
            elif step == "request_summary_type":
                _queue_query_success(backend)
                result = await _resume_summary_type_selection(
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
        name="period_amount_summary_happy_no_pause",
        workflow="period_amount_summary",
        message="신한은행 계좌 이번 달 지출 얼마나 했어",
        setup=lambda backend: (
            queue_account_resolved(backend, 0),
            _queue_query_success(backend),
        ),
        plan={},
        expected_path=["__terminal__:completed"],
    ),
    Scenario(
        name="period_amount_summary_no_hint_selection_required",
        workflow="period_amount_summary",
        message="지출 얼마나 했어",
        setup=lambda backend: queue_account_selection_required(backend),
        plan={"request_summary_account_selection": "1"},
        expected_path=[
            "request_summary_account_selection",
            "__terminal__:completed",
        ],
    ),
    Scenario(
        name="period_amount_summary_summary_type_selection_required",
        workflow="period_amount_summary",
        message="신한은행 계좌 이번 달 거래 내역 정리해줘",
        setup=lambda backend: queue_account_resolved(backend, 0),
        plan={"request_summary_type": "spending"},
        expected_path=["request_summary_type", "__terminal__:completed"],
    ),
]
