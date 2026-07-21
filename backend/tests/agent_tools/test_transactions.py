"""거래내역(API-TRANSACTION-QUERY)·합계(API-TRANSACTION-SUMMARY) 검증.

원장 로드(_load_ledger_rows)와 repository 를 monkeypatch 로 대체해 DB·계정계 없이
기간/유형 필터·전역 정렬·페이지네이션·집계 로직을 검증한다.
"""

from datetime import date, datetime, timezone
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.agent_exceptions import AgentToolError
from backend.schemas.agent_tools.transaction import (
    SummaryType,
    TransactionQueryRequest,
    TransactionSummaryRequest,
    TransactionType,
)
from backend.schemas.execution_context import ResolvedExecutionContext
from backend.services.agent_tools import transaction_service
from backend.services.agent_tools.transaction_service import _LedgerRow

_NO_SESSION = cast(AsyncSession, None)


def _ctx() -> ResolvedExecutionContext:
    return ResolvedExecutionContext(
        execution_context_id=uuid4(),
        user_id=uuid4(),
        chat_session_id=uuid4(),
        agent_thread_id="thread_1",
        scopes=["account:read"],
        timezone="Asia/Seoul",
    )


def _acct(alias="생활비 통장", currency="KRW"):
    return SimpleNamespace(
        id=uuid4(),
        user_id=uuid4(),
        alias=alias,
        currency=currency,
        external_account_id="ext-1",
        account_number="3333-12-1234567",
        active=True,
    )


def _row(account, entry_type, amount, when: datetime, txn_id=None):
    return _LedgerRow(
        account=account,
        transaction_id=txn_id or f"txn_{uuid4().hex[:6]}",
        occurred_at=when,
        entry_type=entry_type,
        amount=amount,
    )


def _utc(y, m, d, hour=12):
    return datetime(y, m, d, hour, 0, tzinfo=timezone.utc)


def _patch(monkeypatch, owned, rows):
    async def _fake_owned(session, user_id, ids):
        return owned

    async def _fake_rows(owned_arg):
        return rows

    async def _fake_create_ctx(session, **kwargs):
        return SimpleNamespace(id=uuid4())

    monkeypatch.setattr(transaction_service, "get_owned_accounts_by_ids", _fake_owned)
    monkeypatch.setattr(transaction_service, "_load_ledger_rows", _fake_rows)
    monkeypatch.setattr(transaction_service, "create_transaction_query_context", _fake_create_ctx)


def _query_req(account, **overrides) -> TransactionQueryRequest:
    params: dict[str, object] = {
        "account_ids": [str(account.id)],
        "start_date": date(2026, 7, 1),
        "end_date": date(2026, 7, 14),
        **overrides,
    }
    return TransactionQueryRequest.model_validate(params)


# ── API-TRANSACTION-QUERY ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_query_filters_by_period(monkeypatch):
    acc = _acct()
    rows = [
        _row(acc, "DEBIT", 15000, _utc(2026, 7, 10)),
        _row(acc, "DEBIT", 9999, _utc(2026, 7, 20)),  # 범위 밖
    ]
    _patch(monkeypatch, [acc], rows)

    data = await transaction_service.query_transactions(_NO_SESSION, _ctx(), _query_req(acc))

    assert [r.amount for r in data.transaction_results] == [15000]
    assert data.transaction_query_id  # 저장된 Query Context id


@pytest.mark.asyncio
async def test_query_filters_by_type(monkeypatch):
    acc = _acct()
    rows = [
        _row(acc, "CREDIT", 3_200_000, _utc(2026, 7, 5)),
        _row(acc, "DEBIT", 15000, _utc(2026, 7, 6)),
    ]
    _patch(monkeypatch, [acc], rows)

    data = await transaction_service.query_transactions(
        _NO_SESSION, _ctx(), _query_req(acc, transaction_type=TransactionType.DEPOSIT)
    )

    assert [r.transaction_type for r in data.transaction_results] == ["deposit"]
    assert data.transaction_results[0].amount == 3_200_000


@pytest.mark.asyncio
async def test_query_sorts_desc_and_paginates(monkeypatch):
    acc = _acct()
    rows = [
        _row(acc, "DEBIT", 1, _utc(2026, 7, 3), txn_id="a"),
        _row(acc, "DEBIT", 2, _utc(2026, 7, 10), txn_id="b"),
        _row(acc, "DEBIT", 3, _utc(2026, 7, 7), txn_id="c"),
    ]
    _patch(monkeypatch, [acc], rows)

    data = await transaction_service.query_transactions(_NO_SESSION, _ctx(), _query_req(acc, limit=2))

    # 최신순(07-10, 07-07) 2건, 다음 커서 존재
    assert [r.transaction_id for r in data.transaction_results] == ["b", "c"]
    assert data.next_cursor == "2"


@pytest.mark.asyncio
async def test_query_empty_returns_no_cursor(monkeypatch):
    acc = _acct()
    _patch(monkeypatch, [acc], [])

    data = await transaction_service.query_transactions(_NO_SESSION, _ctx(), _query_req(acc))

    assert data.transaction_results == []
    assert data.next_cursor is None
    assert data.transaction_query_id


@pytest.mark.asyncio
async def test_query_preserves_instant_and_maps_fields(monkeypatch):
    acc = _acct(alias="비상금")
    when = _utc(2026, 7, 10)
    _patch(monkeypatch, [acc], [_row(acc, "DEBIT", 15000, when, txn_id="t1")])

    data = await transaction_service.query_transactions(_NO_SESSION, _ctx(), _query_req(acc))

    item = data.transaction_results[0]
    assert item.transaction_id == "t1"
    assert item.account_id == str(acc.id)
    assert item.account_alias == "비상금"
    assert item.transaction_type == "withdrawal"
    assert item.occurred_at == when  # 같은 순간(표현만 KST 로 변환)
    assert item.transaction_title is None  # 원장에 없음
    assert item.category is None


@pytest.mark.asyncio
async def test_query_rejects_unowned(monkeypatch):
    acc = _acct()
    _patch(monkeypatch, [acc], [])  # owned 1개
    req = _query_req(acc)
    req.account_ids = [str(acc.id), str(uuid4())]  # 요청 2개

    with pytest.raises(AgentToolError) as exc:
        await transaction_service.query_transactions(_NO_SESSION, _ctx(), req)
    assert exc.value.code == "ACCOUNT_ACCESS_DENIED"


@pytest.mark.asyncio
async def test_query_malformed_id(monkeypatch):
    acc = _acct()
    _patch(monkeypatch, [acc], [])
    req = _query_req(acc)
    req.account_ids = ["not-a-uuid"]

    with pytest.raises(AgentToolError) as exc:
        await transaction_service.query_transactions(_NO_SESSION, _ctx(), req)
    assert exc.value.code == "INVALID_REQUEST"


# ── API-TRANSACTION-SUMMARY ──────────────────────────────────────────────────


def _summary_req(account, summary_type):
    return TransactionSummaryRequest(
        account_ids=[str(account.id)],
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 14),
        summary_type=summary_type,
    )


@pytest.mark.asyncio
async def test_summary_spending_sums_debit(monkeypatch):
    acc = _acct()
    rows = [
        _row(acc, "DEBIT", 100, _utc(2026, 7, 3)),
        _row(acc, "DEBIT", 200, _utc(2026, 7, 5)),
        _row(acc, "CREDIT", 500, _utc(2026, 7, 6)),  # 지출 아님
        _row(acc, "DEBIT", 9999, _utc(2026, 7, 20)),  # 범위 밖
    ]
    _patch(monkeypatch, [acc], rows)

    data = await transaction_service.summarize_transactions(
        _NO_SESSION, _ctx(), _summary_req(acc, SummaryType.SPENDING)
    )

    assert data.summary_result.total_amount == 300
    assert data.summary_result.transaction_count == 2
    assert data.summary_result.summary_type == "spending"
    assert data.summary_result.currency == "KRW"


@pytest.mark.asyncio
async def test_summary_income_sums_credit(monkeypatch):
    acc = _acct()
    rows = [
        _row(acc, "CREDIT", 3_200_000, _utc(2026, 7, 5)),
        _row(acc, "DEBIT", 200, _utc(2026, 7, 6)),
    ]
    _patch(monkeypatch, [acc], rows)

    data = await transaction_service.summarize_transactions(_NO_SESSION, _ctx(), _summary_req(acc, SummaryType.INCOME))

    assert data.summary_result.total_amount == 3_200_000
    assert data.summary_result.transaction_count == 1


@pytest.mark.asyncio
async def test_summary_empty_is_zero(monkeypatch):
    acc = _acct()
    _patch(monkeypatch, [acc], [])

    data = await transaction_service.summarize_transactions(
        _NO_SESSION, _ctx(), _summary_req(acc, SummaryType.SPENDING)
    )

    assert data.summary_result.total_amount == 0
    assert data.summary_result.transaction_count == 0


# ── 요청 스키마 검증 ─────────────────────────────────────────────────────────


def test_query_request_rejects_end_before_start():
    with pytest.raises(ValueError):
        TransactionQueryRequest(
            account_ids=["a"],
            start_date=date(2026, 7, 14),
            end_date=date(2026, 7, 1),
        )


def test_query_request_rejects_duplicate_accounts():
    with pytest.raises(ValueError):
        TransactionQueryRequest(
            account_ids=["a", "a"],
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 14),
        )


# ── 라우터 인증 게이트 ───────────────────────────────────────────────────────


def test_transactions_query_requires_token(client):
    response = client.post(
        "/api/v1/agent-tools/transactions:query",
        json={
            "account_ids": [str(uuid4())],
            "start_date": "2026-07-01",
            "end_date": "2026-07-14",
        },
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_SERVICE_TOKEN"


def test_transactions_summary_requires_token(client):
    response = client.post(
        "/api/v1/agent-tools/transactions:summary",
        json={
            "account_ids": [str(uuid4())],
            "start_date": "2026-07-01",
            "end_date": "2026-07-14",
            "summary_type": "spending",
        },
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_SERVICE_TOKEN"
