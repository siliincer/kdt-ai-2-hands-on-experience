"""mock-financial-service 클라이언트 + 장애 격리 계약 테스트.

httpx.MockTransport 로 계정계 응답을 흉내내 네트워크 없이 검증한다.
"""

import httpx
import pytest

from backend.services.financial.financial_client import (
    FinancialServiceClient,
    FinancialServiceError,
    financial_service_error_handler,
)
from backend.services.ui_service import _ledger_to_item


def _client(handler) -> FinancialServiceClient:
    return FinancialServiceClient(
        base_url="http://financial.test",
        analytics_key="analytics-demo-key",
        transport=httpx.MockTransport(handler),
    )


@pytest.mark.asyncio
async def test_get_balance_returns_payload_and_sends_key():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Analytics-Key"] == "analytics-demo-key"
        assert request.url.path == "/api/v1/analytics/accounts/acc-1/balance"
        return httpx.Response(200, json={"account_id": "acc-1", "balance": 5000, "currency": "KRW"})

    client = _client(handler)
    data = await client.get_balance("acc-1")
    assert data == {"account_id": "acc-1", "balance": 5000, "currency": "KRW"}
    await client.aclose()


@pytest.mark.asyncio
async def test_get_balance_404_returns_none():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error_code": "ACCOUNT_NOT_FOUND"})

    client = _client(handler)
    assert await client.get_balance("missing") is None
    await client.aclose()


@pytest.mark.asyncio
async def test_get_balance_5xx_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error_code": "HTTP_ERROR"})

    client = _client(handler)
    with pytest.raises(FinancialServiceError):
        await client.get_balance("acc-1")
    await client.aclose()


@pytest.mark.asyncio
async def test_connection_error_raises_financial_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    client = _client(handler)
    with pytest.raises(FinancialServiceError):
        await client.get_balance("acc-1")
    await client.aclose()


@pytest.mark.asyncio
async def test_get_ledger_returns_list_and_404_empty():
    def handler(request: httpx.Request) -> httpx.Response:
        if "missing" in str(request.url):
            return httpx.Response(404, json={"error_code": "ACCOUNT_NOT_FOUND"})
        return httpx.Response(
            200,
            json=[
                {
                    "entry_id": "e1",
                    "transaction_id": "t1",
                    "entry_type": "CREDIT",
                    "amount": 1000,
                    "running_balance": 1000,
                    "created_at": "2026-07-01T09:05:00Z",
                }
            ],
        )

    client = _client(handler)
    entries = await client.get_ledger("acc-1")
    assert len(entries) == 1
    assert await client.get_ledger("missing") == []
    await client.aclose()


@pytest.mark.asyncio
async def test_create_account_posts_owner_and_returns_payload():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/api/v1/accounts"
        import json

        body = json.loads(request.content)
        assert body == {"owner": "홍길동", "initial_balance": 1000000}
        return httpx.Response(
            201,
            json={
                "account_id": "acc-new",
                "owner": "홍길동",
                "balance": 1000000,
                "currency": "KRW",
                "created_at": "2026-07-10T00:00:00Z",
            },
        )

    client = _client(handler)
    created = await client.create_account("홍길동", 1000000)
    assert created["account_id"] == "acc-new"
    await client.aclose()


@pytest.mark.asyncio
async def test_create_account_error_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"error_code": "VALIDATION_ERROR"})

    client = _client(handler)
    with pytest.raises(FinancialServiceError):
        await client.create_account("", 0)
    await client.aclose()


@pytest.mark.asyncio
async def test_transfer_sends_idempotency_key_and_body():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/api/v1/transfers"
        assert request.headers["Idempotency-Key"] == "idem-1"
        import json

        body = json.loads(request.content)
        assert body == {
            "sender_account_number": "111-222-333",
            "receiver_bank_name": "KDT은행",
            "receiver_account_number": "444-555-666",
            "amount": 7000,
        }
        return httpx.Response(200, json={"transfer_id": "t1", "status": "success"})

    client = _client(handler)
    res = await client.transfer("111-222-333", "KDT은행", "444-555-666", 7000, "idem-1")
    assert res["transfer_id"] == "t1"
    await client.aclose()


@pytest.mark.asyncio
async def test_transfer_error_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"error_code": "INSUFFICIENT_BALANCE"})

    client = _client(handler)
    with pytest.raises(FinancialServiceError):
        await client.transfer("111-222-333", "KDT은행", "444-555-666", 10**9, "idem-2")
    await client.aclose()


@pytest.mark.asyncio
async def test_error_handler_returns_503_envelope():
    response = await financial_service_error_handler(None, FinancialServiceError())  # type: ignore
    assert response.status_code == 503
    assert b"FINANCIAL_SERVICE_UNAVAILABLE" in response.body


def test_ledger_to_item_credit_and_debit_mapping():
    credit = _ledger_to_item(
        {
            "entry_type": "CREDIT",
            "amount": 3000,
            "created_at": "2026-07-01T09:05:00Z",
        },
        1,
    )
    assert credit.type == "in"
    assert credit.amount == 3000
    assert credit.month == "2026-07"

    debit = _ledger_to_item(
        {
            "entry_type": "DEBIT",
            "amount": 3000,
            "created_at": "2026-07-02T14:20:00Z",
        },
        2,
    )
    assert debit.type == "out"
    assert debit.amount == -3000
    assert debit.day == 2
