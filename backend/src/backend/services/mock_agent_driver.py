"""mock 에이전트 드라이버.

실제 Agent(LangGraph)가 스텁이라, /chat·/approve 가 이 드라이버를 백그라운드로 돌려
agent:stream:{chat_session_id} 에 status/tool_call/need_approval/done 을 XADD 한다.
→ FE(assistant-ui)의 스트리밍·confirm(HITL) 루프를 에이전트 없이 검증할 수 있다.

실제 Agent 연동 시 이 파일을 걷어내고, Agent 가 웹훅(POST /webhooks/agent) 또는
직접 XADD 로 동일 이벤트를 보내면 된다.
"""

import asyncio
import logging
import re
from uuid import UUID, uuid4

import redis.asyncio as aioredis

from ..db.postgres import AsyncSessionLocal
from ..db.redis import stream_pool
from ..schemas.sse import AgentStreamEvent, AgentStreamEventType
from .agent_stream_producer import publish_agent_event
from .mock.hitl_fixtures import (
    BALANCE_ACCOUNTS,
    UI_BALANCE_ACCOUNT_SELECTION,
    build_balance_result,
)
from .pending_input_service import register_pending_input

logger = logging.getLogger(__name__)

_STEP_DELAY_SECONDS = 0.5

# 송금 의도로 볼 키워드
_TRANSFER_KEYWORDS = ("송금", "보내", "이체", "transfer")

# 자동이체(정기결제) 등록 의도 키워드. "이체"를 포함하므로 송금보다 먼저 검사한다.
_AUTOTRANSFER_KEYWORDS = (
    "자동이체",
    "정기이체",
    "정기결제",
    "정기 결제",
    "autotransfer",
)

# 읽기전용 카드 의도 → component 키 (앞쪽 우선 매칭)
_COMPONENT_KEYWORDS: list[tuple[tuple[str, ...], str]] = [
    (("잔액", "자산", "balance"), "balance"),
    (("소비", "지출", "spending"), "spending"),
    (("거래 내역", "거래내역", "내역", "transactions"), "transactions"),
    (("예산", "구독", "budget"), "budget"),
    (("카드", "청구서", "cards"), "cards"),
]

# component 별 안내 문구(status/component/done 텍스트)
_COMPONENT_MESSAGES: dict[str, tuple[str, str]] = {
    "balance": ("자산 현황을 불러왔어요.", "다른 도움이 필요하시면 말씀해 주세요."),
    "spending": (
        "이번 달 소비 분석을 준비했어요.",
        "카테고리를 눌러 상세 내역을 볼 수 있어요.",
    ),
    "transactions": ("거래 내역을 불러왔어요.", "월을 선택해 기간별로 확인해 보세요."),
    "budget": ("예산 현황을 불러왔어요.", "예산과 구독을 관리해 보세요."),
    "cards": ("보유하신 카드를 불러왔어요.", "카드를 눌러 자세히 확인해 보세요."),
}

# 파싱 실패 시 사용할 샘플(스크린샷 기준)
_SAMPLE_ARGS = {
    "name": "김철수",
    "bank": "하나은행",
    "account": "110-123-456789",
    "amount": "30000",
    "time": "지금 바로",
}

# 자동이체 confirm 폼 프리필 샘플(파싱 실패 시)
_AUTOTRANSFER_SAMPLE_ARGS = {
    "account": "우리은행 1002-345-678901",
    "amount": "200000",
    "day": "매월 25일",
}


def _is_autotransfer_intent(message: str) -> bool:
    return any(keyword in message for keyword in _AUTOTRANSFER_KEYWORDS)


def _is_transfer_intent(message: str) -> bool:
    return any(keyword in message for keyword in _TRANSFER_KEYWORDS)


def _match_component(message: str) -> str | None:
    """읽기전용 카드 의도면 component 키를 반환."""
    for keywords, component in _COMPONENT_KEYWORDS:
        if any(keyword in message for keyword in keywords):
            return component
    return None


def _extract_transfer_args(message: str) -> dict[str, str]:
    """메시지에서 송금 파라미터를 가볍게 파싱(목). 실패 필드는 샘플로 채운다."""
    args = dict(_SAMPLE_ARGS)

    # 금액: "30,000원" / "3만원" 대략 처리 → 숫자만
    amount_match = re.search(r"([\d,]{1,20})\s*원", message)
    if amount_match:
        args["amount"] = amount_match.group(1).replace(",", "")

    # 계좌번호: 숫자/하이픈 6자리 이상
    account_match = re.search(r"\d[\d-]{5,}", message)
    if account_match:
        args["account"] = account_match.group(0)

    return args


def _extract_autotransfer_args(message: str) -> dict[str, str]:
    """메시지에서 자동이체 파라미터를 가볍게 파싱(목). 실패 필드는 샘플로 채운다."""
    args = dict(_AUTOTRANSFER_SAMPLE_ARGS)

    amount_match = re.search(r"([\d,]{1,20})\s*원", message)
    if amount_match:
        args["amount"] = amount_match.group(1).replace(",", "")

    # 이체일: "매월 25일" / "25일"
    day_match = re.search(r"(매월\s*)?(\d{1,2})\s*일", message)
    if day_match:
        args["day"] = f"매월 {day_match.group(2)}일"

    return args


async def _emit(
    redis_stream: aioredis.Redis,
    chat_session_id: UUID,
    event_type: AgentStreamEventType,
    content: str,
    *,
    approval_id: str | None = None,
    metadata: dict | None = None,
    delay: bool = True,
) -> None:
    if delay:
        await asyncio.sleep(_STEP_DELAY_SECONDS)
    await publish_agent_event(
        redis_stream,
        chat_session_id,
        AgentStreamEvent(
            event_type=event_type,
            content=content,
            approval_id=approval_id,
            metadata=metadata,
        ),
    )


async def _register_pending_input(
    chat_session_id: UUID,
    input_request_id: str,
    ui_contract_id: str,
    ui_type: str,
    execution_context_id: UUID | None,
    agent_thread_id: str | None,
) -> None:
    """need_input 발행 전에 대기 행을 DB 에 영속한다(계약 1.4·1.5).

    실 Agent 는 Webhook 경로로 영속되지만, in-process mock 은 자체 세션으로 등록한다.
    """
    async with AsyncSessionLocal() as session:
        await register_pending_input(
            session,
            chat_session_id=chat_session_id,
            input_request_id=input_request_id,
            ui_contract_id=ui_contract_id,
            ui_type=ui_type,
            execution_context_id=execution_context_id,
            agent_thread_id=agent_thread_id,
        )


async def run_initial_turn(
    chat_session_id: UUID,
    message: str,
    execution_context_id: UUID | None = None,
    agent_thread_id: str | None = None,
) -> None:
    """사용자 메시지에 대한 첫 턴을 스트림에 발행한다.

    송금 의도면 need_approval(confirm 카드)까지 발행하고 멈춘다(승인 대기).
    잔액 의도면 need_input(계좌 선택)까지 발행하고 멈춘다(wf_balance_inquiry 입력 대기).
    그 외에는 간단한 답변 후 done.
    """
    redis_stream = aioredis.Redis(connection_pool=stream_pool)
    try:
        # 자동이체는 "이체"를 포함하므로 송금보다 먼저 검사한다.
        if _is_autotransfer_intent(message):
            args = _extract_autotransfer_args(message)
            approval_id = uuid4().hex
            await _emit(
                redis_stream,
                chat_session_id,
                AgentStreamEventType.STATUS,
                "자동이체 등록을 도와드릴게요. 정보를 확인해 주세요.",
                delay=False,
            )
            await _emit(
                redis_stream,
                chat_session_id,
                AgentStreamEventType.NEED_APPROVAL,
                "아래 내용으로 자동이체를 등록할까요? 각 항목을 수정할 수 있어요.",
                approval_id=approval_id,
                metadata={"tool": "autotransfer", "args": args},
            )
            # 승인 대기 — done 을 보내지 않고 종료(스트림은 열린 채 유지)
            return

        if _is_transfer_intent(message):
            args = _extract_transfer_args(message)
            approval_id = uuid4().hex
            await _emit(
                redis_stream,
                chat_session_id,
                AgentStreamEventType.STATUS,
                "요청을 이해했어요. 송금 정보를 확인할게요.",
                delay=False,
            )
            await _emit(
                redis_stream,
                chat_session_id,
                AgentStreamEventType.TOOL_CALL,
                "받는 분 계좌 정보를 조회하고 있어요...",
                metadata={"tool": "lookup_account"},
            )
            await _emit(
                redis_stream,
                chat_session_id,
                AgentStreamEventType.NEED_APPROVAL,
                "아래 정보로 송금할까요? 각 항목을 확인하고 수정할 수 있어요.",
                approval_id=approval_id,
                metadata={"tool": "transfer", "args": args},
            )
            # 승인 대기 — done 을 보내지 않고 종료(스트림은 열린 채 유지)
            return

        component = _match_component(message)
        if component == "balance":
            # 잔액 조회는 계약 wf_balance_inquiry: 계좌 선택(need_input) → 잔액 결과.
            await _run_balance_account_selection(
                redis_stream, chat_session_id, execution_context_id, agent_thread_id
            )
            return

        if component is not None:
            # 읽기전용 카드: 데이터는 싣지 않고 렌더 시그널만(ADR-002).
            # FE 가 UI Data API 로 데이터를 별도 fetch 한다.
            component_text, done_text = _COMPONENT_MESSAGES[component]
            await _emit(
                redis_stream,
                chat_session_id,
                AgentStreamEventType.STATUS,
                "정보를 조회하고 있어요...",
                delay=False,
            )
            await _emit(
                redis_stream,
                chat_session_id,
                AgentStreamEventType.COMPONENT,
                component_text,
                metadata={"component": component},
            )
            await _emit(
                redis_stream,
                chat_session_id,
                AgentStreamEventType.DONE,
                done_text,
            )
            return

        # 일반 대화(목)
        await _emit(
            redis_stream,
            chat_session_id,
            AgentStreamEventType.STATUS,
            "생각하고 있어요...",
            delay=False,
        )
        answer_chunks = (
            "무엇을 ",
            "도와드릴까요? ",
            "송금, 잔액 조회, ",
            "거래내역, 예산관리, 잔액조회, "
            "자동이체등록, 카드관리, "
            "소비 분석을 할 수 있어요.",
        )
        for chunk in answer_chunks:
            await _emit(
                redis_stream, chat_session_id, AgentStreamEventType.TOKEN, chunk
            )
        await _emit(
            redis_stream,
            chat_session_id,
            AgentStreamEventType.DONE,
            "무엇이든 말씀해 주세요.",
        )
    finally:
        await redis_stream.aclose()


async def _run_balance_account_selection(
    redis_stream: aioredis.Redis,
    chat_session_id: UUID,
    execution_context_id: UUID | None,
    agent_thread_id: str | None,
) -> None:
    """wf_balance_inquiry: 잔액 조회 계좌 선택을 need_input 으로 요청한다(계약 5.3)."""
    input_request_id = f"input_balance_{uuid4().hex[:12]}"
    await _emit(
        redis_stream,
        chat_session_id,
        AgentStreamEventType.STATUS,
        "잔액을 조회할 계좌를 확인하고 있어요...",
        delay=False,
    )
    # need_input 발행 전에 대기 행을 먼저 만든다(FE 즉시 제출 대비, 계약 1.5).
    await _register_pending_input(
        chat_session_id,
        input_request_id,
        UI_BALANCE_ACCOUNT_SELECTION,
        "account_card_list",
        execution_context_id,
        agent_thread_id,
    )
    await _emit(
        redis_stream,
        chat_session_id,
        AgentStreamEventType.NEED_INPUT,
        "잔액을 조회할 계좌를 선택해 주세요.",
        metadata={
            "input_request_id": input_request_id,
            "ui_contract_id": UI_BALANCE_ACCOUNT_SELECTION,
            "ui": {
                "type": "account_card_list",
                "payload": {
                    "title": "잔액을 조회할 계좌를 선택해 주세요.",
                    "accounts": BALANCE_ACCOUNTS,
                    "actions": ["select", "cancel"],
                },
            },
        },
    )
    # 입력 대기 — done 을 보내지 않고 종료(스트림은 열린 채 유지)


async def run_after_input(
    chat_session_id: UUID,
    ui_contract_id: str,
    value: dict,
) -> None:
    """일반 입력·선택 대기 회신 이후의 후속 턴을 발행한다(UI-HITL 계약 1.5).

    `ui_contract_id` 로 어떤 워크플로우를 이어갈지 분기한다.
    """
    redis_stream = aioredis.Redis(connection_pool=stream_pool)
    try:
        if ui_contract_id == UI_BALANCE_ACCOUNT_SELECTION:
            await _run_balance_result(redis_stream, chat_session_id, value)
        else:
            # 아직 워크플로우가 없는 계약: 브리지 확인용 플레이스홀더(다음 Slice 교체).
            await _emit(
                redis_stream,
                chat_session_id,
                AgentStreamEventType.DONE,
                "입력을 반영했어요.",
                delay=False,
            )
    finally:
        await redis_stream.aclose()


async def _run_balance_result(
    redis_stream: aioredis.Redis,
    chat_session_id: UUID,
    value: dict,
) -> None:
    """선택된 계좌의 잔액 결과(balance_result)를 발행한다(계약 4.2)."""
    if value.get("account_selection_outcome") != "selected":
        await _emit(
            redis_stream,
            chat_session_id,
            AgentStreamEventType.DONE,
            "잔액 조회를 취소했어요.",
            delay=False,
        )
        return

    account_ids = value.get("account_ids") or []
    payload = build_balance_result([str(account_id) for account_id in account_ids])
    await _emit(
        redis_stream,
        chat_session_id,
        AgentStreamEventType.STATUS,
        "잔액을 조회하고 있어요...",
        delay=False,
    )
    # 결과 UI 는 inline payload(ADR C3): component 이벤트 params 에 표시 데이터를 싣고
    # FE 가 fetch 없이 즉시 렌더한다(마스킹된 소용량 카드라 SSE 전송에 문제 없음).
    await _emit(
        redis_stream,
        chat_session_id,
        AgentStreamEventType.COMPONENT,
        "잔액을 불러왔어요.",
        metadata={"component": "balance_result", "params": payload},
    )
    await _emit(
        redis_stream,
        chat_session_id,
        AgentStreamEventType.DONE,
        "다른 도움이 필요하시면 말씀해 주세요.",
    )


async def run_after_approval(
    chat_session_id: UUID,
    approval_id: str,
    decision: str,
    args: dict | None,
    component: str | None = None,
    user_id: UUID | None = None,
) -> None:
    """confirm 카드 승인/거절 이후의 후속 턴을 발행한다.

    `component` 로 어떤 confirm(transfer/autotransfer)인지 구분한다(FE 가 전달).
    `user_id` 가 있으면 송금 승인 시 계정계 실이체를 시도한다(Phase 2).
    """
    redis_stream = aioredis.Redis(connection_pool=stream_pool)
    try:
        if component == "autotransfer":
            await _run_autotransfer_result(
                redis_stream, chat_session_id, approval_id, decision, args
            )
        else:
            await _run_transfer_result(
                redis_stream, chat_session_id, approval_id, decision, args, user_id
            )
    finally:
        await redis_stream.aclose()


async def _run_transfer_result(
    redis_stream: aioredis.Redis,
    chat_session_id: UUID,
    approval_id: str,
    decision: str,
    args: dict | None,
    user_id: UUID | None = None,
) -> None:
    if decision != "approve":
        await _emit(
            redis_stream,
            chat_session_id,
            AgentStreamEventType.DONE,
            "송금을 취소했어요.",
            delay=False,
        )
        return

    amount = (args or {}).get("amount", _SAMPLE_ARGS["amount"])
    name = (args or {}).get("name", _SAMPLE_ARGS["name"])
    await _emit(
        redis_stream,
        chat_session_id,
        AgentStreamEventType.STATUS,
        "송금을 처리하고 있어요...",
        delay=False,
    )
    await _emit(
        redis_stream,
        chat_session_id,
        AgentStreamEventType.TOOL_CALL,
        "송금을 실행하고 있어요...",
        metadata={"tool": "transfer", "approval_id": approval_id},
    )
    # 실이체는 수행하지 않는다(D5: env-고정 수취처 데모 로직 제거). 실제 송금은
    # Stage 7 의 실 Agent 연동이 agent-tools Prepare→승인→인증→Execute 로 수행한다.
    _ = user_id
    await _emit(
        redis_stream,
        chat_session_id,
        AgentStreamEventType.DONE,
        f"{name}님께 {int(amount):,}원을 보냈어요. ✓",
    )


async def _run_autotransfer_result(
    redis_stream: aioredis.Redis,
    chat_session_id: UUID,
    approval_id: str,
    decision: str,
    args: dict | None,
) -> None:
    if decision != "approve":
        await _emit(
            redis_stream,
            chat_session_id,
            AgentStreamEventType.DONE,
            "자동이체 등록을 취소했어요.",
            delay=False,
        )
        return

    amount = (args or {}).get("amount", _AUTOTRANSFER_SAMPLE_ARGS["amount"])
    day = (args or {}).get("day", _AUTOTRANSFER_SAMPLE_ARGS["day"])
    await _emit(
        redis_stream,
        chat_session_id,
        AgentStreamEventType.STATUS,
        "자동이체를 등록하고 있어요...",
        delay=False,
    )
    await _emit(
        redis_stream,
        chat_session_id,
        AgentStreamEventType.TOOL_CALL,
        "자동이체를 등록하고 있어요...",
        metadata={"tool": "autotransfer", "approval_id": approval_id},
    )
    await _emit(
        redis_stream,
        chat_session_id,
        AgentStreamEventType.DONE,
        f"{day} {int(amount):,}원 자동이체를 등록했어요. ✓",
    )
