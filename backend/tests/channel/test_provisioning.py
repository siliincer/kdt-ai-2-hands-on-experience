"""회원가입 프로비저닝(Phase 2) 단위 테스트.

DB/네트워크 없이 provisioning 의 분기(모드/멱등/장애격리)를 검증한다.
"""

from typing import cast

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.user import User
from backend.services.financial import provisioning
from backend.services.financial.financial_client import FinancialServiceError

# 테스트는 provisioning 의 DB 접근을 monkeypatch 로 대체하므로 세션은 쓰이지 않는다.
_NO_SESSION = cast(AsyncSession, None)


def _user() -> User:
    return User(email="hong@test.com", name="홍길동", password_hash="x")


class _FakeClient:
    def __init__(self, result: dict | None = None, error: bool = False):
        self._result = result
        self._error = error
        self.calls = 0

    async def create_account(self, owner: str, initial_balance: int = 0, bank_name: str | None = None) -> dict | None:
        self.calls += 1
        self.last_bank_name = bank_name
        if self._error:
            raise FinancialServiceError("down")
        return self._result


@pytest.fixture
def created(monkeypatch):
    """create_mapped_account 를 가로채 저장된 매핑을 기록한다."""
    recorded = {}

    async def fake_create_mapped_account(session, **kwargs):
        recorded.update(kwargs)
        return None

    async def fake_has_mapped_account(session, user_id):
        return False

    monkeypatch.setattr(provisioning, "create_mapped_account", fake_create_mapped_account)
    monkeypatch.setattr(provisioning, "has_mapped_account", fake_has_mapped_account)
    return recorded


@pytest.mark.asyncio
async def test_http_mode_provisions_and_maps(monkeypatch, created):
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

    result = await provisioning.provision_account_for_user(_NO_SESSION, _user())
    assert result == "acc-x"
    assert created["external_account_id"] == "acc-x"
    assert created["balance"] == 1000000
    # 계정계가 부여한 실제 계좌번호/은행명을 그대로 저장한다.
    assert created["account_number"] == "271-069-693651"
    assert created["bank_name"] == "KDT은행"


@pytest.mark.asyncio
async def test_http_mode_falls_back_to_local_number_when_absent(monkeypatch, created):
    """구버전 계정계(account_number 미반환) 호환: 로컬 임시번호로 대체."""
    fake = _FakeClient(result={"account_id": "acc-y", "balance": 0, "currency": "KRW"})
    monkeypatch.setattr(provisioning, "get_financial_client", lambda: fake)

    result = await provisioning.provision_account_for_user(_NO_SESSION, _user())
    assert result == "acc-y"
    assert created["account_number"].startswith("MFS")
    assert created["bank_name"] is None


@pytest.mark.asyncio
async def test_financial_outage_is_isolated(monkeypatch, created):
    monkeypatch.setattr(provisioning, "get_financial_client", lambda: _FakeClient(error=True))
    # 장애여도 예외 전파 없이 None (회원가입 계속, 결정 D).
    result = await provisioning.provision_account_for_user(_NO_SESSION, _user())
    assert result is None
    assert created == {}


@pytest.mark.asyncio
async def test_already_mapped_is_idempotent(monkeypatch):
    async def already_mapped(session, user_id):
        return True

    fake = _FakeClient(result={"account_id": "should-not-be-used"})
    monkeypatch.setattr(provisioning, "has_mapped_account", already_mapped)
    monkeypatch.setattr(provisioning, "get_financial_client", lambda: fake)

    result = await provisioning.provision_account_for_user(_NO_SESSION, _user())
    assert result is None
    assert fake.calls == 0


# ── 계좌 추가(/add_account) ──────────────────────────────────────────────────


def test_normalize_bank_name_accepts_supported_and_normalizes():
    # 공백·대소문자 차이를 흡수해 정식 표기로 돌려준다.
    assert provisioning.normalize_bank_name("신한은행") == "신한은행"
    assert provisioning.normalize_bank_name("kdt 은행") == "KDT은행"


def test_normalize_bank_name_rejects_unsupported():
    with pytest.raises(HTTPException) as exc:
        provisioning.normalize_bank_name("없는은행")
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_add_account_creates_with_requested_bank(monkeypatch, created):
    fake = _FakeClient(
        result={
            "account_id": "acc-add",
            "account_number": "399-111-222333",
            "bank_name": "신한은행",
            "balance": 1000000,
            "currency": "KRW",
        }
    )
    monkeypatch.setattr(provisioning, "get_financial_client", lambda: fake)

    await provisioning.add_account_for_user(_NO_SESSION, _user(), "신한은행")

    assert fake.last_bank_name == "신한은행"  # 계정계에도 은행명을 전달한다
    assert created["external_account_id"] == "acc-add"
    assert created["bank_name"] == "신한은행"
    assert created["balance"] == 1000000  # 회원가입 프로비저닝과 동일한 기본값


@pytest.mark.asyncio
async def test_add_account_financial_outage_is_503(monkeypatch, created):
    # 사용자가 명시적으로 요청한 동작이라 계정계 장애를 삼키지 않고 알린다.
    monkeypatch.setattr(provisioning, "get_financial_client", lambda: _FakeClient(error=True))

    with pytest.raises(HTTPException) as exc:
        await provisioning.add_account_for_user(_NO_SESSION, _user(), "신한은행")
    assert exc.value.status_code == 503
