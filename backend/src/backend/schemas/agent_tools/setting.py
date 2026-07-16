"""기본 출금 계좌·계좌 별칭 변경 DTO (#11~#14).

Prepare 는 승인 대상을 Confirmation 에 고정하고, Execute 는 confirmation_id 만 받는다.
설정 변경은 사용자 승인은 받지만 추가 인증은 요구하지 않는다(계약 19.3).

업무 판정(`unchanged`/`correction_required`)은 오류가 아니라 200 + success=true +
data.outcome 으로 반환한다(D2'). 응답은 outcome 별 필드만 노출하도록 라우터에서
response_model_exclude_none=True 를 사용한다.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class SettingOutcome:
    """설정 변경 API 의 `data.outcome` 값(계약 19·21장)."""

    READY_FOR_CONFIRMATION = "ready_for_confirmation"
    UNCHANGED = "unchanged"
    CORRECTION_REQUIRED = "correction_required"
    COMPLETED = "completed"


class SettingReason:
    """`data.reason` 업무 사유 코드(계약 6.2·19.5·21.6)."""

    ACCOUNT_NOT_ELIGIBLE = "account_not_eligible"
    ALIAS_NOT_ALLOWED = "alias_not_allowed"


# ── 요청 ─────────────────────────────────────────────────────────────────────


class DefaultAccountPrepareRequest(BaseModel):
    account_id: str
    # 현재 기본 계좌는 Backend 가 확인하므로 Agent 가 전달하지 않는다(계약 19.2).


class AccountAliasPrepareRequest(BaseModel):
    account_id: str
    alias: str = Field(min_length=1)


class ExecuteByConfirmationRequest(BaseModel):
    """#12·#14 공용. Confirmation 에 고정된 값을 다시 보내지 않는다."""

    confirmation_id: str


# ── 승인 화면(confirmation_view) 구성요소 ────────────────────────────────────


class AccountRef(BaseModel):
    """기본계좌 변경 화면의 계좌 표시 정보."""

    account_id: str
    bank_name: str | None
    account_alias: str | None
    masked_account_number: str


class AliasAccountRef(BaseModel):
    """별칭 변경 화면의 계좌 표시 정보.

    계약 21.4: 변경 대상 계좌를 식별하기 위한 마스킹 정보만 담는다.
    기존 별칭(current_alias)·account_label 은 포함하지 않는다.
    """

    account_id: str
    bank_name: str | None
    masked_account_number: str


class DefaultAccountConfirmationView(BaseModel):
    # 사용자에게 기본계좌가 아직 없으면 None.
    current_default_account: AccountRef | None
    new_default_account: AccountRef
    expires_at: datetime


class AccountAliasConfirmationView(BaseModel):
    account: AliasAccountRef
    alias: str
    expires_at: datetime


class CorrectionView(BaseModel):
    title: str | None = None
    # Agent 는 reason 으로 추측하지 않고 이 목록만 수정 UI 로 제공한다(계약 14.5).
    allowed_change_targets: list[str]


# ── 응답 data ────────────────────────────────────────────────────────────────
# TODO: 정책 차단 조건(금융거래 제한 등)을 도입하면 blocked/blocked_view 를 추가한다.
# 현재 샌드박스에는 설정 변경을 차단할 정책 상태가 없어 blocked 를 반환하지 않는다.


class DefaultAccountPrepareData(BaseModel):
    outcome: str
    confirmation_id: str | None = None
    confirmation_view: DefaultAccountConfirmationView | None = None
    reason: str | None = None
    correction_view: CorrectionView | None = None
    account_id: str | None = None  # unchanged 일 때 대상 계좌


class AccountAliasPrepareData(BaseModel):
    outcome: str
    confirmation_id: str | None = None
    confirmation_view: AccountAliasConfirmationView | None = None
    reason: str | None = None
    correction_view: CorrectionView | None = None
    account_id: str | None = None  # unchanged 일 때
    alias: str | None = None  # unchanged 일 때 정규화된 별칭


class DefaultAccountExecuteData(BaseModel):
    outcome: str
    account_id: str | None = None  # 실제 반영된 최종 계좌
    completed_at: datetime | None = None
    reason: str | None = None
    correction_view: CorrectionView | None = None


class AccountAliasExecuteData(BaseModel):
    outcome: str
    account_id: str | None = None
    alias: str | None = None
    completed_at: datetime | None = None
    reason: str | None = None
    correction_view: CorrectionView | None = None
