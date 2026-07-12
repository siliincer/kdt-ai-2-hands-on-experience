"""회원가입 프로비저닝(Phase 2) 단위 테스트.

DB/네트워크 없이 provisioning 의 분기(모드/멱등/장애격리)를 검증한다.
"""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from backend.services.financial import provisioning
from backend.services.financial.financial_client import FinancialServiceError


def _user():
    return SimpleNamespace(id=uuid4(), name="홍길동", email="hong@test.com")


class _FakeClient:
    def __init__(self, result=None, error=False):
        self._result = result
        self._error = error
        self.calls = 0

    async def create_account(self, owner: str, initial_balance: int = 0) -> dict:
        self.calls += 1
        if self._error:
            raise FinancialServiceError("down")
        return self._result


@pytest.fixture
def created(monkeypatch):
    """create_mapped_account 를 가로채 저장된 매핑을 기록한다."""
    recorded = {}

    async def fake_create_mapped_account(session, **kwargs):
        recorded.update(kwargs)
        return SimpleNamespace(**kwargs)

    async def fake_has_mapped_account(session, user_id):
        return False

    monkeypatch.setattr(
        provisioning, "create_mapped_account", fake_create_mapped_account
    )
    monkeypatch.setattr(provisioning, "has_mapped_account", fake_has_mapped_account)
    return recorded


@pytest.mark.asyncio
async def test_mock_mode_skips_provisioning(monkeypatch, created):
    monkeypatch.setattr(provisioning.settings, "FINANCIAL_CLIENT", "mock")
    result = await provisioning.provision_account_for_user(None, _user())
    assert result is None
    assert created == {}


@pytest.mark.asyncio
async def test_http_mode_provisions_and_maps(monkeypatch, created):
    monkeypatch.setattr(provisioning.settings, "FINANCIAL_CLIENT", "http")
    fake = _FakeClient(
        result={
            "account_id": "acc-x",
            "account_number": "271-069-693651",
            "bank_name": "KDT은행",
            "balance": 1000000,
            "currency": "KRW",
        }
    )
    monkeypatch.setattr(provisioning, "get_financial_client", lambda: fake)

    result = await provisioning.provision_account_for_user(None, _user())
    assert result == "acc-x"
    assert created["external_account_id"] == "acc-x"
    assert created["balance"] == 1000000
    # 계정계가 부여한 실제 계좌번호/은행명을 그대로 저장한다.
    assert created["account_number"] == "271-069-693651"
    assert created["bank_name"] == "KDT은행"


@pytest.mark.asyncio
async def test_http_mode_falls_back_to_local_number_when_absent(monkeypatch, created):
    """구버전 계정계(account_number 미반환) 호환: 로컬 임시번호로 대체."""
    monkeypatch.setattr(provisioning.settings, "FINANCIAL_CLIENT", "http")
    fake = _FakeClient(result={"account_id": "acc-y", "balance": 0, "currency": "KRW"})
    monkeypatch.setattr(provisioning, "get_financial_client", lambda: fake)

    result = await provisioning.provision_account_for_user(None, _user())
    assert result == "acc-y"
    assert created["account_number"].startswith("MFS")
    assert created["bank_name"] is None


@pytest.mark.asyncio
async def test_financial_outage_is_isolated(monkeypatch, created):
    monkeypatch.setattr(provisioning.settings, "FINANCIAL_CLIENT", "http")
    monkeypatch.setattr(
        provisioning, "get_financial_client", lambda: _FakeClient(error=True)
    )
    # 장애여도 예외 전파 없이 None (회원가입 계속, 결정 D).
    result = await provisioning.provision_account_for_user(None, _user())
    assert result is None
    assert created == {}


@pytest.mark.asyncio
async def test_already_mapped_is_idempotent(monkeypatch):
    monkeypatch.setattr(provisioning.settings, "FINANCIAL_CLIENT", "http")

    async def already_mapped(session, user_id):
        return True

    fake = _FakeClient(result={"account_id": "should-not-be-used"})
    monkeypatch.setattr(provisioning, "has_mapped_account", already_mapped)
    monkeypatch.setattr(provisioning, "get_financial_client", lambda: fake)

    result = await provisioning.provision_account_for_user(None, _user())
    assert result is None
    assert fake.calls == 0
