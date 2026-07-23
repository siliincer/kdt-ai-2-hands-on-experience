"""DLQ 컨슈머 스켈레톤 검증(services/dlq_consumer).

Redis 없이 `aioredis.Redis` 를 가짜로 대체해 스트림 항목을 읽어 처리 건수를 돌려주는지 확인한다.
(현재 구현은 로깅만 하므로 건수·읽기 인자만 검증한다.)
"""

import pytest

from backend.services import dlq_consumer


class _FakeRedis:
    def __init__(self, entries) -> None:
        self._entries = entries
        self.xrange_args: list[tuple] = []

    async def xrange(self, key, count=None):  # noqa: ANN001 - 테스트 더블
        self.xrange_args.append((key, count))
        return self._entries


@pytest.mark.asyncio
async def test_consume_reads_and_returns_count(monkeypatch):
    entries = [
        ("1-0", {"kind": "financial_transfer", "operation": "transfer"}),
        ("2-0", {"kind": "agent_exec", "operation": "start_execution"}),
    ]
    fake = _FakeRedis(entries)
    monkeypatch.setattr(dlq_consumer.aioredis, "Redis", lambda *a, **k: fake)

    processed = await dlq_consumer.consume_dlq(count=50)

    assert processed == 2
    # DLQ 스트림 키를 count 한도로 읽는다.
    assert fake.xrange_args[0][0] == dlq_consumer.DLQ_STREAM_KEY
    assert fake.xrange_args[0][1] == 50


@pytest.mark.asyncio
async def test_consume_empty_stream_returns_zero(monkeypatch):
    fake = _FakeRedis([])
    monkeypatch.setattr(dlq_consumer.aioredis, "Redis", lambda *a, **k: fake)

    assert await dlq_consumer.consume_dlq() == 0
