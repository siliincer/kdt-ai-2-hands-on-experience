"""본인 계좌 간 이체 DTO (#9·#10, 계약 17~18장).

본인 이체도 사용자 승인 후 추가 인증을 **항상** 수행한다. 추가 인증 여부는 고정 정책이라
Prepare 응답에 `additional_auth_required` 같은 선택 플래그를 두지 않는다(계약 17.3).

Execute 는 `confirmation_id` + `auth_context_id` 만 받는다. Confirmation 에 고정된
출금·입금 계좌, 금액, 통화를 다시 전달하지 않는다(계약 18.2).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class TransferOutcome:
    """이체 API 의 `data.outcome` 값(계약 17·18장)."""

    READY_FOR_CONFIRMATION = "ready_for_confirmation"
    CORRECTION_REQUIRED = "correction_required"
    REAUTHENTICATION_REQUIRED = "reauthentication_required"
    BLOCKED = "blocked"
    COMPLETED = "completed"


class TransferReason:
    """`data.reason` 업무 사유 코드(계약 6.2)."""

    INSUFFICIENT_BALANCE = "insufficient_balance"
    LIMIT_EXCEEDED = "limit_exceeded"
    ACCOUNT_INACTIVE = "account_inactive"
    AUTH_CONTEXT_EXPIRED = "auth_context_expired"
    # 계약 6.2 예시 목록에는 없으나 본인이체 고유 판정이라 추가한다(계약 17.6:
    # "두 계좌가 서로 다른지" 검증). 사용자가 입금 계좌를 바꾸면 해결된다.
    SAME_ACCOUNT = "same_account"


class InternalTransferPrepareRequest(BaseModel):
    from_account_id: str
    to_account_id: str
    # 0보다 큰 정수. 실제 허용 금액(한도·잔액)은 Backend 가 판정한다(계약 17.2).
    amount: int = Field(gt=0)
    # 현재 범위에서는 KRW 만 지원한다. 다른 값은 계약에 정의되지 않은 조합(422).
    currency: Literal["KRW"]


class TransferExecuteRequest(BaseModel):
    """#10 (그리고 Stage 6 의 #8) 공용. 추가 인증이 필수라 두 참조를 모두 받는다."""

    confirmation_id: str
    auth_context_id: str


class TransferAccountRef(BaseModel):
    account_id: str
    account_alias: str | None
    bank_name: str | None
    masked_account_number: str


class InternalTransferConfirmationView(BaseModel):
    from_account: TransferAccountRef
    to_account: TransferAccountRef
    amount: int
    fee: int
    total_debit: int
    currency: str
    expires_at: datetime


class CorrectionView(BaseModel):
    title: str | None = None
    # 허용 값: from_account, to_account, amount (계약 17.4)
    allowed_change_targets: list[str]


class BlockedView(BaseModel):
    title: str
    description: str | None = None


class InternalTransferPrepareData(BaseModel):
    outcome: str
    confirmation_id: str | None = None
    confirmation_view: InternalTransferConfirmationView | None = None
    reason: str | None = None
    correction_view: CorrectionView | None = None
    blocked_view: BlockedView | None = None


class TransferExecuteData(BaseModel):
    outcome: str
    transaction_id: str | None = None
    completed_at: datetime | None = None
    reason: str | None = None
    correction_view: CorrectionView | None = None
    blocked_view: BlockedView | None = None
