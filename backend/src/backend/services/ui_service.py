"""UI Data API 비즈니스 로직 (BFF, ADR-002).

FE 가 component 시그널을 받은 뒤 카드 데이터를 조회하는 계층.

FINANCIAL_CLIENT=mock(기본): 목 픽스처 반환(개발/테스트/CI).
FINANCIAL_CLIENT=http: balance/transactions 는 mock-financial-service(계정계)를
정보계(analytics) 경로로 실조회하고, 원장 데이터를 UI 뷰로 enrich 한다.
spending/budget/cards 는 Phase 1 범위 밖이라 픽스처 유지(결정 B).
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ..core.load_environment_var import settings
from ..repository.account_repository import get_external_account_ids
from ..schemas.ui import (
    AccountSummary,
    BalanceData,
    BudgetData,
    CardsData,
    SpendingData,
    TransactionItem,
    TransactionsData,
)
from .financial import get_financial_client
from .mock.ui_fixtures import (
    BALANCE_FIXTURE,
    BUDGET_FIXTURE,
    CARDS_FIXTURE,
    SPENDING_FIXTURE,
    TRANSACTIONS_FIXTURE,
)

# 계정 메타(은행/별칭/색)는 계정계 원장에 없어 backend 가 채운다(Phase 1 기본 enrich).
_ACCOUNT_COLORS = ["#0052A3", "#FAE100", "#2DD4BF", "#F97316", "#8B5CF6"]
_DEFAULT_BANK = "mock은행"
_DEFAULT_ALIAS = "입출금통장"


def _use_http() -> bool:
    return settings.FINANCIAL_CLIENT.strip().lower() == "http"


def _parse_dt(value: str) -> datetime:
    """계정계 ISO8601(Z 포함) 문자열 파싱."""
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


async def get_balance_view(
    user_id: UUID, session: AsyncSession | None = None
) -> BalanceData:
    """사용자 자산 현황 view model.

    http 모드: 계정계 잔액을 계좌별로 합산. mock 모드: 픽스처.
    """
    if not _use_http() or session is None:
        return BALANCE_FIXTURE

    account_ids = await get_external_account_ids(session, user_id)
    client = get_financial_client()

    summaries: list[AccountSummary] = []
    for idx, account_id in enumerate(account_ids):
        balance = await client.get_balance(account_id)
        if balance is None:  # 404 — 계좌 없음, 건너뜀
            continue
        summaries.append(
            AccountSummary(
                id=idx + 1,
                bank=_DEFAULT_BANK,
                alias=_DEFAULT_ALIAS,
                tail=str(balance["account_id"])[-4:],
                balance=balance["balance"],
                color=_ACCOUNT_COLORS[idx % len(_ACCOUNT_COLORS)],
            )
        )

    return BalanceData(
        total=sum(a.balance for a in summaries),
        accounts=summaries,
    )


def _ledger_to_item(entry: dict, item_id: int) -> TransactionItem:
    """계정계 원장 항목 -> UI 거래 항목(제한된 enrich).

    원장에는 상호명/카테고리/이모지가 없어 CREDIT/DEBIT 기준 기본값을 채운다.
    """
    created = _parse_dt(entry["created_at"])
    is_credit = entry["entry_type"] == "CREDIT"
    amount = entry["amount"] if is_credit else -entry["amount"]
    return TransactionItem(
        id=item_id,
        name="입금" if is_credit else "출금",
        emoji="💰" if is_credit else "💸",
        date=created.strftime("%m.%d %H:%M"),
        month=created.strftime("%Y-%m"),
        day=created.day,
        amount=amount,
        type="in" if is_credit else "out",
        category="수입" if is_credit else "기타",
    )


async def get_transactions_view(
    user_id: UUID, month: str | None = None, session: AsyncSession | None = None
) -> TransactionsData:
    """거래 내역 view model.

    http 모드: 계정계 원장을 계좌별로 조회해 최신순 병합. month(예: '2025-06')
    가 주어지면 해당 월만 필터. mock 모드: 픽스처.
    """
    if not _use_http() or session is None:
        if month is None:
            return TRANSACTIONS_FIXTURE
        items = [tx for tx in TRANSACTIONS_FIXTURE.items if tx.month == month]
        return TransactionsData(months=TRANSACTIONS_FIXTURE.months, items=items)

    account_ids = await get_external_account_ids(session, user_id)
    client = get_financial_client()

    raw: list[dict] = []
    for account_id in account_ids:
        raw.extend(await client.get_ledger(account_id))
    # 계좌 병합 후 최신순 재정렬.
    raw.sort(key=lambda e: e["created_at"], reverse=True)

    items = [_ledger_to_item(e, i + 1) for i, e in enumerate(raw)]
    months = sorted({it.month for it in items}, reverse=True)
    if month is not None:
        items = [it for it in items if it.month == month]
    return TransactionsData(months=months, items=items)


async def get_spending_view(user_id: UUID) -> SpendingData:
    """소비 분석 view model. TODO(Phase 2): 정보계 집계로 교체."""
    _ = user_id
    return SPENDING_FIXTURE


async def get_budget_view(user_id: UUID) -> BudgetData:
    """예산 현황 view model. TODO(Phase 2): 정보계 조회로 교체."""
    _ = user_id
    return BUDGET_FIXTURE


async def get_cards_view(user_id: UUID) -> CardsData:
    """카드 관리 view model. TODO(Phase 2): 계정계(카드) 조회로 교체."""
    _ = user_id
    return CARDS_FIXTURE
