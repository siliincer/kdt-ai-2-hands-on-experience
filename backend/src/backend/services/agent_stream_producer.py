"""agent:stream:{chat_session_id} 로의 이벤트 발행(XADD) 헬퍼.

웹훅 엔드포인트(POST /webhooks/agent)와 로컬 목 프로듀서가 공유한다.
스트림 자체가 fast-write 로그 역할을 하므로, connect가 0-0부터 리플레이하면
재연결 시에도 유실 없이 이전 단계를 복원할 수 있다(별도 스냅샷 스토어 불필요).
"""

import json
from typing import Any, cast
from uuid import UUID

import redis.asyncio as aioredis

from ..core.load_environment_var import settings
from ..schemas.sse import AgentStreamEvent, AgentStreamEventType

AGENT_STREAM_KEY_PREFIX = "agent:stream:"


def agent_stream_key(chat_session_id: UUID) -> str:
    return f"{AGENT_STREAM_KEY_PREFIX}{chat_session_id}"


def _to_fields(event: AgentStreamEvent) -> dict[str, str]:
    """AgentStreamEvent → XADD field-value 맵. Redis Stream 값은 문자열만 허용."""
    fields = {
        "event_type": event.event_type.value,
        "content": event.content,
    }
    if event.approval_id is not None:
        fields["approval_id"] = event.approval_id
    if event.metadata is not None:
        fields["metadata"] = json.dumps(event.metadata)
    return fields


def fields_to_event(fields: dict[str, str]) -> AgentStreamEvent:
    """XREAD로 읽은 field 맵 → AgentStreamEvent 복원(relay에서 사용)."""
    metadata_raw = fields.get("metadata")
    return AgentStreamEvent(
        event_type=AgentStreamEventType(fields["event_type"]),
        content=fields.get("content", ""),
        approval_id=fields.get("approval_id"),
        metadata=json.loads(metadata_raw) if metadata_raw else None,
    )


async def publish_agent_event(
    redis_stream: aioredis.Redis,
    chat_session_id: UUID,
    event: AgentStreamEvent,
) -> str:
    """이벤트를 스트림에 XADD 하고 메시지 ID를 반환한다.

    MAXLEN ~ 로 근사 트리밍, 매 발행 시 TTL을 갱신한다.
    """
    key = agent_stream_key(chat_session_id)
    message_id = await redis_stream.xadd(
        key,
        fields=cast(dict[Any, Any], _to_fields(event)),
        maxlen=settings.AGENT_STREAM_MAXLEN,
        approximate=True,
    )
    await redis_stream.expire(key, settings.AGENT_STREAM_TTL_SECONDS)
    return str(message_id)
