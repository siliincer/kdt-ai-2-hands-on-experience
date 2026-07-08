"""mock 에이전트 드라이버.

실제 Agent(LangGraph)가 스텁이라, /chat·/approve 가 이 드라이버를 백그라운드로 돌려
agent:stream:{chat_session_id} 에 status/tool_call/need_approval/done 을 XADD 한다.
→ FE(assistant-ui)의 스트리밍·confirm(HITL) 루프를 에이전트 없이 검증할 수 있다.

실제 Agent 연동 시 이 파일을 걷어내고, Agent 가 웹훅(POST /webhooks/agent) 또는
직접 XADD 로 동일 이벤트를 보내면 된다.
"""

import asyncio
import re
from uuid import UUID, uuid4

import redis.asyncio as aioredis

from ..db.redis import stream_pool
from ..schemas.sse import AgentStreamEvent, AgentStreamEventType
from .agent_stream_producer import publish_agent_event

_STEP_DELAY_SECONDS = 0.5

# 송금 의도로 볼 키워드
_TRANSFER_KEYWORDS = ("송금", "보내", "이체", "transfer")

# 파싱 실패 시 사용할 샘플(스크린샷 기준)
_SAMPLE_ARGS = {
    "name": "김철수",
    "bank": "하나은행",
    "account": "110-123-456789",
    "amount": "30000",
    "time": "지금 바로",
}


def _is_transfer_intent(message: str) -> bool:
    return any(keyword in message for keyword in _TRANSFER_KEYWORDS)


def _extract_transfer_args(message: str) -> dict[str, str]:
    """메시지에서 송금 파라미터를 가볍게 파싱(목). 실패 필드는 샘플로 채운다."""
    args = dict(_SAMPLE_ARGS)

    # 금액: "30,000원" / "3만원" 대략 처리 → 숫자만
    amount_match = re.search(r"([\d,]+)\s*원", message)
    if amount_match:
        args["amount"] = amount_match.group(1).replace(",", "")

    # 계좌번호: 숫자/하이픈 6자리 이상
    account_match = re.search(r"\d[\d-]{5,}", message)
    if account_match:
        args["account"] = account_match.group(0)

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


async def run_initial_turn(chat_session_id: UUID, message: str) -> None:
    """사용자 메시지에 대한 첫 턴을 스트림에 발행한다.

    송금 의도면 need_approval(confirm 카드)까지 발행하고 멈춘다(승인 대기).
    그 외에는 간단한 답변 후 done.
    """
    redis_stream = aioredis.Redis(connection_pool=stream_pool)
    try:
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


async def run_after_approval(
    chat_session_id: UUID,
    approval_id: str,
    decision: str,
    args: dict | None,
) -> None:
    """confirm 카드 승인/거절 이후의 후속 턴을 발행한다."""
    redis_stream = aioredis.Redis(connection_pool=stream_pool)
    try:
        if decision == "approve":
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
            await _emit(
                redis_stream,
                chat_session_id,
                AgentStreamEventType.DONE,
                f"{name}님께 {int(amount):,}원을 보냈어요. ✓",
            )
        else:
            await _emit(
                redis_stream,
                chat_session_id,
                AgentStreamEventType.DONE,
                "송금을 취소했어요.",
                delay=False,
            )
    finally:
        await redis_stream.aclose()
