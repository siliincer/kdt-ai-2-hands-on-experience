"""외부 호출 seam 재시도+DLQ 통합 검증(agent_client·financial_client).

httpx.MockTransport 로 5xx/4xx 를 흉내내 재시도 횟수·DLQ 적재 여부를 확인한다. 대기(wait)는
wait_none 으로 대체하고, DLQ enqueue 는 캡처로 대체한다(Redis 불필요).
"""

import httpx
import pytest
from tenacity import (
    AsyncRetrying,
    retry_if_exception,
    stop_after_attempt,
    wait_none,
)

from backend.core import resilience
from backend.core.resilience import MAX_RETRY_ATTEMPTS, is_retryable
from backend.services import agent_client as agent_mod
from backend.services.agent_client import AgentServiceClient, AgentServiceError
from backend.services.financial import financial_client as fin_mod
from backend.services.financial.financial_client import (
    FinancialServiceClient,
    FinancialServiceError,
)


@pytest.fixture(autouse=True)
def _no_wait(monkeypatch):
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


def _capture_dlq(monkeypatch, module):
    calls: list[dict] = []

    async def _fake(**kwargs):
        calls.append(kwargs)
        return "dlq-1"

    monkeypatch.setattr(module, "enqueue_dlq", _fake)
    return calls


def _counting_transport(status: int) -> tuple[httpx.MockTransport, dict]:
    counter = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        counter["n"] += 1
        return httpx.Response(status, json={"error": "x"})

    return httpx.MockTransport(handler), counter


# ── 계정계 송금(상태변경) ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_transfer_5xx_retries_and_enqueues_dlq(monkeypatch):
    dlq_calls = _capture_dlq(monkeypatch, fin_mod)
    transport, counter = _counting_transport(500)
    client = FinancialServiceClient("http://f.test", "k", transport=transport)

    with pytest.raises(FinancialServiceError):
        await client.transfer("333-1", "KDT은행", "444-2", 50000, "idem_1")

    assert counter["n"] == MAX_RETRY_ATTEMPTS  # 3회 재시도
    assert len(dlq_calls) == 1
    assert dlq_calls[0]["kind"] == "financial_transfer"
    assert dlq_calls[0]["correlation_id"] == "idem_1"
    # DLQ 에는 마스킹 계좌만(원문 없음).
    assert dlq_calls[0]["args"]["sender"] != "333-1"
    await client.aclose()


@pytest.mark.asyncio
async def test_transfer_4xx_no_retry_no_dlq(monkeypatch):
    dlq_calls = _capture_dlq(monkeypatch, fin_mod)
    transport, counter = _counting_transport(400)
    client = FinancialServiceClient("http://f.test", "k", transport=transport)

    with pytest.raises(FinancialServiceError):
        await client.transfer("333-1", "KDT은행", "444-2", 50000, "idem_2")

    assert counter["n"] == 1  # 4xx 는 즉시 전파
    assert dlq_calls == []
    await client.aclose()


# ── Agent 실행/재개 ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_agent_start_5xx_retries_and_enqueues_dlq(monkeypatch):
    dlq_calls = _capture_dlq(monkeypatch, agent_mod)
    transport, counter = _counting_transport(503)
    client = AgentServiceClient("http://a.test", "tok", transport=transport)

    with pytest.raises(AgentServiceError):
        await client.start_execution(
            request_id="req_1",
            chat_session_id="cs_1",
            execution_context_id="ec_1",
            message="안녕",
        )

    assert counter["n"] == MAX_RETRY_ATTEMPTS
    assert len(dlq_calls) == 1
    assert dlq_calls[0]["kind"] == "agent_exec"
    assert dlq_calls[0]["correlation_id"] == "req_1"
    await client.aclose()


@pytest.mark.asyncio
async def test_agent_start_4xx_no_retry_no_dlq(monkeypatch):
    dlq_calls = _capture_dlq(monkeypatch, agent_mod)
    transport, counter = _counting_transport(400)
    client = AgentServiceClient("http://a.test", "tok", transport=transport)

    with pytest.raises(AgentServiceError):
        await client.start_execution(
            request_id="req_2",
            chat_session_id="cs_1",
            execution_context_id="ec_1",
            message="안녕",
        )

    assert counter["n"] == 1
    assert dlq_calls == []
    await client.aclose()
