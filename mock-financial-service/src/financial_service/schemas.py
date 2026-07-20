"""Pydantic schemas for request/response."""

from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator

from .models import BANK_CATALOG, BANK_NAME

# ── Error schema (fixed contract) ────────────────────────────────────────────


class ErrorResponse(BaseModel):
    error_code: str
    message: str


# ── Account ───────────────────────────────────────────────────────────────────


class AccountCreate(BaseModel):
    owner: str = Field(..., min_length=1, max_length=255)
    initial_balance: int = Field(default=0, ge=0)
    # 생략 시 KDT은행(기본값) — 하위호환 보장; BANK_CATALOG 외 값은 422 반환
    bank_name: str = Field(default=BANK_NAME, min_length=1, max_length=50)

    @field_validator("bank_name")
    @classmethod
    def bank_must_be_in_catalog(cls, v: str) -> str:
        if v not in BANK_CATALOG:
            raise ValueError(
                f"Unsupported bank: {v}. Supported banks: {sorted(BANK_CATALOG)}"
            )
        return v


class AccountResponse(BaseModel):
    account_id: str
    owner: str
    bank_name: str
    account_number: str
    alias: str | None = None
    balance: int
    currency: str
    created_at: datetime

    model_config = {"from_attributes": True}


class AccountAliasUpdate(BaseModel):
    alias: str = Field(..., min_length=1, max_length=100)


# ── Balance ───────────────────────────────────────────────────────────────────


class BalanceResponse(BaseModel):
    account_id: str
    balance: int
    currency: str


# ── Ledger / Transaction history ──────────────────────────────────────────────


class LedgerEntryResponse(BaseModel):
    entry_id: str
    transaction_id: str
    entry_type: str  # DEBIT / CREDIT
    amount: int
    running_balance: int
    # TRANSFER(일반 송금) / CARD_SETTLEMENT(카드 정산) — settlement_type 파생값.
    transaction_type: str
    # 같은 거래의 상대 계좌. CARD_SETTLEMENT는 카드 정산용 내부 계좌라 owner 표기가
    # 사람 이름이 아닐 수 있음 — 그대로 노출(별도 마스킹 없음, 계정계 계약 밖).
    counterparty_account_id: str | None = None
    counterparty_account_number: str | None = None
    counterparty_owner: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AuditLogResponse(BaseModel):
    audit_log_id: str
    transaction_id: str | None
    actor: str
    action: str
    reason: str
    status: str
    timestamp: datetime

    model_config = {"from_attributes": True}


# ── Transfer ──────────────────────────────────────────────────────────────────


class TransferRequest(BaseModel):
    sender_account_number: str
    receiver_bank_name: str
    receiver_account_number: str
    amount: int = Field(..., gt=0)

    @field_validator("amount")
    @classmethod
    def amount_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("amount must be positive")
        return v


class TransferResponse(BaseModel):
    transfer_id: str
    from_account: str
    to_account: str
    sender_bank_name: str
    sender_account_number: str
    receiver_bank_name: str
    receiver_account_number: str
    amount: int
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class DailyTransferredResponse(BaseModel):
    account_id: str
    business_date: date
    total_sent: int  # sender 기준 성공한 일반 송금(TRANSFER) 합계. 카드 정산 제외.


# ── Balance reconciliation / 정보계 ────────────────────────────────────────────


class ReconciliationResponse(BaseModel):
    account_id: str
    cached_balance: int
    expected_balance: int
    sum_credit: int
    sum_debit: int
    drift_detected: bool
    delta: int
    reconciled_at: str


# ── Card ──────────────────────────────────────────────────────────────────────


class CardCreate(BaseModel):
    account_id: str
    limit: int = Field(..., gt=0)
    currency: str = Field(default="KRW", min_length=3, max_length=3)


class CardResponse(BaseModel):
    card_id: str
    account_id: str
    limit: int
    currency: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Card Charge ───────────────────────────────────────────────────────────────


class CardChargeRequest(BaseModel):
    amount: int = Field(..., gt=0)


class CardChargeResponse(BaseModel):
    card_ledger_entry_id: str
    card_id: str
    amount: int
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Card Settlement ───────────────────────────────────────────────────────────


class CardSettleResponse(BaseModel):
    transaction_id: str
    card_id: str
    settled_amount: int
    settlement_watermark_rowid: int
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Card Ledger Entry (analytics) ─────────────────────────────────────────────


class CardLedgerEntryResponse(BaseModel):
    card_ledger_entry_id: str
    card_id: str
    amount: int
    # 소비 분석용 — 실제 은행엔 없는 필드. mock 데이터만 채움, 라이브 결제는 둘 다 null.
    merchant_name: str | None = None
    category: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Daily Closing (EOD batch) ──────────────────────────────────────────────────


class DailyClosingSnapshotResponse(BaseModel):
    account_id: str
    business_date: date
    closing_balance: int
    sum_credit: int
    sum_debit: int
    last_entry_rowid: int | None
    created_at: datetime

    model_config = {"from_attributes": True}


class DailyClosingBatchResponse(BaseModel):
    business_date: date
    accounts_closed: int
    snapshots: list[DailyClosingSnapshotResponse]
