"""wf_external_transfer(타인송금) 경로 검증 시나리오."""

from __future__ import annotations

import uuid
from typing import Any

from agent.testing.external_transfer import create_external_transfer_mock_testbed

from ._shared import (
    ACCOUNTS,
    AutoAckMockBackend,
    Scenario,
    config,
    final_outcome,
    masked,
    next_answer,
    queue_account_resolved,
    queue_prepare,
    queue_recipient_resolved,
    queue_recipient_selection_required,
    resume_account_selection,
    resume_amount,
    resume_approval,
    resume_authentication,
)

_PREPARE_PATH = "/api/v1/agent-tools/transfers/external:prepare"
_EXECUTE_PATH = "/api/v1/agent-tools/transfers/external"
_CONFIRMATION_VIEW = {
    "from_account": masked(ACCOUNTS[0]),
    "recipient": {
        "name": "받는 분",
        "bank_name": "국민은행",
        "masked_account_number": "222-***-456789",
    },
    "amount": 100000,
    "fee": 500,
    "total_debit": 100500,
    "currency": "KRW",
    "expires_at": "2026-12-31T23:59:59+09:00",
}


async def _resume_recipient_selection(testbed, thread_id: str, waiting, answer: str):
    input_request_id = waiting.pending_interaction["input_request_id"]
    if answer == "cancel":
        value = {
            "recipient_selection_outcome": "cancelled",
            "to_recipient_id": None,
            "to_recipient_candidate_id": None,
        }
    elif answer.startswith("new:"):
        value = {
            "recipient_selection_outcome": "selected",
            "to_recipient_id": None,
            "to_recipient_candidate_id": f"candidate_{uuid.uuid4().hex[:6]}",
        }
    else:
        value = {
            "recipient_selection_outcome": "selected",
            "to_recipient_id": f"recipient_{uuid.uuid4().hex[:6]}",
            "to_recipient_candidate_id": None,
        }
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

    async with create_external_transfer_mock_testbed(
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

            if step == "request_recipient_selection":
                # 여기서 재개하면 곧장 resolve_external_from_account가 돌고,
                # 금액이 이미 있으면 그다음 바로 Prepare까지 간다 — 둘 다
                # 미리 큐잉해둬야 한다(금액 입력 화면을 타는 시나리오라도
                # 안 쓰이는 응답이 남을 뿐 문제는 없다).
                queue_account_resolved(backend, 0)
                queue_prepare(backend, _PREPARE_PATH, _CONFIRMATION_VIEW)
                result = await _resume_recipient_selection(
                    testbed, thread_id, result, answer
                )
            elif step == "request_external_from_account_selection":
                queue_prepare(backend, _PREPARE_PATH, _CONFIRMATION_VIEW)
                result = await resume_account_selection(
                    testbed, thread_id, result, answer
                )
            elif step == "request_external_transfer_amount":
                result = await resume_amount(testbed, thread_id, result, answer)
            elif step == "request_external_transfer_approval":
                result = await resume_approval(
                    testbed,
                    thread_id,
                    result,
                    backend,
                    answer,
                    targets=("from_account", "recipient", "amount"),
                    prepare_path=_PREPARE_PATH,
                    confirmation_view=_CONFIRMATION_VIEW,
                )
            elif step == "request_external_authentication":
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
        name="external_happy_recipient_and_account_resolved",
        workflow="external_transfer",
        message="국민은행 계좌에서 철수에게 10만원 보내줘",
        setup=lambda backend: (
            queue_recipient_resolved(backend, "recipient_철수"),
            queue_account_resolved(backend, 0),
            queue_prepare(backend, _PREPARE_PATH, _CONFIRMATION_VIEW),
        ),
        plan={
            "request_external_transfer_approval": "approve",
            "request_external_authentication": "verified",
        },
        expected_path=[
            "request_external_transfer_approval",
            "request_external_authentication",
            "__terminal__:completed",
        ],
    ),
    Scenario(
        name="external_ambiguous_recipient_selection",
        workflow="external_transfer",
        message="국민은행 계좌에서 철수에게 10만원 보내줘",
        setup=lambda backend: queue_recipient_selection_required(backend),
        plan={
            "request_recipient_selection": "철수",
            "request_external_transfer_approval": "approve",
            "request_external_authentication": "verified",
        },
        expected_path=[
            "request_recipient_selection",
            "request_external_transfer_approval",
            "request_external_authentication",
            "__terminal__:completed",
        ],
    ),
    Scenario(
        name="external_no_recipient_hint",
        workflow="external_transfer",
        message="10만원 송금해줘",
        setup=lambda backend: None,
        plan={
            "request_recipient_selection": "new:이름모름",
            "request_external_transfer_approval": "approve",
            "request_external_authentication": "verified",
        },
        expected_path=[
            "request_recipient_selection",
            "request_external_transfer_approval",
            "request_external_authentication",
            "__terminal__:completed",
        ],
    ),
    Scenario(
        name="external_cancelled_at_approval",
        workflow="external_transfer",
        message="국민은행 계좌에서 철수에게 10만원 보내줘",
        setup=lambda backend: (
            queue_recipient_resolved(backend, "recipient_철수"),
            queue_account_resolved(backend, 0),
            queue_prepare(backend, _PREPARE_PATH, _CONFIRMATION_VIEW),
        ),
        plan={"request_external_transfer_approval": "cancel"},
        expected_path=[
            "request_external_transfer_approval",
            "__terminal__:completed",
        ],
    ),
]
