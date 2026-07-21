"""거래내역 조회(API-TRANSACTION-QUERY)·기간 합계(API-TRANSACTION-SUMMARY) 로직.

계정계 원장에는 기간·유형 필터가 없어(D4) Backend 가 계좌별 원장을 병합해 메모리에서
기간·유형 필터·전역 정렬·페이지네이션·집계를 수행한다. title·category·keyword 매칭은
계정계에 원천 데이터가 없어 미지원(None/무시)하며 TODO(계정계)로 남긴다.

원장은 계정계(정보계)에서 실조회한다(mock 일원화, 작업 B). 테스트는 _load_ledger_rows
또는 계정계 HTTP 클라이언트를 stub 으로 대체한다.
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
    rows = await _load_ledger_rows(owned)
    tz = resolve_tz(context.timezone)

    filtered = [r for r in rows if _within_period(r.occurred_at, tz, req.start_date, req.end_date)]
    if req.transaction_type is not None:
        # TODO(계정계): transfer 는 원장 entry 만으로 구분 불가 → 현재 매칭 없음.
        want = req.transaction_type.value
        filtered = [r for r in filtered if _entry_to_txn_type(r.entry_type) == want]

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
            transaction_title=None,  # TODO(계정계): 원장에 표시용 상호명 없음
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
    rows = await _load_ledger_rows(owned)
    tz = resolve_tz(context.timezone)

    in_period = [r for r in rows if _within_period(r.occurred_at, tz, req.start_date, req.end_date)]
    # spending=DEBIT(출금), income=CREDIT(입금). keyword 는 원장에 원천 없어 무시(TODO).
    target = "DEBIT" if req.summary_type.value == "spending" else "CREDIT"
    matched = [r for r in in_period if r.entry_type == target]

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
