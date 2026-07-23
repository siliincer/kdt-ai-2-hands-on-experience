"""외부 호출 재시도 정책(Tenacity) — 실패 복구 인프라

BE→Agent(agent_client)·BE→계정계 상태변경(financial_client.transfer) 같은 외부 HTTP 호출을
**인라인 3회 재시도**로 감싼다(짧은 지수 백오프+jitter). 재시도 여부는 예외의 `retryable`
속성으로 판정한다: 전송 오류·타임아웃·5xx 는 True, 4xx(계약 위반·소유권 거부 등)는 False 로
즉시 전파한다(무한 재시도·상태변경 중복 방지). 재시도/실패 상태는 로거로 즉시 남긴다(2순위 연동).

DLQ 적재(최종 실패 시 Redis Stream 에 페이로드 저장)는 `services/dlq.py` 가 담당하며, 이
모듈은 재시도 프리미티브만 제공한다(호출부 seam 에서 둘을 결합).
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

from tenacity import (
    AsyncRetrying,
    before_sleep_log,
    retry_if_exception,
    stop_after_attempt,
    wait_random_exponential,
)

logger = logging.getLogger(__name__)

# 최초 1회 + 재시도 2회 = 총 3회 시도(사용자 확정: 인라인 3회).
MAX_RETRY_ATTEMPTS = 3

T = TypeVar("T")


def is_retryable(exc: BaseException) -> bool:
    """예외의 `retryable` 속성으로 재시도 여부를 판정한다(없으면 재시도 안 함)."""
    return bool(getattr(exc, "retryable", False))


def build_external_retrying() -> AsyncRetrying:
    """외부 호출용 공통 AsyncRetrying 을 만든다.

    - stop: 총 3회 시도.
    - wait: 지수 백오프 + jitter(상한 2s) — 짧게 잡아 요청 인라인 재시도가 과도하지 않게.
    - retry: `retryable` 인 예외만.
    - before_sleep: 재시도 직전 WARNING 로그(파일/콘솔로 남김).
    - reraise: 최종 실패 시 원본 예외를 그대로 올린다(seam 이 DLQ 적재 후 전파).
    """
    return AsyncRetrying(
        stop=stop_after_attempt(MAX_RETRY_ATTEMPTS),
        wait=wait_random_exponential(multiplier=0.2, max=2),
        retry=retry_if_exception(is_retryable),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    # AsyncRetrying 객체는 비동기 이터레이터입니다.
    # stop 조건(최대 3회)에 도달할 때까지 루프를 계속 돌립니다.


async def call_with_retry(
    func: Callable[..., Awaitable[T]],
    *args: object,
    **kwargs: object,
) -> T:
    """`func(*args, **kwargs)` 를 공통 재시도 정책으로 실행한다.

    재시도 가능(`retryable`) 예외면 최대 3회까지 재시도하고, 소진되면 원본 예외를 전파한다.
    비재시도 예외는 즉시 전파한다.
    """
    async for attempt in build_external_retrying():
        with attempt:
            return await func(*args, **kwargs)
    # AsyncRetrying(reraise=True) 는 위 루프에서 성공 반환 또는 예외 전파로 끝난다.
    raise AssertionError("unreachable")  # pragma: no cover
