"""wf_transaction_history(거래내역 조회) 경로 검증 시나리오."""

from __future__ import annotations

import uuid
from typing import Any

from agent.testing.transaction_history import create_transaction_history_mock_testbed

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

_QUERY_PATH = "/api/v1/agent-tools/transactions:query"


def _queue_query_success(backend: MockBackend) -> None:
    # TransactionQueryResult는 transaction_query_id가 필수(Pydantic 계약,
    # extra=forbid) — 빠뜨리면 Tool 응답 검증에서 조용히 실패해 emit_error로
    # 새는데, 경로만 보면 성공과 구분이 안 된다(실제로 겪은 버그).
    backend.add_success(
        "POST",
        _QUERY_PATH,
        {
            "transaction_results": [],
            "transaction_query_id": f"txn_query_{uuid.uuid4().hex[:8]}",
        },
    )


async def run_scenario(scenario: Scenario) -> dict[str, Any]:
    backend = AutoAckMockBackend()
    thread_id = f"path_{uuid.uuid4().hex[:8]}"
    scenario.setup(backend)

    visited: list[str] = []
    visit_counts: dict[str, int] = {}

    async with create_transaction_history_mock_testbed(
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

            if step == "request_transaction_account_selection":
                _queue_query_success(backend)
                result = await resume_account_selection(
                    testbed, thread_id, result, answer
                )
            elif step == "request_period_selection":
                _queue_query_success(backend)
                result = await resume_period_selection(
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
        name="transaction_history_happy_no_pause",
        workflow="transaction_history",
        message="신한은행 계좌 이번 달 거래내역 보여줘",
        setup=lambda backend: (
            queue_account_resolved(backend, 0),
            _queue_query_success(backend),
        ),
        plan={},
        expected_path=["__terminal__:completed"],
    ),
    Scenario(
        name="transaction_history_no_hint_selection_required",
        workflow="transaction_history",
        message="거래내역 보여줘",
        setup=lambda backend: queue_account_selection_required(backend),
        plan={"request_transaction_account_selection": "1"},
        expected_path=[
            "request_transaction_account_selection",
            "__terminal__:completed",
        ],
    ),
    Scenario(
        name="transaction_history_ambiguous_period_selection_required",
        workflow="transaction_history",
        message="신한은행 계좌 지난 분기 거래내역 보여줘",
        setup=lambda backend: queue_account_resolved(backend, 0),
        plan={"request_period_selection": "2026-04-01..2026-06-30"},
        expected_path=["request_period_selection", "__terminal__:completed"],
    ),
]
