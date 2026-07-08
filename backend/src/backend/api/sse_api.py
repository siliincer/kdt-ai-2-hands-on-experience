from collections.abc import AsyncIterable
from uuid import UUID

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.sse import EventSourceResponse, ServerSentEvent

from ..db.redis import get_redis_cache
from ..models.user import User
from ..schemas.response import CommonResponse
from ..schemas.sse import SseTicketResponse
from ..security.jwt import get_current_user
from ..services.sse_service import mock_agent_stream
from ..services.sse_ticket_service import consume_sse_ticket, grant_sse_ticket
from ..utils.build_response import success_response

sse_router = APIRouter(prefix="/sse", tags=["SSE"])


async def get_sse_user_from_ticket(
    sse_session_id: UUID,
    redis: aioredis.Redis = Depends(get_redis_cache),
) -> UUID:
    """EventSource 연결 전 티켓을 검증한다.
    SSE 스트림 시작 이전에 401을 반환하기 위해 dependency로 분리."""

    user_id = await consume_sse_ticket(redis, sse_session_id)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않거나 만료된 SSE 티켓입니다.",
        )
    return user_id


@sse_router.get("/ticket", response_model=CommonResponse[SseTicketResponse])
async def issue_sse_ticket(
    current_user: User = Depends(get_current_user),
    redis: aioredis.Redis = Depends(get_redis_cache),
):
    """EventSource는 Authorization 헤더를 보낼 수 없으므로,
    Bearer 인증 후 SSE 티켓을 발급한다."""

    ticket = await grant_sse_ticket(redis, current_user.id)
    return success_response(
        message="SSE 연결 티켓이 발급되었습니다.",
        data=ticket,
    )


@sse_router.get("/connect", response_class=EventSourceResponse)
async def connect_sse(
    user_id: UUID = Depends(get_sse_user_from_ticket),
) -> AsyncIterable[ServerSentEvent]:
    """
    발급받은 sse_session_id로 SSE 스트림에 연결한다.
    (Phase 1: Mock 이벤트)
    """
    async for event in mock_agent_stream(user_id):
        yield event
