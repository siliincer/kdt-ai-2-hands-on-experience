"""거래내역 조회(API-TRANSACTION-QUERY)·기간 합계(API-TRANSACTION-SUMMARY) 로직.

계정계 원장에는 기간·유형 필터가 없어(D4) Backend 가 계좌별 원장을 병합해 메모리에서
기간·유형 필터·전역 정렬·페이지네이션·집계를 수행한다. 계좌 원장(송금류)은 상호명이
없어 category 는 여전히 미지원(None)이지만, keyword(상호명) 매칭은 카드 원장(구매내역)을
같이 합류시켜 지원한다 — 카드 구매는 결제 시점엔 계좌 잔액에 반영되지 않지만(계정계
정산 전) 조회 전용으로만 합치므로 잔액/원장 불변식에는 영향 없다.

원장은 계정계(정보계)에서 실조회한다(mock 일원화, 작업 B). 테스트는 _load_ledger_rows/
_load_card_rows 또는 계정계 HTTP 클라이언트를 stub 으로 대체한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from ...core.agent_exceptions import AgentToolError
from ...models.account import Account
from ...repository.account_repository import get_owned_accounts_by_ids
from ...repository.transaction_query_repository import (
    create_transaction_query_context,
)
from ...schemas.agent_tools.transaction import (
    TransactionQueryData,
    TransactionQueryRequest,
    TransactionResultItem,
    TransactionSummaryData,
    TransactionSummaryRequest,
    TransactionSummaryResult,
    TransactionType,
)
from ...schemas.execution_context import ResolvedExecutionContext
from ...utils.datetime_parse import parse_iso_utc
from ...utils.parsing import parse_uuid_list
from ...utils.timezone import resolve_tz
from ..financial import get_financial_client

# 계정계 원장에 기간 필터가 없어 계좌별로 넉넉히 가져와 메모리 필터한다.
# TODO(계정계): /ledger 에 start_date·end_date 파라미터가 생기면 하향 위임.
_LEDGER_FETCH_CAP = 200
# 거래내역 Query Context 유효시간(초). 이후 페이지를 Frontend 가 재조회하는 창.
_QUERY_CONTEXT_TTL_SECONDS = 900


def _entry_to_txn_type(entry_type: str) -> str:
    """계정계 entry_type → 계약 transaction_type. CREDIT=deposit, DEBIT=withdrawal."""
    return "deposit" if entry_type == "CREDIT" else "withdrawal"


@dataclass
class _LedgerRow:
    account: Account
    transaction_id: str
    occurred_at: datetime
    entry_type: str
    amount: int
    merchant_name: str | None = None


def _invalid_account_ids() -> AgentToolError:
    return AgentToolError.invalid_request("account_ids 형식이 올바르지 않습니다.")


async def _load_owned(
    session: AsyncSession,
    context: ResolvedExecutionContext,
    account_ids: list[str],
) -> list[Account]:
    """소유권 검증. 한 계좌라도 소유·접근 실패면 전체 거절(계약 11.4)."""
    parsed = parse_uuid_list(account_ids, _invalid_account_ids)
    owned = await get_owned_accounts_by_ids(session, context.user_id, parsed)
    if len(owned) != len(parsed):
        raise AgentToolError.account_access_denied()
    return owned


async def _load_ledger_rows(owned: list[Account]) -> list[_LedgerRow]:
    """소유 계좌들의 원장을 병합한다(계정계 정보계 실조회)."""
    client = get_financial_client()
    rows: list[_LedgerRow] = []
    for account in owned:
        if not account.external_account_id:
            continue
        entries = await client.get_ledger(account.external_account_id, limit=_LEDGER_FETCH_CAP)
        for entry in entries:
            rows.append(
                _LedgerRow(
                    account=account,
                    transaction_id=entry["transaction_id"],
                    occurred_at=parse_iso_utc(entry["created_at"]),
                    entry_type=entry["entry_type"],
                    amount=int(entry["amount"]),
                )
            )
    return rows


async def _load_card_rows(owned: list[Account]) -> list[_LedgerRow]:
    """소유 계좌에 연결된 카드의 구매내역을 원장 행 형태로 병합한다.

    카드 구매는 계좌 원장(ledger_entries)에 정산되어 들어오지 않아(결제 시점엔
    잔액 미변경) 계좌 원장만 봐서는 상호명이 전혀 안 잡힌다 — 카드 원장을
    별도로 조회해 지출(DEBIT)로 합류시킨다. 잔액에는 영향 없음(조회 전용).
    """
    client = get_financial_client()
    rows: list[_LedgerRow] = []
    for account in owned:
        if not account.external_account_id:
            continue
        cards = await client.get_cards(account.external_account_id)
        for card in cards:
            entries = await client.get_card_ledger(card["card_id"], limit=_LEDGER_FETCH_CAP)
            for entry in entries:
                rows.append(
                    _LedgerRow(
                        account=account,
                        transaction_id=entry["card_ledger_entry_id"],
                        occurred_at=parse_iso_utc(entry["created_at"]),
                        entry_type="DEBIT",
                        amount=int(entry["amount"]),
                        merchant_name=entry.get("merchant_name"),
                    )
                )
    return rows


async def _load_all_rows(owned: list[Account]) -> list[_LedgerRow]:
    """계좌 원장 + 카드 원장을 합친 전체 거래 행."""
    ledger_rows = await _load_ledger_rows(owned)
    card_rows = await _load_card_rows(owned)
    return ledger_rows + card_rows


def _matches_keyword(row: _LedgerRow, keyword: str | None) -> bool:
    """상호명 키워드 매칭(대소문자 무시). 상호명 없는 행(송금류)은 매칭 안 됨."""
    if keyword is None:
        return True
    return bool(row.merchant_name) and keyword.lower() in row.merchant_name.lower()


def _within_period(occurred_at: datetime, tz: ZoneInfo | timezone, start: date, end: date) -> bool:
    """사용자 타임존 기준 날짜가 [start, end] 양끝 포함 범위인지(계약 12장)."""
    local_date = occurred_at.astimezone(tz).date()
    return start <= local_date <= end


async def query_transactions(
    session: AsyncSession,
    context: ResolvedExecutionContext,
    req: TransactionQueryRequest,
) -> TransactionQueryData:
    """거래내역 첫 페이지를 조회하고 이후 페이지용 Query Context 를 저장한다."""
    owned = await _load_owned(session, context, req.account_ids)
    rows = await _load_all_rows(owned)
    tz = resolve_tz(context.timezone)

    filtered = [r for r in rows if _within_period(r.occurred_at, tz, req.start_date, req.end_date)]
    if req.transaction_type is not None:
        # TODO(계정계): transfer 는 원장 entry 만으로 구분 불가 → 현재 매칭 없음.
        want = req.transaction_type.value
        filtered = [r for r in filtered if _entry_to_txn_type(r.entry_type) == want]
    if req.keyword is not None:
        filtered = [r for r in filtered if _matches_keyword(r, req.keyword)]

    filtered.sort(key=lambda r: r.occurred_at, reverse=True)

    page = filtered[: req.limit]
    next_cursor = str(req.limit) if len(filtered) > req.limit else None

    results = [
        TransactionResultItem(
            transaction_id=r.transaction_id,
            account_id=str(r.account.id),
            account_alias=r.account.alias,
            occurred_at=r.occurred_at.astimezone(tz),
            transaction_type=_entry_to_txn_type(r.entry_type),
            amount=r.amount,
            currency=r.account.currency,
            transaction_title=r.merchant_name or ("입금" if r.entry_type == "CREDIT" else "출금"),
            category=None,  # TODO(계정계): 원장에 카테고리 없음
        )
        for r in page
    ]

    expires_at = datetime.now(timezone.utc) + timedelta(seconds=_QUERY_CONTEXT_TTL_SECONDS)
    query_ctx = await create_transaction_query_context(
        session,
        user_id=context.user_id,
        account_ids=req.account_ids,
        start_date=req.start_date,
        end_date=req.end_date,
        keyword=req.keyword,
        transaction_type=(req.transaction_type.value if req.transaction_type else None),
        page_size=req.limit,
        expires_at=expires_at,
    )

    return TransactionQueryData(
        transaction_results=results,
        transaction_query_id=str(query_ctx.id),
        next_cursor=next_cursor,
    )


async def summarize_transactions(
    session: AsyncSession,
    context: ResolvedExecutionContext,
    req: TransactionSummaryRequest,
) -> TransactionSummaryData:
    """기간 내 지출/수입 합계를 집계한다. 조건에 맞는 거래가 없으면 0 을 반환."""
    owned = await _load_owned(session, context, req.account_ids)
    rows = await _load_all_rows(owned)
    tz = resolve_tz(context.timezone)

    in_period = [r for r in rows if _within_period(r.occurred_at, tz, req.start_date, req.end_date)]
    # spending=DEBIT(출금·카드결제), income=CREDIT(입금).
    target = "DEBIT" if req.summary_type.value == "spending" else "CREDIT"
    matched = [r for r in in_period if r.entry_type == target]
    if req.keyword is not None:
        matched = [r for r in matched if _matches_keyword(r, req.keyword)]

    currency = owned[0].currency if owned else "KRW"
    result = TransactionSummaryResult(
        summary_type=req.summary_type.value,
        total_amount=sum(r.amount for r in matched),
        transaction_count=len(matched),
        currency=currency,
        start_date=req.start_date,
        end_date=req.end_date,
    )
    return TransactionSummaryData(summary_result=result)


# transaction_type import 는 라우터/테스트에서 재사용될 수 있어 노출.
__all__ = [
    "query_transactions",
    "summarize_transactions",
    "TransactionType",
]
