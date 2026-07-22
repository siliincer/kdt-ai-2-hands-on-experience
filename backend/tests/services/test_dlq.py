"""DLQ enqueue 검증(services/dlq).

Redis 없이 `aioredis.Redis` 를 가짜로 대체해 XADD 필드·2차 실패 흡수를 확인한다.
"""

import json

import pytest

from backend.services import dlq


class _FakeRedis:
    def __init__(self) -> None:
        self.added: list[tuple[str, dict]] = []
        self.expired: list[tuple[str, int]] = []

    async def xadd(self, key, fields, maxlen, approximate):  # noqa: ANN001 - 테스트 더블
        self.added.append((key, fields))
        return "1-0"

    async def expire(self, key, ttl):  # noqa: ANN001
        self.expired.append((key, ttl))


@pytest.mark.asyncio
async def test_enqueue_writes_expected_fields(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(dlq.aioredis, "Redis", lambda *a, **k: fake)

    mid = await dlq.enqueue_dlq(
        kind="financial_transfer",
        operation="transfer",
        correlation_id="idem_1",
        args={"amount": 50000, "sender": "333-**-1234567"},
        attempts=3,
        error_type="FinancialServiceError",
    )

    assert mid == "1-0"
    key, fields = fake.added[0]
    assert key == dlq.DLQ_STREAM_KEY
    assert fields["kind"] == "financial_transfer"
    assert fields["operation"] == "transfer"
    assert fields["correlation_id"] == "idem_1"
    assert fields["attempts"] == "3"
    assert fields["error_type"] == "FinancialServiceError"
    assert "failed_at" in fields
    # args 는 JSON 문자열로 저장(원문 계좌번호 없이 마스킹본만).
    assert json.loads(fields["args"])["amount"] == 50000
    assert fake.expired[0] == (dlq.DLQ_STREAM_KEY, dlq.DLQ_TTL_SECONDS)


@pytest.mark.asyncio
async def test_enqueue_swallows_secondary_failure(monkeypatch):
    class _Boom:
        async def xadd(self, *a, **k):
            raise RuntimeError("redis down")

        async def expire(self, *a, **k):
            pass

    monkeypatch.setattr(dlq.aioredis, "Redis", lambda *a, **k: _Boom())

    # DLQ 적재(2차) 실패는 예외를 전파하지 않고 None 을 반환한다(원 요청 보호).
    mid = await dlq.enqueue_dlq(
        kind="agent_exec",
        operation="start_execution",
        correlation_id=None,
        args={},
        attempts=3,
        error_type="AgentServiceError",
    )
    assert mid is None
