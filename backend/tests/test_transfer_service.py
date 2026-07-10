"""계정계 송금 실행(Phase 2) 단위 테스트.

DB/네트워크 없이 transfer_service 의 분기(모드/수취계좌/자기송금/장애격리)를 검증한다.
"""

from uuid import uuid4

import pytest

from backend.services.financial import transfer_service
from backend.services.financial.financial_client import FinancialServiceError


class _FakeClient:
    def __init__(self, result=None, error=False):
        self._result = result
        self._error = error
        self.calls = []

    async def transfer(
        self, sender_account_id, receiver_account_id, amount, idempotency_key
    ):
        self.calls.append(
            (sender_account_id, receiver_account_id, amount, idempotency_key)
        )
        if self._error:
            raise FinancialServiceError("down")
        return self._result


def _set_sender(monkeypatch, ids):
    async def ext(session, user_id):
        return ids

    monkeypatch.setattr(transfer_service, "get_external_account_ids", ext)


@pytest.fixture
def http(monkeypatch):
    monkeypatch.setattr(transfer_service.settings, "FINANCIAL_CLIENT", "http")
    monkeypatch.setattr(
        transfer_service.settings, "FINANCIAL_DEMO_RECEIVER_ACCOUNT_ID", "recv-1"
    )
    _set_sender(monkeypatch, ["send-1"])


@pytest.mark.asyncio
async def test_mock_mode_returns_none(monkeypatch):
    monkeypatch.setattr(transfer_service.settings, "FINANCIAL_CLIENT", "mock")
    result = await transfer_service.execute_external_transfer(None, uuid4(), 1000, "k")
    assert result is None


@pytest.mark.asyncio
async def test_success_moves_and_uses_idempotency_key(monkeypatch, http):
    fake = _FakeClient(result={"transfer_id": "t1", "status": "COMPLETED"})
    monkeypatch.setattr(transfer_service, "get_financial_client", lambda: fake)
    result = await transfer_service.execute_external_transfer(
        None, uuid4(), 5000, "appr-9"
    )
    assert result["transfer_id"] == "t1"
    assert fake.calls == [("send-1", "recv-1", 5000, "appr-9")]


@pytest.mark.asyncio
async def test_missing_receiver_returns_none(monkeypatch):
    monkeypatch.setattr(transfer_service.settings, "FINANCIAL_CLIENT", "http")
    monkeypatch.setattr(
        transfer_service.settings, "FINANCIAL_DEMO_RECEIVER_ACCOUNT_ID", ""
    )
    _set_sender(monkeypatch, ["send-1"])
    result = await transfer_service.execute_external_transfer(None, uuid4(), 1000, "k")
    assert result is None


@pytest.mark.asyncio
async def test_self_transfer_guarded(monkeypatch):
    monkeypatch.setattr(transfer_service.settings, "FINANCIAL_CLIENT", "http")
    monkeypatch.setattr(
        transfer_service.settings, "FINANCIAL_DEMO_RECEIVER_ACCOUNT_ID", "same"
    )
    _set_sender(monkeypatch, ["same"])
    fake = _FakeClient(result={"transfer_id": "nope"})
    monkeypatch.setattr(transfer_service, "get_financial_client", lambda: fake)
    result = await transfer_service.execute_external_transfer(None, uuid4(), 1000, "k")
    assert result is None
    assert fake.calls == []


@pytest.mark.asyncio
async def test_outage_is_isolated(monkeypatch, http):
    monkeypatch.setattr(
        transfer_service, "get_financial_client", lambda: _FakeClient(error=True)
    )
    result = await transfer_service.execute_external_transfer(None, uuid4(), 1000, "k")
    assert result is None
