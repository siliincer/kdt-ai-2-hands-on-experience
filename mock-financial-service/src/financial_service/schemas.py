"""Pydantic schemas for request/response."""
from datetime import datetime

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
    entry_type: str   # DEBIT / CREDIT
    amount: int
    running_balance: int
    created_at: datetime

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
