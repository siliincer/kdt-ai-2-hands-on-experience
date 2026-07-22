"""외부 호출 재시도 정책 검증(core/resilience).

재시도 판정(`retryable`)·재시도 횟수·비재시도 즉시전파·성공 반환을 확인한다. 대기(wait)는
테스트 속도를 위해 wait_none 으로 대체한다.
"""

import pytest
from tenacity import (
    AsyncRetrying,
    retry_if_exception,
    stop_after_attempt,
    wait_none,
)

from backend.core import resilience
from backend.core.resilience import MAX_RETRY_ATTEMPTS, call_with_retry, is_retryable


class _BoomError(Exception):
    def __init__(self, retryable: bool) -> None:
        super().__init__("boom")
        self.retryable = retryable


@pytest.fixture(autouse=True)
def _no_wait(monkeypatch):
    """재시도 대기를 제거해 테스트를 빠르게 한다(정책 로직만 검증)."""
    monkeypatch.setattr(
        resilience,
        "build_external_retrying",
        lambda: AsyncRetrying(
            stop=stop_after_attempt(MAX_RETRY_ATTEMPTS),
            wait=wait_none(),
            retry=retry_if_exception(is_retryable),
            reraise=True,
        ),
    )


def test_is_retryable():
    assert is_retryable(_BoomError(retryable=True)) is True
    assert is_retryable(_BoomError(retryable=False)) is False
    assert is_retryable(ValueError("x")) is False  # 속성 없음 → 재시도 안 함


@pytest.mark.asyncio
async def test_retryable_retries_up_to_max_then_reraises():
    calls = {"n": 0}

    async def _fn():
        calls["n"] += 1
        raise _BoomError(retryable=True)

    with pytest.raises(_BoomError):
        await call_with_retry(_fn)
    assert calls["n"] == MAX_RETRY_ATTEMPTS  # 최초 1 + 재시도 2 = 3


@pytest.mark.asyncio
async def test_non_retryable_raises_immediately():
    calls = {"n": 0}

    async def _fn():
        calls["n"] += 1
        raise _BoomError(retryable=False)

    with pytest.raises(_BoomError):
        await call_with_retry(_fn)
    assert calls["n"] == 1  # 재시도 없음


@pytest.mark.asyncio
async def test_success_returns_value_without_retry():
    calls = {"n": 0}

    async def _fn():
        calls["n"] += 1
        return "ok"

    assert await call_with_retry(_fn) == "ok"
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_recovers_after_transient_failures():
    calls = {"n": 0}

    async def _fn():
        calls["n"] += 1
        if calls["n"] < MAX_RETRY_ATTEMPTS:
            raise _BoomError(retryable=True)
        return "recovered"

    assert await call_with_retry(_fn) == "recovered"
    assert calls["n"] == MAX_RETRY_ATTEMPTS
