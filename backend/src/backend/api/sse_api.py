from collections.abc import AsyncIterable
from uuid import UUID

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.sse import EventSourceResponse, ServerSentEvent
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import limiter
from ..core.load_environment_var import settings
from ..db.postgres import get_db
from ..db.redis import get_redis_cache, get_redis_stream
from ..models.user import User
from ..schemas.response import CommonResponse
from ..schemas.sse import SseTicketContext, SseTicketResponse
from ..security.jwt import get_current_user
from ..services.chat_session_service import resolve_chat_session
from ..services.sse_service import relay_agent_stream
from ..services.sse_ticket_service import consume_sse_ticket, grant_sse_ticket
from ..utils.build_response import success_response

sse_router = APIRouter(prefix="/sse", tags=["SSE"])


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
@limiter.limit(settings.SSE_TICKET_RATE_LIMIT)
async def issue_sse_ticket(
    request: Request,
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
    resolved_chat_session_id = await resolve_chat_session(
        session, current_user.id, chat_session_id
    )
    ticket = await grant_sse_ticket(redis, current_user.id, resolved_chat_session_id)
    return success_response(
        message="SSE 연결 티켓이 발급되었습니다.",
        data=ticket,
    )


@sse_router.get("/connect", response_class=EventSourceResponse)
@limiter.limit(settings.SSE_CONNECT_RATE_LIMIT)
async def connect_sse(
    request: Request,
    last_event_id: str | None = None,
    context: SseTicketContext = Depends(get_sse_ticket_context),
    redis_stream: aioredis.Redis = Depends(get_redis_stream),
) -> AsyncIterable[ServerSentEvent]:
    """발급받은 sse_session_id로 SSE 스트림에 연결한다.

    티켓에 바인딩된 chat_session_id 의 Redis Stream(agent:stream:{id})을
    XREAD BLOCK 으로 중계한다. 재개 지점은 다음 우선순위로 정한다:
    Last-Event-ID 헤더 → last_event_id 쿼리 파라미터 → 없으면 처음(0-0)부터.

    쿼리 폴백을 두는 이유: 네이티브 EventSource는 커스텀 헤더를 못 보내므로,
    FE가 티켓을 재발급받아 수동 재연결할 때 헤더 대신 쿼리로 재개점을 전달한다.
    """
    resume_from = request.headers.get("Last-Event-ID") or last_event_id
    async for event in relay_agent_stream(
        redis_stream, context.chat_session_id, resume_from
    ):
        yield event
