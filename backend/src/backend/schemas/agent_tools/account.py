"""계좌 목록(API-ACCOUNT-LIST)·잔액 조회(API-BALANCE-QUERY) DTO.

Agent 에 노출하는 account_id 는 Backend 로컬 Account.id(UUID) 다. Backend 가 내부에서
계정계 external_account_id 로 매핑하므로 Agent 는 계정계 식별자를 알지 못한다.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator

# 계좌 해소 결과(계약 9.2). resolved=단일 확정, selection_required=사용자 선택 필요,
# no_accounts=후보 없음. Agent 는 이 값으로 워크플로우를 분기한다.
AccountResolutionOutcome = Literal["resolved", "selection_required", "no_accounts"]


class AccountCapability(str, Enum):
    """계좌 조회 목적. 호출 Step 에 고정되는 요청값(계약 9.2)."""

    INQUIRY = "inquiry"
    WITHDRAW = "withdraw"
    DEPOSIT = "deposit"
    SETTINGS = "settings"


class AccountListItem(BaseModel):
    account_id: str
    bank_name: str | None
    account_alias: str | None
    account_type: str | None
    masked_account_number: str
    currency: str
    is_default: bool
    status: str  # "active" | "inactive"


class AccountListData(BaseModel):
    accounts: list[AccountListItem]
    # resolve_selection 요청 시 Backend 가 채운다(계약 9.2). 미요청이면 None/빈 목록.
    account_resolution_outcome: AccountResolutionOutcome | None = None
    account_ids: list[str] = Field(default_factory=list)


class BalanceQueryRequest(BaseModel):
    account_ids: list[str] = Field(min_length=1, max_length=20)

    @field_validator("account_ids")
    @classmethod
    def _no_duplicates(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("account_ids 에 중복된 계좌가 있습니다.")
        return value


class BalanceResultItem(BaseModel):
    account_id: str
    bank_name: str | None
    account_alias: str | None
    masked_account_number: str
    balance: int
    available_balance: int
    currency: str
    as_of: datetime


class BalanceQueryData(BaseModel):
    balance_results: list[BalanceResultItem]
