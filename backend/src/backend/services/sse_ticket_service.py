from typing import cast
from uuid import UUID, uuid4

import redis.asyncio as aioredis

from ..core.load_environment_var import settings
from ..schemas.sse import SseTicketResponse

SSE_TICKET_KEY_PREFIX = "sse:ticket:"
USER_CACHE_KEY_PREFIX = "user:cache:"


def _ticket_key(sse_session_id: UUID) -> str:
    return f"{SSE_TICKET_KEY_PREFIX}{sse_session_id}"


def _user_cache_key(user_id: UUID) -> str:
    return f"{USER_CACHE_KEY_PREFIX}{user_id}"


async def grant_sse_ticket(redis: aioredis.Redis, user_id: UUID) -> SseTicketResponse:
    """Bearer JWT로 인증된 사용자에게 SSE 연결용 일회성 티켓을 발급한다."""
    sse_session_id = uuid4()
    ttl = settings.SSE_TICKET_TTL_SECONDS
    ticket_key = _ticket_key(sse_session_id)

    await redis.set(ticket_key, str(user_id), ex=ttl)
    await redis.hset(
        _user_cache_key(user_id),
        mapping={"sse_session_id": str(sse_session_id)},
    )
    await redis.expire(_user_cache_key(user_id), ttl)

    return SseTicketResponse(sse_session_id=sse_session_id, expires_in=ttl)


async def consume_sse_ticket(
    redis: aioredis.Redis, sse_session_id: UUID
) -> UUID | None:
    ticket_key = _ticket_key(sse_session_id)
    user_id_raw = await redis.getdel(ticket_key)

    if user_id_raw is None:
        return None

    # user_id_raw를 강제로 str 타입으로 캐스팅하여 Pyright 통과
    return UUID(cast(str, user_id_raw))
