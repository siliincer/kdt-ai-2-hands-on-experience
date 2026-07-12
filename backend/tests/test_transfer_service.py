"""계정계 송금 실행(Phase 2) 단위 테스트.

DB/네트워크 없이 transfer_service 의 분기(모드/수취처/자기송금/장애격리)를 검증한다.
계정계 신 계약: sender=매핑계좌 account_number, receiver=데모 은행명+계좌번호.
"""

from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.financial import transfer_service
from backend.services.financial.financial_client import FinancialServiceError

# 세션은 monkeypatch 로 대체되는 조회에만 넘어가고 실제로 쓰이지 않는다.
_NO_SESSION = cast(AsyncSession, None)


class _FakeClient:
    def __init__(self, result: dict | None = None, error: bool = False):
        self._result = result
        self._error = error
        self.calls = []

    async def transfer(
        self,
        sender_account_number,
        receiver_bank_name,
        receiver_account_number,
        amount,
        idempotency_key,
    ):
        self.calls.append(
            (
                sender_account_number,
                receiver_bank_name,
                receiver_account_number,
                amount,
                idempotency_key,
            )
        )
        if self._error:
            raise FinancialServiceError("down")
        return self._result


def _set_sender(monkeypatch, account_number):
    async def primary(session, user_id):
        if account_number is None:
            return None
        return SimpleNamespace(account_number=account_number)

    monkeypatch.setattr(transfer_service, "get_primary_mapped_account", primary)


@pytest.fixture
def http(monkeypatch):
    monkeypatch.setattr(transfer_service.settings, "FINANCIAL_CLIENT", "http")
    monkeypatch.setattr(
        transfer_service.settings, "FINANCIAL_DEMO_RECEIVER_BANK_NAME", "KDT은행"
    )
    monkeypatch.setattr(
        transfer_service.settings,
        "FINANCIAL_DEMO_RECEIVER_ACCOUNT_NUMBER",
        "444-555-666",
    )
    _set_sender(monkeypatch, "111-222-333")


@pytest.mark.asyncio
async def test_mock_mode_returns_none(monkeypatch):
    monkeypatch.setattr(transfer_service.settings, "FINANCIAL_CLIENT", "mock")
    result = await transfer_service.execute_external_transfer(
        _NO_SESSION, uuid4(), 1000, "k"
    )
    assert result is None


@pytest.mark.asyncio
async def test_success_moves_and_uses_idempotency_key(monkeypatch, http):
    fake = _FakeClient(result={"transfer_id": "t1", "status": "success"})
    monkeypatch.setattr(transfer_service, "get_financial_client", lambda: fake)
    result = await transfer_service.execute_external_transfer(
        _NO_SESSION, uuid4(), 5000, "appr-9"
    )
    assert result is not None
    assert result["transfer_id"] == "t1"
    assert fake.calls == [("111-222-333", "KDT은행", "444-555-666", 5000, "appr-9")]


@pytest.mark.asyncio
async def test_no_mapped_account_returns_none(monkeypatch, http):
    _set_sender(monkeypatch, None)
    fake = _FakeClient(result={"transfer_id": "nope"})
    monkeypatch.setattr(transfer_service, "get_financial_client", lambda: fake)
    result = await transfer_service.execute_external_transfer(
        _NO_SESSION, uuid4(), 1000, "k"
    )
    assert result is None
    assert fake.calls == []


@pytest.mark.asyncio
async def test_missing_receiver_returns_none(monkeypatch):
    monkeypatch.setattr(transfer_service.settings, "FINANCIAL_CLIENT", "http")
    monkeypatch.setattr(
        transfer_service.settings, "FINANCIAL_DEMO_RECEIVER_BANK_NAME", ""
    )
    monkeypatch.setattr(
        transfer_service.settings, "FINANCIAL_DEMO_RECEIVER_ACCOUNT_NUMBER", ""
    )
    _set_sender(monkeypatch, "111-222-333")
    result = await transfer_service.execute_external_transfer(
        _NO_SESSION, uuid4(), 1000, "k"
    )
    assert result is None


@pytest.mark.asyncio
async def test_self_transfer_guarded(monkeypatch, http):
    _set_sender(monkeypatch, "444-555-666")  # sender == receiver number
    fake = _FakeClient(result={"transfer_id": "nope"})
    monkeypatch.setattr(transfer_service, "get_financial_client", lambda: fake)
    result = await transfer_service.execute_external_transfer(
        _NO_SESSION, uuid4(), 1000, "k"
    )
    assert result is None
    assert fake.calls == []


@pytest.mark.asyncio
async def test_outage_is_isolated(monkeypatch, http):
    monkeypatch.setattr(
        transfer_service, "get_financial_client", lambda: _FakeClient(error=True)
    )
    result = await transfer_service.execute_external_transfer(
        _NO_SESSION, uuid4(), 1000, "k"
    )
    assert result is None
