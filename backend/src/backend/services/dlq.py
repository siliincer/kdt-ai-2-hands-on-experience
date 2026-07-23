"""Dead Letter Queue(DLQ) — 외부 호출 최종 실패 페이로드를 Redis Stream 에 적재.

dramatiq 도입 없이, Tenacity 3회 재시도가 모두 실패하면 해당 태스크의
페이로드를 **이미 있는 Redis Stream**(`stream_pool`)에 쌓아 둔다. 컨슈머(재처리 워커)는 차후
과제이고, 지금은 유실 없이 enqueue 까지만 한다. 실패한 요청을 나중에 안전하게 재처리할 수
있도록 상관관계 id(request_id/idempotency_key)를 함께 남긴다(멱등성으로 safe replay).

주의: **PII/원문 계좌번호·비밀번호는 절대 넣지 않는다**(마스킹본만, B6 규칙). 계층상 DB 가 아닌
Redis 인프라라 repository 가 아니라 이 전용 모듈에 둔다.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, cast

import redis.asyncio as aioredis

from ..db.redis import stream_pool

logger = logging.getLogger(__name__)

DLQ_STREAM_KEY = "agent:dlq"
# 폭주 방지 근사 트리밍(오래된 항목은 컨슈머 도입 전이라도 상한 유지).
DLQ_MAXLEN = 5000
# DLQ 는 재처리 여지를 위해 1일 보존한다(1일).
DLQ_TTL_SECONDS = 24 * 3600


async def enqueue_dlq(
    *,
    kind: str,
    operation: str,
    correlation_id: str | None,
    args: dict[str, Any],
    attempts: int,
    error_type: str,
) -> str | None:
    """실패 태스크를 DLQ 스트림에 적재한다(2차 실패는 삼키고 로그만 남긴다).

    - kind: 태스크 분류(예: "agent_exec", "financial_transfer"). 컨슈머 라우팅 키.
    - operation: 세부 동작(예: "start_execution", "transfer").
    - correlation_id: request_id 또는 idempotency_key(재처리 멱등 기준).
    - args: 재처리에 필요한 최소 인자(마스킹·비-PII 만). JSON 직렬화해 저장.
    - attempts: 실제 시도 횟수.
    - error_type: 최종 예외 타입명(내부 주소·원문 유출 방지 위해 타입명만).
    반환: XADD message id, 적재 실패 시 None.
    """
    fields = {
        "kind": kind,
        "operation": operation,
        "correlation_id": correlation_id or "-",
        "args": json.dumps(args, ensure_ascii=False, default=str),
        "attempts": str(attempts),
        "error_type": error_type,
        "failed_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        redis = aioredis.Redis(connection_pool=stream_pool)
        message_id = await redis.xadd(
            DLQ_STREAM_KEY,
            # redis 스텁의 fields 타입 불변성(invariance) 회피(문자열 맵만 저장).
            fields=cast(dict[Any, Any], fields),
            maxlen=DLQ_MAXLEN,
            approximate=True,
        )
        await redis.expire(DLQ_STREAM_KEY, DLQ_TTL_SECONDS)
        logger.error(
            "dlq enqueued kind=%s operation=%s correlation_id=%s attempts=%s error=%s",
            kind,
            operation,
            correlation_id,
            attempts,
            error_type,
        )
        return str(message_id)
    except Exception:
        # DLQ 적재(2차) 실패가 원 요청을 다시 깨지 않도록 삼키고 로그만 남긴다.
        logger.exception(
            "dlq enqueue failed kind=%s operation=%s correlation_id=%s",
            kind,
            operation,
            correlation_id,
        )
        return None
