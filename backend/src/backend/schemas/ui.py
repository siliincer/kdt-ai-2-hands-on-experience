"""UI Data API (BFF) 응답 스키마.

Agent 는 `component` SSE 시그널만 보내고(ADR-002), FE 가 이 엔드포인트로 카드 데이터를
조회한다. 현재는 목 픽스처, 향후 postgres/redis/mock-financial-service 조회로 교체.
스키마는 backend/docs/agent_ui_event_spec.md §4b 와 일치한다.
"""

from pydantic import BaseModel, Field


class AccountSummary(BaseModel):
    id: int
    bank: str
    alias: str
    tail: str
    balance: int
    color: str


class BalanceData(BaseModel):
    """GET /api/v1/ui/balance"""

    total: int = Field(description="총 자산(원)")
    accounts: list[AccountSummary]


# --- account_detail (계좌 상세, GET /api/v1/ui/account/{account_id}) ---


class RecentTxItem(BaseModel):
    name: str
    emoji: str
    date: str
    amount: int = Field(description="부호 있음(출금 음수) — A2 규칙과 다름")
    type: str = Field(description="'in' | 'out'")


class AccountDetailInfo(BaseModel):
    bank: str
    alias: str
    tail: str
    balance: int


class AccountDetailData(BaseModel):
    """GET /api/v1/ui/account/{account_id}"""

    account: AccountDetailInfo
    recent: list[RecentTxItem]


# --- spending (소비 분석, GET /api/v1/ui/spending) ---


class PieDatum(BaseModel):
    name: str
    value: int = Field(description="비중(%)")
    color: str
    amount: int


class ChangeItem(BaseModel):
    name: str
    amount: int


class BarCatDatum(BaseModel):
    name: str
    change: int = Field(description="전월 대비 증감률(%)")
    prev: int
    curr: int
    added: list[ChangeItem]
    removed: list[ChangeItem]


class MonthlySpendDatum(BaseModel):
    month: str
    amount: int


class CatTxDatum(BaseModel):
    name: str
    date: str
    amount: int


class SpendingData(BaseModel):
    """GET /api/v1/ui/spending"""

    pie: list[PieDatum]
    bar: list[BarCatDatum]
    monthly: list[MonthlySpendDatum]
    catTx: dict[str, list[CatTxDatum]]  # noqa: N815


# --- transactions (거래 내역, GET /api/v1/ui/transactions) ---
class TransactionItem(BaseModel):
    id: int
    name: str
    emoji: str
    date: str
    month: str
    day: int
    amount: int
    type: str = Field(description="'in' | 'out'")
    category: str


class TransactionsData(BaseModel):
    """GET /api/v1/ui/transactions"""

    months: list[str]
    items: list[TransactionItem]


# --- budget (예산 현황, GET /api/v1/ui/budget) ---


class BudgetItem(BaseModel):
    cat: str
    used: int
    total: int


class SubscriptionItem(BaseModel):
    name: str
    amount: int
    active: bool


class BudgetData(BaseModel):
    """GET /api/v1/ui/budget"""

    budgetItems: list[BudgetItem]  # noqa: N815
    subItems: list[SubscriptionItem]  # noqa: N815


# --- cards (카드 관리, GET /api/v1/ui/cards) ---


class CreditCard(BaseModel):
    name: str
    num: str
    exp: str
    bg: str


class CardsData(BaseModel):
    """GET /api/v1/ui/cards"""

    cards: list[CreditCard]
