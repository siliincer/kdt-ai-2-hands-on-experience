"""DLQ 컨슈머(스켈레톤) — `agent:dlq` 스트림의 실패 태스크를 읽어 처리한다.

BE_Coding §TODO 1순위의 마무리: 실패 요청을 Redis Stream(DLQ)에 쌓아 둔 것을 뒤늦게 처리하는
진입점이다. **현재는 유실 감시용 로깅만** 하고, 실제 재처리/알림은 확장 지점으로 남긴다.

TODO(BE): 디스코드 알림이나 재시도 워커 로직 구현으로 확장 가능
  (예: consumer group(XREADGROUP)+XACK 로 at-least-once 소비, correlation_id/idempotency_key 로
   원 태스크 안전 재처리, 임계치 초과 시 Discord 웹훅 알림 등).
"""

from __future__ import annotations

import logging
from typing import cast

import redis.asyncio as aioredis

from ..db.redis import stream_pool
from .dlq import DLQ_STREAM_KEY

# XRANGE 결과 한 항목: (entry_id, {field: value}). stream_pool 은 decode_responses=True.
_StreamEntry = tuple[str, dict[str, str]]

logger = logging.getLogger(__name__)


async def consume_dlq(*, count: int = 100) -> int:
    """DLQ 스트림의 실패 태스크를 최대 `count` 건 읽어 로깅한다. 처리 건수를 반환한다.

    현재 구현은 **로깅만** 한다(재처리·ack·알림은 위 TODO 로 확장). stream_pool 은
    decode_responses=True 라 field 는 문자열로 온다.
    """
    redis = aioredis.Redis(connection_pool=stream_pool)
    entries = cast(
        list[_StreamEntry],
        await redis.xrange(DLQ_STREAM_KEY, count=count) or [],
    )
    for entry_id, fields in entries:
        logger.warning(
            "dlq entry id=%s kind=%s operation=%s correlation_id=%s error=%s failed_at=%s",
            entry_id,
            fields.get("kind"),
            fields.get("operation"),
            fields.get("correlation_id"),
            fields.get("error_type"),
            fields.get("failed_at"),
        )
    logger.info("dlq consume scanned=%s entries", len(entries))
    return len(entries)
