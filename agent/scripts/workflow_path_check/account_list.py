"""wf_account_list(계좌 목록 조회) 경로 검증 시나리오.

HITL 지점이 아예 없다 — extract → fetch → emit_result/emit_error뿐이라
매번 한 번에 끝난다.
"""

from __future__ import annotations

import uuid
from typing import Any

from agent.testing.account_list import create_account_list_mock_testbed

from ._shared import (
    AutoAckMockBackend,
    Scenario,
    config,
    final_outcome,
    queue_account_resolved,
)


async def run_scenario(scenario: Scenario) -> dict[str, Any]:
    backend = AutoAckMockBackend()
    thread_id = f"path_{uuid.uuid4().hex[:8]}"
    scenario.setup(backend)

    async with create_account_list_mock_testbed(
        backend, config(), thread_id=thread_id
    ) as testbed:
        result = await testbed.start(
            message=scenario.message,
            request_id="req_start",
            chat_session_id="chat_path_check",
            execution_context_id="exec_path_check",
        )
        if result.status == "waiting":
            step = result.pending_interaction["step_id"]  # type: ignore[index]
            return {
                "path": [step],
                "final_status": "unhandled_step",
                "error": f"드라이버가 못 다루는 step: {step}",
            }
        return await final_outcome(testbed, thread_id, [], result)


SCENARIOS: list[Scenario] = [
    Scenario(
        name="account_list_happy",
        workflow="account_list",
        message="신한은행 계좌들 보여줘",
        setup=lambda backend: queue_account_resolved(backend, 0),
        plan={},
        expected_path=["__terminal__:completed"],
    ),
]
