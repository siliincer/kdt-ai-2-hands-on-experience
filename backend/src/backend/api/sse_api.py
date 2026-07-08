from collections.abc import AsyncIterable
from uuid import UUID

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.sse import EventSourceResponse, ServerSentEvent
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.postgres import get_db
from ..db.redis import get_redis_cache, get_redis_stream
from ..models.chat_session import ChatSession
from ..models.user import User
from ..schemas.response import CommonResponse
from ..schemas.sse import SseTicketContext, SseTicketResponse
from ..security.jwt import get_current_user
from ..services.sse_service import relay_agent_stream
from ..services.sse_ticket_service import consume_sse_ticket, grant_sse_ticket
from ..utils.build_response import success_response

sse_router = APIRouter(prefix="/sse", tags=["SSE"])


async def _resolve_chat_session(
    session: AsyncSession, user_id: UUID, chat_session_id: UUID | None
) -> UUID:
    """티켓 발급 시 chat_session_id 를 확정한다.

    - 주어지면: 해당 세션이 이 유저 소유인지 DB로 검증(소유권 검증은 여기서 끝냄).
    - 없으면: 유저용 chat_sessions row 를 새로 만들어 부트스트랩.
    """
    if chat_session_id is not None:
        result = await session.execute(
            select(ChatSession).where(
                ChatSession.id == chat_session_id,
                ChatSession.user_id == user_id,
            )
        )
        if result.scalar_one_or_none() is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="해당 대화 세션을 찾을 수 없습니다.",
            )
        return chat_session_id

    new_session = ChatSession(user_id=user_id)
    session.add(new_session)
    await session.commit()
    await session.refresh(new_session)
    return new_session.id


async def get_sse_ticket_context(
    sse_session_id: UUID,
    redis: aioredis.Redis = Depends(get_redis_cache),
) -> SseTicketContext:
    """EventSource 연결 전 티켓을 검증한다.
    SSE 스트림 시작 이전에 401을 반환하기 위해 dependency로 분리."""

    context = await consume_sse_ticket(redis, sse_session_id)
    if context is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않거나 만료된 SSE 티켓입니다.",
        )
    return context


@sse_router.get("/ticket", response_model=CommonResponse[SseTicketResponse])
async def issue_sse_ticket(
    chat_session_id: UUID | None = None,
    current_user: User = Depends(get_current_user),
    redis: aioredis.Redis = Depends(get_redis_cache),
    session: AsyncSession = Depends(get_db),
):
    """EventSource는 Authorization 헤더를 보낼 수 없으므로,
    Bearer 인증 후 SSE 티켓을 발급한다.

    chat_session_id 를 넘기면 소유권 검증 후 바인딩하고,
    생략하면 새 대화 세션을 만들어 바인딩한다.
    """
    resolved_chat_session_id = await _resolve_chat_session(
        session, current_user.id, chat_session_id
    )
    ticket = await grant_sse_ticket(redis, current_user.id, resolved_chat_session_id)
    return success_response(
        message="SSE 연결 티켓이 발급되었습니다.",
        data=ticket,
    )


@sse_router.get("/connect", response_class=EventSourceResponse)
async def connect_sse(
    request: Request,
    context: SseTicketContext = Depends(get_sse_ticket_context),
    redis_stream: aioredis.Redis = Depends(get_redis_stream),
) -> AsyncIterable[ServerSentEvent]:
    """발급받은 sse_session_id로 SSE 스트림에 연결한다.

    티켓에 바인딩된 chat_session_id 의 Redis Stream(agent:stream:{id})을
    XREAD BLOCK 으로 중계한다. Last-Event-ID 헤더가 있으면 그 지점부터 재개.
    """
    last_event_id = request.headers.get("Last-Event-ID")
    async for event in relay_agent_stream(
        redis_stream, context.chat_session_id, last_event_id
    ):
        yield event
