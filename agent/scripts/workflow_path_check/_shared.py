"""8개 워크플로우 모듈이 공유하는 Fixture와 실행 엔진.

Mock 계좌 데이터, `AutoAckMockBackend`, `Scenario`/`next_answer`/`final_outcome`
같은 시나리오 실행 엔진, 그리고 계좌 선택·금액 입력·승인(송금 계열)·인증처럼
2개 이상의 워크플로우가 그대로 재사용하는 범용 Resume 드라이버만 모아둔다.
워크플로우 하나에만 쓰이는 것(수취인 선택, 별칭 입력, 기간/합계유형 선택 등은
하나만 예외, 아래 참고)은 각자의 워크플로우 파일에 둔다.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import SecretStr

from agent.clients.backend import BackendClientConfig
from agent.runtime.hitl import ExecutionResumeRequest
from agent.testing.mock_backend import MockBackend

WEBHOOK_PATH = "/api/v1/webhooks/agent"
ACCOUNTS_PATH = "/api/v1/agent-tools/accounts"
AUTH_CONTEXT_PATH = "/api/v1/agent-tools/auth-contexts"
RECIPIENT_RESOLVE_PATH = "/api/v1/agent-tools/recipients:resolve"

ACCOUNTS = [
    {
        "account_id": "acc_001",
        "bank_name": "신한은행",
        "account_alias": "생활비 통장",
        "account_type": "checking",
        "masked_account_number": "110-***-123456",
        "currency": "KRW",
        "is_default": True,
        "status": "active",
    },
    {
        "account_id": "acc_002",
        "bank_name": "토스뱅크",
        "account_alias": "여행 적금",
        "account_type": "checking",
        "masked_account_number": "1000-***-654321",
        "currency": "KRW",
        "is_default": False,
        "status": "active",
    },
]


class AutoAckMockBackend(MockBackend):
    """Webhook 발신은 내용 무관하게 항상 성공시키는 Mock Backend."""

    def handler(self, request):  # noqa: ANN001
        if request.url.path == WEBHOOK_PATH:
            import httpx

            self.requests.append(request)
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "message": "처리 완료",
                    "data": {"message_id": f"msg_{uuid.uuid4().hex[:8]}"},
                },
            )
        return super().handler(request)


def config() -> BackendClientConfig:
    return BackendClientConfig(
        base_url="http://backend.test",
        agent_service_token=SecretStr("agent-service-token"),
        agent_webhook_secret=SecretStr("agent-webhook-secret"),
        retry_backoff_seconds=0,
    )


def masked(account: dict[str, Any]) -> dict[str, Any]:
    return {
        "account_id": account["account_id"],
        "bank_name": account["bank_name"],
        "account_alias": account["account_alias"],
        "masked_account_number": account["masked_account_number"],
    }


def queue_account_selection_required(backend: MockBackend) -> None:
    backend.add_success(
        "GET",
        ACCOUNTS_PATH,
        {
            "account_resolution_outcome": "selection_required",
            "accounts": ACCOUNTS,
            "account_ids": [],
        },
    )


def queue_account_resolved(backend: MockBackend, account_index: int) -> None:
    account = ACCOUNTS[account_index]
    backend.add_success(
        "GET",
        ACCOUNTS_PATH,
        {
            "account_resolution_outcome": "resolved",
            "accounts": [account],
            "account_ids": [account["account_id"]],
        },
    )


def queue_prepare(
    backend: MockBackend, prepare_path: str, confirmation_view: dict
) -> None:
    backend.add_success(
        "POST",
        prepare_path,
        {
            "outcome": "ready_for_confirmation",
            "confirmation_id": f"confirm_{uuid.uuid4().hex[:6]}",
            "confirmation_view": confirmation_view,
        },
    )


def queue_recipient_resolved(backend: MockBackend, recipient_id: str) -> None:
    backend.add_success(
        "POST",
        RECIPIENT_RESOLVE_PATH,
        {"outcome": "resolved", "to_recipient_id": recipient_id},
    )


def queue_recipient_selection_required(backend: MockBackend) -> None:
    """external_transfer(자기 시나리오용)와 global_entry(라우팅 확인 중
    불가피하게 발생하는 Tool 호출을 죽지 않게 하는 용도) 둘 다 쓴다."""

    backend.add_success(
        "POST",
        RECIPIENT_RESOLVE_PATH,
        {"outcome": "selection_required", "selection_reason": "multiple_matches"},
    )


def resume_request(**resume: object) -> ExecutionResumeRequest:
    return ExecutionResumeRequest.model_validate(
        {
            "request_id": f"req_{uuid.uuid4().hex[:8]}",
            "chat_session_id": "chat_path_check",
            "execution_context_id": "exec_path_check",
            "resume": resume,
        }
    )


WorkflowName = Literal[
    "internal_transfer",
    "external_transfer",
    "default_account",
    "account_alias",
    "account_list",
    "balance_inquiry",
    "transaction_history",
    "period_amount_summary",
]


@dataclass(frozen=True)
class Scenario:
    """시나리오 하나 — 어떤 메시지로 시작해서 어떤 step 순서를 밟아야 하는가."""

    name: str
    workflow: WorkflowName
    message: str
    setup: Any  # Callable[[MockBackend], None] — start() 전에 큐잉할 것들
    plan: dict[str, str | list[str]]  # step_id -> 그 step에서 낼 답 (반복 방문은 list)
    expected_path: list[str]  # 마지막 원소는 "__terminal__:<status>"


def next_answer(plan: dict[str, Any], visit_counts: dict[str, int], step: str) -> str:
    visit_counts[step] = visit_counts.get(step, 0) + 1
    raw = plan.get(step)
    if raw is None:
        raise KeyError(f"시나리오 계획에 없는 step: {step}")
    if isinstance(raw, list):
        idx = visit_counts[step] - 1
        if idx >= len(raw):
            raise IndexError(f"{step} 방문 횟수가 시나리오 계획보다 많습니다.")
        return raw[idx]
    return raw


async def resume_account_selection(testbed, thread_id: str, waiting, answer: str):
    input_request_id = waiting.pending_interaction["input_request_id"]
    if answer == "cancel":
        value = {"account_selection_outcome": "cancelled", "account_ids": []}
    else:
        account_id = ACCOUNTS[int(answer) - 1]["account_id"]
        value = {"account_selection_outcome": "selected", "account_ids": [account_id]}
    return await testbed.resume_input(
        agent_thread_id=thread_id,
        request_id=f"req_{uuid.uuid4().hex[:8]}",
        chat_session_id="chat_path_check",
        execution_context_id="exec_path_check",
        input_request_id=input_request_id,
        value=value,
    )


async def resume_amount(testbed, thread_id: str, waiting, answer: str):
    input_request_id = waiting.pending_interaction["input_request_id"]
    if answer == "cancel":
        value = {"amount_input_outcome": "cancelled"}
    else:
        value = {"amount_input_outcome": "submitted", "amount": int(answer)}
    return await testbed.resume_input(
        agent_thread_id=thread_id,
        request_id=f"req_{uuid.uuid4().hex[:8]}",
        chat_session_id="chat_path_check",
        execution_context_id="exec_path_check",
        input_request_id=input_request_id,
        value=value,
    )


async def resume_approval(
    testbed,
    thread_id: str,
    waiting,
    backend: MockBackend,
    answer: str,
    *,
    targets: tuple[str, ...],
    prepare_path: str,
    confirmation_view: dict,
):
    """송금 계열(본인이체·타인송금) 승인 화면 — approve 뒤에 인증이 이어진다."""

    confirmation_id = waiting.pending_interaction["confirmation_id"]
    if answer == "approve":
        backend.add_success(
            "POST",
            AUTH_CONTEXT_PATH,
            {
                "outcome": "authentication_required",
                "auth_context_id": f"auth_{uuid.uuid4().hex[:6]}",
                "auth_request_view": {
                    "title": "본인 인증이 필요합니다.",
                    "available_methods": ["biometric"],
                    "expires_at": "2026-12-31T23:59:59+09:00",
                },
            },
        )
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
    if answer in targets:
        if answer != "amount":
            queue_account_selection_required(backend)
        queue_prepare(backend, prepare_path, confirmation_view)
        return await testbed.resume(
            thread_id,
            resume_request(
                type="approval",
                confirmation_id=confirmation_id,
                approval_outcome="change_requested",
                change_target=answer,
            ),
        )
    raise ValueError(f"알 수 없는 approval 답: {answer!r}")


async def resume_authentication(
    testbed,
    thread_id: str,
    waiting,
    backend: MockBackend,
    answer: str,
    execute_path: str,
):
    auth_context_id = waiting.pending_interaction["auth_context_id"]
    if answer == "verified":
        backend.add_success(
            "POST",
            execute_path,
            {
                "outcome": "completed",
                "transaction_id": f"txn_{uuid.uuid4().hex[:8]}",
                "completed_at": "2026-12-31T23:59:59+09:00",
            },
        )
    return await testbed.resume(
        thread_id,
        resume_request(
            type="authentication",
            auth_context_id=auth_context_id,
            auth_status=answer,
        ),
    )


async def resume_period_selection(testbed, thread_id: str, waiting, answer: str):
    """조회 기간 선택 — transaction_history/period_amount_summary가 공유한다."""

    input_request_id = waiting.pending_interaction["input_request_id"]
    if answer == "cancel":
        value = {"period_selection_outcome": "cancelled"}
    else:
        start_date, end_date = answer.split("..")
        value = {
            "period_selection_outcome": "selected",
            "start_date": start_date,
            "end_date": end_date,
        }
    return await testbed.resume_input(
        agent_thread_id=thread_id,
        request_id=f"req_{uuid.uuid4().hex[:8]}",
        chat_session_id="chat_path_check",
        execution_context_id="exec_path_check",
        input_request_id=input_request_id,
        value=value,
    )


async def final_outcome(
    testbed, thread_id: str, visited: list[str], result
) -> dict[str, Any]:
    """경로가 기대와 같아도 조용히 emit_error로 샌 건 아닌지 한 번 더 본다.

    Mock 응답이 실제 Tool 계약(필수 필드 등)과 안 맞으면 Tool 호출이
    조용히 예외로 처리돼 emit_error로 빠지는데, 그래도 top-level
    상태는 다른 정상 종료와 똑같이 "completed"라 경로 길이만 봐서는
    구분이 안 된다(실제로 이 버그를 한 번 놓칠 뻔했다). 내부 State의
    safe_error_message 유무로 한 번 더 검증한다.
    """

    visited = [*visited, f"__terminal__:{result.status}"]
    state = await testbed.state(thread_id)
    safe_error = state.get("data", {}).get("safe_error_message")
    if safe_error is not None:
        return {"path": visited, "final_status": "silent_error", "error": safe_error}
    return {"path": visited, "final_status": result.status, "error": None}
