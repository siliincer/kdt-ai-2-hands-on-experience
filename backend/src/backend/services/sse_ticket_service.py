import json
from typing import cast
from uuid import UUID, uuid4

import redis.asyncio as aioredis

from ..core.load_environment_var import settings
from ..schemas.sse import SseTicketContext, SseTicketResponse

SSE_TICKET_KEY_PREFIX = "sse:ticket:"
USER_CACHE_KEY_PREFIX = "user:cache:"


def _ticket_key(sse_session_id: UUID) -> str:
    return f"{SSE_TICKET_KEY_PREFIX}{sse_session_id}"


def _user_cache_key(user_id: UUID) -> str:
    return f"{USER_CACHE_KEY_PREFIX}{user_id}"


async def grant_sse_ticket(
    redis: aioredis.Redis, user_id: UUID, chat_session_id: UUID
) -> SseTicketResponse:
    """Bearer JWT로 인증된 사용자에게 SSE 연결용 일회성 티켓을 발급한다.

    티켓에 chat_session_id를 함께 바인딩한다.
    connect 핸들러는 SSE 스트림 안에서 DB 검증을 하지 않으므로,
    소유권 검증(이 세션이 이 유저 것인가)은 티켓 발급 시점에 끝낸다.
    """
    sse_session_id = uuid4()
    ttl = settings.SSE_TICKET_TTL_SECONDS
    ticket_key = _ticket_key(sse_session_id)

    # 값을 JSON으로 저장 → connect 시 GETDEL 한 번으로 원자적 단일 소비 유지.
    payload = json.dumps(
        {"user_id": str(user_id), "chat_session_id": str(chat_session_id)}
    )
    await redis.set(ticket_key, payload, ex=ttl)
    await redis.hset(
        _user_cache_key(user_id),
        mapping={
            "sse_session_id": str(sse_session_id),
            "chat_session_id": str(chat_session_id),
        },
    )
    await redis.expire(_user_cache_key(user_id), ttl)

    return SseTicketResponse(
        sse_session_id=sse_session_id,
        chat_session_id=chat_session_id,
        expires_in=ttl,
    )


async def consume_sse_ticket(
    redis: aioredis.Redis, sse_session_id: UUID
) -> SseTicketContext | None:
    """티켓을 GETDEL로 원자적으로 소비하고, 바인딩된 컨텍스트를 반환한다."""
    ticket_key = _ticket_key(sse_session_id)
    raw = await redis.getdel(ticket_key)

    if raw is None:
        return None

    data = json.loads(cast(str, raw))
    return SseTicketContext(
        user_id=UUID(data["user_id"]),
        chat_session_id=UUID(data["chat_session_id"]),
    )
