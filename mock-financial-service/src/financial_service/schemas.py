"""Pydantic schemas for request/response."""

from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator

# ── Error schema (fixed contract) ────────────────────────────────────────────


class ErrorResponse(BaseModel):
    error_code: str
    message: str


# ── Account ───────────────────────────────────────────────────────────────────


class AccountCreate(BaseModel):
    owner: str = Field(..., min_length=1, max_length=255)
    initial_balance: int = Field(default=0, ge=0)


class AccountResponse(BaseModel):
    account_id: str
    owner: str
    bank_name: str
    account_number: str
    balance: int
    currency: str
    created_at: datetime

    model_config = {"from_attributes": True}


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
    sender_account_id: str
    receiver_account_id: str
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
    amount: int
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Snapshot / 정보계 ──────────────────────────────────────────────────────────


class SnapshotResponse(BaseModel):
    account_id: str
    cached_balance: int
    last_entry_rowid: int | None
    sum_credit: int
    sum_debit: int
    refreshed_at: datetime

    model_config = {"from_attributes": True}


class ReconciliationResponse(BaseModel):
    account_id: str
    cached_balance: int
    expected_balance: int
    sum_credit: int
    sum_debit: int
    last_entry_rowid: int | None
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
