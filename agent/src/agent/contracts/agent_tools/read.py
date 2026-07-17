"""조회 계열 Agent Tool API 요청·응답 계약."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

NonEmptyString = Annotated[str, Field(min_length=1)]
AccountIdList = Annotated[list[NonEmptyString], Field(min_length=1, max_length=20)]
AccountCapability = Literal["inquiry", "withdraw", "deposit", "settings"]
AccountResolutionOutcome = Literal["resolved", "selection_required", "no_accounts"]
TransactionType = Literal[
    "deposit",
    "withdrawal",
    "transfer",
    "card_payment",
    "atm_withdrawal",
    "fee",
    "interest",
]
SummaryType = Literal["spending", "income"]
RecipientResolutionOutcome = Literal["resolved", "selection_required"]
RecipientSelectionReason = Literal["multiple_matches", "no_match"]


class ReadToolContract(BaseModel):
    """조회 Tool 계약의 공통 엄격 모델."""

    model_config = ConfigDict(extra="forbid")


def _ensure_unique(values: list[str], *, field_name: str) -> list[str]:
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name}에는 중복 값을 사용할 수 없습니다.")
    return values


class AccountSummary(ReadToolContract):
    account_id: NonEmptyString
    bank_name: NonEmptyString
    account_alias: str | None = None
    account_type: NonEmptyString
    masked_account_number: NonEmptyString
    currency: NonEmptyString
    is_default: bool
    status: NonEmptyString


class AccountListRequest(ReadToolContract):
    account_hint: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    account_capability: AccountCapability | None = None
    resolve_selection: bool = False
    all_accounts_requested: bool = False
    exclude_account_ids: Annotated[list[NonEmptyString], Field(max_length=20)] = Field(
        default_factory=list
    )
    limit: int = Field(default=20, ge=1, le=100)

    @field_validator("exclude_account_ids")
    @classmethod
    def validate_excluded_accounts(cls, value: list[str]) -> list[str]:
        return _ensure_unique(value, field_name="exclude_account_ids")

    @model_validator(mode="after")
    def validate_resolution_options(self) -> Self:
        if self.all_accounts_requested and not self.resolve_selection:
            raise ValueError(
                "all_accounts_requested는 resolve_selection=true에서만 사용합니다."
            )
        return self


class AccountListResult(ReadToolContract):
    accounts: list[AccountSummary] = Field(default_factory=list)
    account_resolution_outcome: AccountResolutionOutcome | None = None
    account_ids: list[NonEmptyString] = Field(default_factory=list)

    @field_validator("account_ids")
    @classmethod
    def validate_account_ids(cls, value: list[str]) -> list[str]:
        return _ensure_unique(value, field_name="account_ids")

    @model_validator(mode="after")
    def validate_resolution_shape(self) -> Self:
        if self.account_resolution_outcome == "resolved" and not self.account_ids:
            raise ValueError("resolved 응답에는 account_ids가 필요합니다.")
        if self.account_resolution_outcome in {"selection_required", "no_accounts"}:
            if self.account_ids:
                raise ValueError(
                    f"{self.account_resolution_outcome} 응답의 "
                    "account_ids는 비어야 합니다."
                )
        if self.account_resolution_outcome == "no_accounts" and self.accounts:
            raise ValueError("no_accounts 응답의 accounts는 비어야 합니다.")
        return self


class BalanceQueryRequest(ReadToolContract):
    account_ids: AccountIdList

    @field_validator("account_ids")
    @classmethod
    def validate_account_ids(cls, value: list[str]) -> list[str]:
        return _ensure_unique(value, field_name="account_ids")


class BalanceResult(ReadToolContract):
    account_id: NonEmptyString
    bank_name: NonEmptyString
    account_alias: str | None = None
    masked_account_number: NonEmptyString
    balance: int
    available_balance: int
    currency: NonEmptyString
    as_of: datetime


class BalanceQueryResult(ReadToolContract):
    balance_results: list[BalanceResult] = Field(default_factory=list)


class TransactionQueryRequest(ReadToolContract):
    account_ids: AccountIdList
    start_date: date
    end_date: date
    keyword: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    transaction_type: TransactionType | None = None
    limit: int = Field(default=10, ge=1, le=100)

    @field_validator("account_ids")
    @classmethod
    def validate_account_ids(cls, value: list[str]) -> list[str]:
        return _ensure_unique(value, field_name="account_ids")

    @model_validator(mode="after")
    def validate_period(self) -> Self:
        if self.end_date < self.start_date:
            raise ValueError("end_date는 start_date보다 빠를 수 없습니다.")
        return self


class TransactionItem(ReadToolContract):
    transaction_id: NonEmptyString
    account_id: NonEmptyString
    account_alias: str | None = None
    occurred_at: datetime
    transaction_type: TransactionType
    amount: int
    currency: NonEmptyString
    transaction_title: NonEmptyString
    category: str | None = None


class TransactionQueryResult(ReadToolContract):
    transaction_results: list[TransactionItem] = Field(default_factory=list)
    transaction_query_id: NonEmptyString
    next_cursor: str | None = None


class TransactionSummaryRequest(ReadToolContract):
    account_ids: AccountIdList
    start_date: date
    end_date: date
    summary_type: SummaryType
    keyword: Annotated[str, Field(min_length=1, max_length=100)] | None = None

    @field_validator("account_ids")
    @classmethod
    def validate_account_ids(cls, value: list[str]) -> list[str]:
        return _ensure_unique(value, field_name="account_ids")

    @model_validator(mode="after")
    def validate_period(self) -> Self:
        if self.end_date < self.start_date:
            raise ValueError("end_date는 start_date보다 빠를 수 없습니다.")
        return self


class TransactionSummary(ReadToolContract):
    summary_type: SummaryType
    total_amount: int
    transaction_count: int = Field(ge=0)
    currency: NonEmptyString
    start_date: date
    end_date: date

    @model_validator(mode="after")
    def validate_period(self) -> Self:
        if self.end_date < self.start_date:
            raise ValueError("end_date는 start_date보다 빠를 수 없습니다.")
        return self


class TransactionSummaryResult(ReadToolContract):
    summary_result: TransactionSummary


class RecipientResolveRequest(ReadToolContract):
    recipient_name_hint: Annotated[str, Field(min_length=1, max_length=100)]


class RecipientResolveResult(ReadToolContract):
    outcome: RecipientResolutionOutcome
    to_recipient_id: NonEmptyString | None = None
    selection_reason: RecipientSelectionReason | None = None

    @model_validator(mode="after")
    def validate_outcome_shape(self) -> Self:
        if self.outcome == "resolved":
            if self.to_recipient_id is None or self.selection_reason is not None:
                raise ValueError(
                    "resolved 응답에는 to_recipient_id만 포함해야 합니다."
                )
        elif self.to_recipient_id is not None or self.selection_reason is None:
            raise ValueError(
                "selection_required 응답에는 selection_reason만 포함해야 합니다."
            )
        return self
