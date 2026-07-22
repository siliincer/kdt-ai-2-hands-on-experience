"""계좌 목록(API-ACCOUNT-LIST)·잔액 조회(API-BALANCE-QUERY) 검증.

서비스 로직은 repository 를 monkeypatch 로 대체해 DB 없이 검증한다. 잔액은 계정계
정보계가 정본이므로 `financial_stub`(httpx.MockTransport)로 응답을 흉내낸다(mock 일원화).
라우터는 실제 앱에서 인증 게이트만 확인한다.
"""

from types import SimpleNamespace
from typing import cast
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.agent_exceptions import AgentToolError
from backend.schemas.agent_tools.account import (
    AccountCapability,
    BalanceQueryRequest,
)
from backend.schemas.execution_context import ResolvedExecutionContext
from backend.services.agent_tools import account_service

_NO_SESSION = cast(AsyncSession, None)


def _ctx(user_id: UUID | None = None) -> ResolvedExecutionContext:
    return ResolvedExecutionContext(
        execution_context_id=uuid4(),
        user_id=user_id or uuid4(),
        chat_session_id=uuid4(),
        agent_thread_id="thread_1",
        scopes=["account:read"],
        timezone="Asia/Seoul",
    )


def _acct(**overrides):
    base = dict(
        id=uuid4(),
        user_id=uuid4(),
        account_number="3333-12-1234567",
        bank_name="카카오뱅크",
        alias="생활비 통장",
        account_type="checking",
        currency="KRW",
        is_default=True,
        active=True,
        external_account_id="ext-1",
        balance=1_250_000,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _patch_mapped(monkeypatch, accounts):
    async def _fetch(session, user_id):
        return accounts

    monkeypatch.setattr(account_service, "get_mapped_accounts", _fetch)


def _patch_owned(monkeypatch, accounts):
    async def _fetch(session, user_id, ids):
        wanted = set(ids)
        return [a for a in accounts if a.id in wanted]

    monkeypatch.setattr(account_service, "get_owned_accounts_by_ids", _fetch)


# ── API-ACCOUNT-LIST ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_maps_and_masks(monkeypatch):
    account = _acct()
    _patch_mapped(monkeypatch, [account])

    data = await account_service.list_accounts(_NO_SESSION, _ctx(), None, None, 20)

    assert len(data.accounts) == 1
    item = data.accounts[0]
    assert item.account_id == str(account.id)
    assert item.account_alias == "생활비 통장"
    assert item.account_type == "checking"
    assert item.masked_account_number == "3333-**-1234567"
    assert item.is_default is True
    assert item.status == "active"


@pytest.mark.asyncio
async def test_list_hint_filters_on_bank_alias_type(monkeypatch):
    a1 = _acct(alias="생활비 통장", bank_name="카카오뱅크")
    a2 = _acct(alias="비상금", bank_name="신한은행")
    _patch_mapped(monkeypatch, [a1, a2])

    data = await account_service.list_accounts(_NO_SESSION, _ctx(), "생활비", None, 20)

    assert [i.account_alias for i in data.accounts] == ["생활비 통장"]


@pytest.mark.asyncio
async def test_list_capability_keeps_only_active(monkeypatch):
    active = _acct(active=True)
    inactive = _acct(active=False)
    _patch_mapped(monkeypatch, [active, inactive])

    data = await account_service.list_accounts(_NO_SESSION, _ctx(), None, AccountCapability.WITHDRAW, 20)

    assert [i.status for i in data.accounts] == ["active"]


@pytest.mark.asyncio
async def test_list_applies_limit(monkeypatch):
    _patch_mapped(monkeypatch, [_acct() for _ in range(5)])

    data = await account_service.list_accounts(_NO_SESSION, _ctx(), None, None, 2)

    assert len(data.accounts) == 2


@pytest.mark.asyncio
async def test_list_without_resolution_leaves_outcome_none(monkeypatch):
    _patch_mapped(monkeypatch, [_acct(), _acct()])

    data = await account_service.list_accounts(_NO_SESSION, _ctx(), None, None, 20)

    assert data.account_resolution_outcome is None
    assert data.account_ids == []


# ── 계좌 해소(resolve_selection, 계약 9.2) ────────────────────────────────────


@pytest.mark.asyncio
async def test_resolve_single_account_is_resolved(monkeypatch):
    account = _acct()
    _patch_mapped(monkeypatch, [account])

    data = await account_service.list_accounts(_NO_SESSION, _ctx(), None, None, 20, resolve_selection=True)

    assert data.account_resolution_outcome == "resolved"
    assert data.account_ids == [str(account.id)]


@pytest.mark.asyncio
async def test_resolve_multiple_requires_selection(monkeypatch):
    _patch_mapped(monkeypatch, [_acct(), _acct()])

    data = await account_service.list_accounts(_NO_SESSION, _ctx(), None, None, 20, resolve_selection=True)

    assert data.account_resolution_outcome == "selection_required"
    assert data.account_ids == []
    assert len(data.accounts) == 2  # 사용자 선택용 후보는 함께 내려준다


@pytest.mark.asyncio
async def test_resolve_all_accounts_requested_is_resolved(monkeypatch):
    a1, a2 = _acct(), _acct()
    _patch_mapped(monkeypatch, [a1, a2])

    data = await account_service.list_accounts(
        _NO_SESSION,
        _ctx(),
        None,
        None,
        20,
        resolve_selection=True,
        all_accounts_requested=True,
    )

    assert data.account_resolution_outcome == "resolved"
    assert set(data.account_ids) == {str(a1.id), str(a2.id)}


@pytest.mark.asyncio
async def test_resolve_no_candidates_is_no_accounts(monkeypatch):
    _patch_mapped(monkeypatch, [])

    data = await account_service.list_accounts(_NO_SESSION, _ctx(), None, None, 20, resolve_selection=True)

    assert data.account_resolution_outcome == "no_accounts"
    assert data.account_ids == []


@pytest.mark.asyncio
async def test_resolve_hint_narrows_to_single_resolved(monkeypatch):
    keep = _acct(alias="생활비 통장", bank_name="카카오뱅크")
    other = _acct(alias="비상금", bank_name="신한은행")
    _patch_mapped(monkeypatch, [keep, other])

    data = await account_service.list_accounts(_NO_SESSION, _ctx(), "생활비", None, 20, resolve_selection=True)

    assert data.account_resolution_outcome == "resolved"
    assert data.account_ids == [str(keep.id)]


@pytest.mark.asyncio
async def test_resolve_excludes_account_ids(monkeypatch):
    keep = _acct()
    drop = _acct()
    _patch_mapped(monkeypatch, [keep, drop])

    data = await account_service.list_accounts(
        _NO_SESSION,
        _ctx(),
        None,
        None,
        20,
        resolve_selection=True,
        exclude_account_ids=[str(drop.id)],
    )

    # drop 제외 후 단일 후보 → resolved
    assert data.account_resolution_outcome == "resolved"
    assert data.account_ids == [str(keep.id)]


# ── API-BALANCE-QUERY ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_balances_http_reads_ledger_and_available_equals_balance(monkeypatch, financial_stub):
    account = _acct(external_account_id="ext-b", balance=0)
    financial_stub.balances["ext-b"] = {"balance": 777_000, "currency": "KRW"}
    _patch_owned(monkeypatch, [account])

    data = await account_service.query_balances(_NO_SESSION, _ctx(), [str(account.id)])

    assert len(data.balance_results) == 1
    result = data.balance_results[0]
    # 잔액 정본은 계정계(정보계)다 — 로컬 Account.balance(0)가 아니라 stub 값.
    assert result.balance == 777_000
    assert result.available_balance == 777_000
    assert result.masked_account_number == "3333-**-1234567"


@pytest.mark.asyncio
async def test_balances_preserves_request_order(monkeypatch, financial_stub):
    a1 = _acct(external_account_id="ext-1", balance=0)
    a2 = _acct(external_account_id="ext-2", balance=0)
    financial_stub.balances["ext-1"] = {"balance": 100, "currency": "KRW"}
    financial_stub.balances["ext-2"] = {"balance": 200, "currency": "KRW"}
    _patch_owned(monkeypatch, [a1, a2])

    data = await account_service.query_balances(_NO_SESSION, _ctx(), [str(a2.id), str(a1.id)])

    assert [r.account_id for r in data.balance_results] == [str(a2.id), str(a1.id)]


@pytest.mark.asyncio
async def test_balances_rejects_when_any_not_owned(monkeypatch):
    owned = _acct()
    _patch_owned(monkeypatch, [owned])  # 요청 2개 중 1개만 소유

    with pytest.raises(AgentToolError) as exc:
        await account_service.query_balances(_NO_SESSION, _ctx(), [str(owned.id), str(uuid4())])
    assert exc.value.status_code == 403
    assert exc.value.code == "ACCOUNT_ACCESS_DENIED"


@pytest.mark.asyncio
async def test_balances_malformed_id_is_request_error(monkeypatch):
    _patch_owned(monkeypatch, [])
    with pytest.raises(AgentToolError) as exc:
        await account_service.query_balances(_NO_SESSION, _ctx(), ["not-a-uuid"])
    assert exc.value.status_code == 400
    assert exc.value.code == "INVALID_REQUEST"


# ── 요청 스키마 검증 ─────────────────────────────────────────────────────────


def test_request_rejects_duplicates():
    with pytest.raises(ValidationError):
        BalanceQueryRequest(account_ids=["a", "a"])


def test_request_rejects_empty():
    with pytest.raises(ValidationError):
        BalanceQueryRequest(account_ids=[])


def test_request_rejects_over_20():
    with pytest.raises(ValidationError):
        BalanceQueryRequest(account_ids=[str(i) for i in range(21)])


# ── 라우터 인증 게이트(실제 앱, DB 불필요) ──────────────────────────────────


def test_accounts_endpoint_requires_service_token(client):
    response = client.get("/api/v1/agent-tools/accounts")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_SERVICE_TOKEN"


def test_balances_endpoint_requires_service_token(client):
    response = client.post(
        "/api/v1/agent-tools/accounts/balances:query",
        json={"account_ids": [str(uuid4())]},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_SERVICE_TOKEN"
