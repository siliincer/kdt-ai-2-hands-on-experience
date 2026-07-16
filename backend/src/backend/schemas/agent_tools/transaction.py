"""거래내역 조회(API-TRANSACTION-QUERY)·기간 합계(API-TRANSACTION-SUMMARY) DTO.

계정계 원장에는 기간·키워드·유형 필터와 title·category·상대방 필드가 없어(D4),
Backend 가 메모리에서 기간·유형 필터와 집계를 수행한다. title·category 는 미제공(None).
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator, model_validator


class TransactionType(str, Enum):
    """거래 유형. 계정계 entry_type 매핑: CREDIT=deposit, DEBIT=withdrawal."""

    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    TRANSFER = "transfer"


class SummaryType(str, Enum):
    """합계 유형."""

    SPENDING = "spending"
    INCOME = "income"


def _dedup(value: list[str]) -> list[str]:
    if len(set(value)) != len(value):
        raise ValueError("account_ids 에 중복된 계좌가 있습니다.")
    return value


class TransactionQueryRequest(BaseModel):
    account_ids: list[str] = Field(min_length=1, max_length=20)
    start_date: date
    end_date: date
    keyword: str | None = Field(default=None, max_length=100)
    transaction_type: TransactionType | None = None
    limit: int = Field(default=20, ge=1, le=100)

    _validate_ids = field_validator("account_ids")(_dedup)

    @model_validator(mode="after")
    def _check_period(self) -> "TransactionQueryRequest":
        if self.end_date < self.start_date:
            raise ValueError("end_date 는 start_date 이상이어야 합니다.")
        return self


class TransactionResultItem(BaseModel):
    transaction_id: str
    account_id: str
    account_alias: str | None
    occurred_at: datetime
    transaction_type: str
    amount: int
    currency: str
    transaction_title: str | None = None
    category: str | None = None


class TransactionQueryData(BaseModel):
    transaction_results: list[TransactionResultItem]
    transaction_query_id: str
    next_cursor: str | None


class TransactionSummaryRequest(BaseModel):
    account_ids: list[str] = Field(min_length=1, max_length=20)
    start_date: date
    end_date: date
    summary_type: SummaryType
    keyword: str | None = Field(default=None, max_length=100)

    _validate_ids = field_validator("account_ids")(_dedup)

    @model_validator(mode="after")
    def _check_period(self) -> "TransactionSummaryRequest":
        if self.end_date < self.start_date:
            raise ValueError("end_date 는 start_date 이상이어야 합니다.")
        return self


class TransactionSummaryResult(BaseModel):
    summary_type: str
    total_amount: int
    transaction_count: int
    currency: str
    start_date: date
    end_date: date


class TransactionSummaryData(BaseModel):
    summary_result: TransactionSummaryResult
