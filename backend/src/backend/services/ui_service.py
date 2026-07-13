"""UI Data API 비즈니스 로직 (BFF, ADR-002).

FE 가 component 시그널을 받은 뒤 카드 데이터를 조회하는 계층.

FINANCIAL_CLIENT=mock(기본): 목 픽스처 반환(개발/테스트/CI).
FINANCIAL_CLIENT=http: mock-financial-service(계정계)를 정보계(analytics) 경로로
실조회하고 원장 데이터를 UI 뷰로 enrich 한다. 원장에 없는 필드(상호/카테고리/
은행/카드 메타)는 기본값으로 대체한다(원장은 순수 이중기입 원장이라 표시용 메타 없음).
"""

from datetime import datetime
from typing import cast
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.load_environment_var import settings
from ..repository.account_repository import (
    get_external_account_ids,
    get_mapped_accounts,
)
from ..schemas.ui import (
    AccountDetailData,
    AccountDetailInfo,
    AccountSummary,
    BalanceData,
    BudgetData,
    BudgetItem,
    CardsData,
    CatTxDatum,
    CreditCard,
    MonthlySpendDatum,
    PieDatum,
    RecentTxItem,
    SpendingData,
    TransactionItem,
    TransactionsData,
)
from .financial import get_financial_client
from .mock.ui_fixtures import (
    ACCOUNT_DETAIL_FIXTURE,
    BALANCE_FIXTURE,
    BUDGET_FIXTURE,
    CARDS_FIXTURE,
    SPENDING_FIXTURE,
    TRANSACTIONS_FIXTURE,
)

# 계정 메타(은행/별칭/색)는 계정계 원장에 없어 backend 가 채운다(기본 enrich).
_ACCOUNT_COLORS = ["#0052A3", "#FAE100", "#2DD4BF", "#F97316", "#8B5CF6"]
_DEFAULT_BANK = "mock은행"
_DEFAULT_ALIAS = "입출금통장"

# 소비/예산 기본값(원장에 카테고리/예산목표/구독 없음 → 단일 '기타' 버킷 + 기본 예산).
_DEFAULT_CATEGORY = "기타"
_DEFAULT_PIE_COLOR = "#3B82F6"
_DEFAULT_BUDGET_TOTAL = 1_000_000
_CATTX_LIMIT = 20
_RECENT_LIMIT = 10


def _use_http() -> bool:
    return settings.FINANCIAL_CLIENT.strip().lower() == "http"


def _parse_dt(value: str) -> datetime:
    """계정계 ISO8601(Z 포함) 문자열 파싱."""
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


async def _fetch_user_ledger(session: AsyncSession, user_id: UUID) -> list[dict]:
    """user 의 매핑 계좌 원장을 병합해 최신순으로 반환(계좌 간 병합 재정렬)."""
    account_ids = await get_external_account_ids(session, user_id)
    client = get_financial_client()
    raw: list[dict] = []
    for account_id in account_ids:
        raw.extend(await client.get_ledger(account_id))
    raw.sort(key=lambda e: e["created_at"], reverse=True)
    return raw


async def get_balance_view(
    user_id: UUID, session: AsyncSession | None = None
) -> BalanceData:
    """사용자 자산 현황 view model.

    http 모드: 계정계 잔액을 계좌별로 합산. mock 모드: 픽스처.
    """
    if not _use_http():
        return BALANCE_FIXTURE
    session = cast(
        AsyncSession, session
    )  # http 경로는 라우터 Depends 로 항상 세션 존재

    client = get_financial_client()

    # 매핑 행이 있으면 계정계가 부여한 은행명/계좌번호를 그대로 쓴다(정보계 balance
    # 응답엔 없음). 없으면 데모 fallback id 로 기본값 enrich.
    rows = await get_mapped_accounts(session, user_id)
    if rows:
        sources = [(r.external_account_id, r.bank_name, r.account_number) for r in rows]
    else:
        sources = [
            (aid, None, None)
            for aid in await get_external_account_ids(session, user_id)
        ]

    summaries: list[AccountSummary] = []
    for idx, (account_id, bank_name, account_number) in enumerate(sources):
        if account_id is None:  # 매핑 무결성상 없어야 하나 타입 안전 차원
            continue
        balance = await client.get_balance(account_id)
        if balance is None:  # 404 — 계좌 없음, 건너뜀
            continue
        tail = (account_number or str(balance["account_id"]))[-4:]
        summaries.append(
            AccountSummary(
                id=idx + 1,
                bank=bank_name or _DEFAULT_BANK,
                alias=_DEFAULT_ALIAS,
                tail=tail,
                balance=balance["balance"],
                color=_ACCOUNT_COLORS[idx % len(_ACCOUNT_COLORS)],
            )
        )

    return BalanceData(
        total=sum(a.balance for a in summaries),
        accounts=summaries,
    )


def _ledger_to_recent(entry: dict) -> RecentTxItem:
    """계정계 원장 항목 -> 계좌 상세 최근거래 항목(부호 있는 금액).

    B2 는 A2(거래내역)와 달리 amount 에 부호를 준다(출금 음수).
    """
    created = _parse_dt(entry["created_at"])
    is_credit = entry["entry_type"] == "CREDIT"
    amount = entry["amount"] if is_credit else -entry["amount"]
    return RecentTxItem(
        name="입금" if is_credit else "출금",
        emoji="💰" if is_credit else "💸",
        date=created.strftime("%m.%d %H:%M"),
        amount=amount,
        type="in" if is_credit else "out",
    )


async def get_account_detail_view(
    user_id: UUID, account_id: str, session: AsyncSession | None = None
) -> AccountDetailData:
    """계좌 상세 view model (B2).

    http 모드: account_id 가 user 소유(매핑) 계좌인지 확인 후 잔액+최근거래 조회.
    소유가 아니거나 계좌 없음이면 404. mock 모드: 픽스처.
    """
    if not _use_http():
        return ACCOUNT_DETAIL_FIXTURE
    session = cast(AsyncSession, session)

    rows = await get_mapped_accounts(session, user_id)
    row = next((r for r in rows if r.external_account_id == account_id), None)
    if row is None:  # user 스코프 밖 계좌 조회 차단
        raise HTTPException(status_code=404, detail="계좌를 찾을 수 없습니다.")

    client = get_financial_client()
    balance = await client.get_balance(account_id)
    if balance is None:  # 계정계 404
        raise HTTPException(status_code=404, detail="계좌를 찾을 수 없습니다.")

    ledger = await client.get_ledger(account_id, limit=_RECENT_LIMIT)
    tail = (row.account_number or str(balance["account_id"]))[-4:]
    return AccountDetailData(
        account=AccountDetailInfo(
            bank=row.bank_name or _DEFAULT_BANK,
            alias=_DEFAULT_ALIAS,
            tail=tail,
            balance=balance["balance"],
        ),
        recent=[_ledger_to_recent(e) for e in ledger[:_RECENT_LIMIT]],
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
        category="수입" if is_credit else _DEFAULT_CATEGORY,
    )


async def get_transactions_view(
    user_id: UUID, month: str | None = None, session: AsyncSession | None = None
) -> TransactionsData:
    """거래 내역 view model.

    http 모드: 계정계 원장을 계좌별로 조회해 최신순 병합. month(예: '2025-06')
    가 주어지면 해당 월만 필터. mock 모드: 픽스처.
    """
    if not _use_http():
        if month is None:
            return TRANSACTIONS_FIXTURE
        items = [tx for tx in TRANSACTIONS_FIXTURE.items if tx.month == month]
        return TransactionsData(months=TRANSACTIONS_FIXTURE.months, items=items)
    session = cast(AsyncSession, session)

    raw = await _fetch_user_ledger(session, user_id)
    items = [_ledger_to_item(e, i + 1) for i, e in enumerate(raw)]
    months = sorted({it.month for it in items}, reverse=True)
    if month is not None:
        items = [it for it in items if it.month == month]
    return TransactionsData(months=months, items=items)


def _spending_from_ledger(entries: list[dict]) -> SpendingData:
    """원장 -> 소비 분석(제한 집계).

    카테고리/상호가 없어 출금(DEBIT)을 단일 '기타' 버킷으로 묶고, 월별 실제
    출금 합계만 진짜 값으로 채운다. 카테고리 증감(bar)은 데이터가 없어 빈 리스트.
    """
    out = [e for e in entries if e["entry_type"] == "DEBIT"]
    total_out = sum(e["amount"] for e in out)

    monthly_map: dict[str, int] = {}
    for e in out:
        key = _parse_dt(e["created_at"]).strftime("%Y-%m")
        monthly_map[key] = monthly_map.get(key, 0) + e["amount"]
    monthly = [
        MonthlySpendDatum(month=f"{int(k[5:7])}월", amount=v)
        for k, v in sorted(monthly_map.items())
    ]

    pie = (
        [
            PieDatum(
                name=_DEFAULT_CATEGORY,
                value=100,
                color=_DEFAULT_PIE_COLOR,
                amount=total_out,
            )
        ]
        if total_out > 0
        else []
    )
    cat_tx = (
        {
            _DEFAULT_CATEGORY: [
                CatTxDatum(
                    name="출금",
                    date=_parse_dt(e["created_at"]).strftime("%m.%d"),
                    amount=e["amount"],
                )
                for e in out[:_CATTX_LIMIT]
            ]
        }
        if out
        else {}
    )
    return SpendingData(pie=pie, bar=[], monthly=monthly, catTx=cat_tx)


def _budget_from_ledger(entries: list[dict]) -> BudgetData:
    """원장 -> 예산 현황.

    예산 목표/구독 정보는 원장에 없어 기본값으로 대체: '기타' 카테고리 하나에
    실제 출금 합계를 used 로, 기본 예산을 total 로 두고 구독은 빈 리스트.
    """
    used = sum(e["amount"] for e in entries if e["entry_type"] == "DEBIT")
    return BudgetData(
        budgetItems=[
            BudgetItem(cat=_DEFAULT_CATEGORY, used=used, total=_DEFAULT_BUDGET_TOTAL)
        ],
        subItems=[],
    )


async def get_spending_view(
    user_id: UUID, session: AsyncSession | None = None
) -> SpendingData:
    """소비 분석 view model. http 모드: 원장 집계(기본값 대체). mock 모드: 픽스처."""
    if not _use_http():
        return SPENDING_FIXTURE
    session = cast(AsyncSession, session)
    entries = await _fetch_user_ledger(session, user_id)
    return _spending_from_ledger(entries)


async def get_budget_view(
    user_id: UUID, session: AsyncSession | None = None
) -> BudgetData:
    """예산 현황 view model. http 모드: 원장 집계(기본값 대체). mock 모드: 픽스처."""
    if not _use_http():
        return BUDGET_FIXTURE
    session = cast(AsyncSession, session)
    entries = await _fetch_user_ledger(session, user_id)
    return _budget_from_ledger(entries)


def _mask_card_number(num: str) -> str:
    """카드번호 가운데 그룹 마스킹(PII). '5412 3456 7890 1234' -> '5412 **** **** 1234'.

    앞 4자리(BIN 일부)와 뒤 4자리만 노출하고 중간 그룹은 자릿수만큼 * 로 가린다.
    공백 구분 그룹이 2개 이하면 마스킹할 중간이 없어 원본을 그대로 둔다.
    """
    groups = num.split()
    if len(groups) <= 2:
        return num
    masked_mid = ["*" * len(g) for g in groups[1:-1]]
    return " ".join([groups[0], *masked_mid, groups[-1]])


async def get_cards_view(
    user_id: UUID, session: AsyncSession | None = None
) -> CardsData:
    """카드 관리 view model. mock 모드: 픽스처(카드번호 마스킹, B6 PII 규칙).

    http 모드: 계정계에 "계좌별 카드 목록" 엔드포인트가 없어 열거 불가 → 빈 목록
    (카드 미프로비저닝 상태를 정직하게 반영). TODO: 카드 프로비저닝(계좌처럼 card_id
    매핑 저장) 도입 시 실제 카드 반환.
    """
    _ = user_id, session
    if not _use_http():
        return CardsData(
            cards=[
                CreditCard(
                    name=c.name,
                    num=_mask_card_number(c.num),
                    exp=c.exp,
                    bg=c.bg,
                )
                for c in CARDS_FIXTURE.cards
            ]
        )
    return CardsData(cards=[])
