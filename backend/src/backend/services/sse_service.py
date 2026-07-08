"""Phase 2: agent:stream:{chat_session_id} 를 XREAD BLOCK 으로 중계하는 SSE 서비스."""

import asyncio
from collections.abc import AsyncIterable
from typing import Any, cast
from uuid import UUID

import redis.asyncio as aioredis
from fastapi.sse import ServerSentEvent

from ..core.load_environment_var import settings
from ..schemas.sse import AgentStreamEventType
from .agent_stream_producer import agent_stream_key, fields_to_event

# 재연결 시 Last-Event-ID 가 없으면 버퍼에 남은 모든 이벤트를 리플레이한다.
# ("0-0" = 스트림 처음부터) → 재연결/새로고침에도 이전 단계 유실 없이 복원.
REPLAY_FROM_START = "0-0"


async def relay_agent_stream(
    redis_stream: aioredis.Redis,
    chat_session_id: UUID,
    last_event_id: str | None = None,
) -> AsyncIterable[ServerSentEvent]:
    """Redis Stream을 지속 구독하며 SSE 이벤트로 중계한다.

    - last_event_id(재연결): 그 ID 다음 이벤트부터 이어서 전송.
    - last_event_id 없음(최초 연결): 0-0 부터 버퍼된 이벤트를 모두 리플레이 후 tail.
    - DONE 이벤트를 만나면 [DONE] sentinel 을 보내고 스트림을 종료한다.
    - 클라이언트 연결 종료(CancelledError) 시 조용히 정리한다.
    """
    key = agent_stream_key(chat_session_id)
    last_id = last_event_id or REPLAY_FROM_START

    yield ServerSentEvent(comment=f"relay chat_session_id={chat_session_id}")

    try:
        while True:
            response = await redis_stream.xread(
                {key: last_id},
                block=settings.AGENT_STREAM_BLOCK_MS,
                count=10,
            )

            if not response:
                # BLOCK 타임아웃 → keep-alive comment(프록시 idle 타임아웃 방지)
                yield ServerSentEvent(comment="ping")
                continue

            for _stream_name, messages in cast(list[Any], response):
                for message_id, fields in messages:
                    last_id = message_id
                    event = fields_to_event(fields)

                    yield ServerSentEvent(
                        data=event,
                        event=event.event_type.value,
                        id=message_id,
                    )

                    if event.event_type == AgentStreamEventType.DONE:
                        yield ServerSentEvent(raw_data="[DONE]", event="done")
                        return
    except asyncio.CancelledError:
        # 유저가 브라우저를 닫거나 연결을 끊었을 때
        return
