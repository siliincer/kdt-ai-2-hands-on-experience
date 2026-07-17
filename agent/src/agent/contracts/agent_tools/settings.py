"""기본 출금 계좌·계좌 별칭 변경 Agent Tool API 계약."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

NonEmptyString = Annotated[str, Field(min_length=1)]
SettingPrepareOutcome = Literal[
    "ready_for_confirmation",
    "unchanged",
    "correction_required",
    "blocked",
]
SettingExecuteOutcome = Literal["completed", "correction_required", "blocked"]


class SettingToolContract(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _has_value(*values: object | None) -> bool:
    return any(value is not None for value in values)


class SettingBlockedView(SettingToolContract):
    title: NonEmptyString
    description: str | None = None


class DefaultAccountView(SettingToolContract):
    account_id: NonEmptyString
    bank_name: NonEmptyString
    account_alias: str | None = None
    masked_account_number: NonEmptyString


class AliasTargetAccountView(SettingToolContract):
    account_id: NonEmptyString
    bank_name: NonEmptyString
    masked_account_number: NonEmptyString


class DefaultAccountCorrectionView(SettingToolContract):
    allowed_change_targets: Annotated[
        list[Literal["account"]],
        Field(min_length=1, max_length=1),
    ]


class AccountAliasCorrectionView(SettingToolContract):
    allowed_change_targets: Annotated[
        list[Literal["account", "alias"]],
        Field(min_length=1, max_length=1),
    ]


class DefaultAccountPrepareRequest(SettingToolContract):
    account_id: NonEmptyString


class DefaultAccountConfirmationView(SettingToolContract):
    current_default_account: DefaultAccountView | None = None
    new_default_account: DefaultAccountView
    expires_at: datetime


class DefaultAccountPrepareResult(SettingToolContract):
    outcome: SettingPrepareOutcome
    reason: NonEmptyString | None = None
    confirmation_id: NonEmptyString | None = None
    confirmation_view: DefaultAccountConfirmationView | None = None
    account_id: NonEmptyString | None = None
    correction_view: DefaultAccountCorrectionView | None = None
    blocked_view: SettingBlockedView | None = None

    @model_validator(mode="after")
    def validate_outcome_shape(self) -> Self:
        if self.outcome == "ready_for_confirmation":
            if self.confirmation_id is None or self.confirmation_view is None:
                raise ValueError("승인 준비 응답에는 Confirmation이 필요합니다.")
            if _has_value(
                self.reason,
                self.account_id,
                self.correction_view,
                self.blocked_view,
            ):
                raise ValueError("승인 준비 응답에 다른 Outcome 필드가 포함됐습니다.")
        elif self.outcome == "unchanged":
            if self.account_id is None:
                raise ValueError("변경 없음 응답에는 account_id가 필요합니다.")
            if _has_value(
                self.reason,
                self.confirmation_id,
                self.confirmation_view,
                self.correction_view,
                self.blocked_view,
            ):
                raise ValueError("변경 없음 응답에 다른 Outcome 필드가 포함됐습니다.")
        elif self.outcome == "correction_required":
            if self.reason is None or self.correction_view is None:
                raise ValueError("수정 응답에는 reason과 correction_view가 필요합니다.")
            if _has_value(
                self.confirmation_id,
                self.confirmation_view,
                self.account_id,
                self.blocked_view,
            ):
                raise ValueError("수정 응답에 다른 Outcome 필드가 포함됐습니다.")
        else:
            if self.reason is None or self.blocked_view is None:
                raise ValueError("차단 응답에는 reason과 blocked_view가 필요합니다.")
            if _has_value(
                self.confirmation_id,
                self.confirmation_view,
                self.account_id,
                self.correction_view,
            ):
                raise ValueError("차단 응답에 다른 Outcome 필드가 포함됐습니다.")
        return self


class ConfirmationExecuteRequest(SettingToolContract):
    confirmation_id: NonEmptyString


class DefaultAccountExecuteResult(SettingToolContract):
    outcome: SettingExecuteOutcome
    reason: NonEmptyString | None = None
    account_id: NonEmptyString | None = None
    completed_at: datetime | None = None
    correction_view: DefaultAccountCorrectionView | None = None
    blocked_view: SettingBlockedView | None = None

    @model_validator(mode="after")
    def validate_outcome_shape(self) -> Self:
        if self.outcome == "completed":
            if self.account_id is None or self.completed_at is None:
                raise ValueError("완료 응답에는 계좌 ID와 완료시각이 필요합니다.")
            if _has_value(self.reason, self.correction_view, self.blocked_view):
                raise ValueError("완료 응답에 다른 Outcome 필드가 포함됐습니다.")
        elif self.outcome == "correction_required":
            if self.reason is None or self.correction_view is None:
                raise ValueError("수정 응답에는 reason과 correction_view가 필요합니다.")
            if _has_value(self.account_id, self.completed_at, self.blocked_view):
                raise ValueError("수정 응답에 다른 Outcome 필드가 포함됐습니다.")
        else:
            if self.reason is None or self.blocked_view is None:
                raise ValueError("차단 응답에는 reason과 blocked_view가 필요합니다.")
            if _has_value(self.account_id, self.completed_at, self.correction_view):
                raise ValueError("차단 응답에 다른 Outcome 필드가 포함됐습니다.")
        return self


class AccountAliasPrepareRequest(SettingToolContract):
    account_id: NonEmptyString
    alias: NonEmptyString


class AccountAliasConfirmationView(SettingToolContract):
    account: AliasTargetAccountView
    alias: NonEmptyString
    expires_at: datetime


class AccountAliasPrepareResult(SettingToolContract):
    outcome: SettingPrepareOutcome
    reason: NonEmptyString | None = None
    confirmation_id: NonEmptyString | None = None
    confirmation_view: AccountAliasConfirmationView | None = None
    account_id: NonEmptyString | None = None
    alias: NonEmptyString | None = None
    correction_view: AccountAliasCorrectionView | None = None
    blocked_view: SettingBlockedView | None = None

    @model_validator(mode="after")
    def validate_outcome_shape(self) -> Self:
        if self.outcome == "ready_for_confirmation":
            if self.confirmation_id is None or self.confirmation_view is None:
                raise ValueError("승인 준비 응답에는 Confirmation이 필요합니다.")
            if _has_value(
                self.reason,
                self.account_id,
                self.alias,
                self.correction_view,
                self.blocked_view,
            ):
                raise ValueError("승인 준비 응답에 다른 Outcome 필드가 포함됐습니다.")
        elif self.outcome == "unchanged":
            if self.account_id is None or self.alias is None:
                raise ValueError("변경 없음 응답에는 계좌 ID와 별칭이 필요합니다.")
            if _has_value(
                self.reason,
                self.confirmation_id,
                self.confirmation_view,
                self.correction_view,
                self.blocked_view,
            ):
                raise ValueError("변경 없음 응답에 다른 Outcome 필드가 포함됐습니다.")
        elif self.outcome == "correction_required":
            if self.reason is None or self.correction_view is None:
                raise ValueError("수정 응답에는 reason과 correction_view가 필요합니다.")
            if _has_value(
                self.confirmation_id,
                self.confirmation_view,
                self.account_id,
                self.alias,
                self.blocked_view,
            ):
                raise ValueError("수정 응답에 다른 Outcome 필드가 포함됐습니다.")
        else:
            if self.reason is None or self.blocked_view is None:
                raise ValueError("차단 응답에는 reason과 blocked_view가 필요합니다.")
            if _has_value(
                self.confirmation_id,
                self.confirmation_view,
                self.account_id,
                self.alias,
                self.correction_view,
            ):
                raise ValueError("차단 응답에 다른 Outcome 필드가 포함됐습니다.")
        return self


class AccountAliasExecuteResult(SettingToolContract):
    outcome: SettingExecuteOutcome
    reason: NonEmptyString | None = None
    account_id: NonEmptyString | None = None
    alias: NonEmptyString | None = None
    completed_at: datetime | None = None
    correction_view: AccountAliasCorrectionView | None = None
    blocked_view: SettingBlockedView | None = None

    @model_validator(mode="after")
    def validate_outcome_shape(self) -> Self:
        if self.outcome == "completed":
            if (
                self.account_id is None
                or self.alias is None
                or self.completed_at is None
            ):
                raise ValueError("완료 응답에는 계좌 ID, 별칭과 완료시각이 필요합니다.")
            if _has_value(self.reason, self.correction_view, self.blocked_view):
                raise ValueError("완료 응답에 다른 Outcome 필드가 포함됐습니다.")
        elif self.outcome == "correction_required":
            if self.reason is None or self.correction_view is None:
                raise ValueError("수정 응답에는 reason과 correction_view가 필요합니다.")
            if _has_value(
                self.account_id,
                self.alias,
                self.completed_at,
                self.blocked_view,
            ):
                raise ValueError("수정 응답에 다른 Outcome 필드가 포함됐습니다.")
        else:
            if self.reason is None or self.blocked_view is None:
                raise ValueError("차단 응답에는 reason과 blocked_view가 필요합니다.")
            if _has_value(
                self.account_id,
                self.alias,
                self.completed_at,
                self.correction_view,
            ):
                raise ValueError("차단 응답에 다른 Outcome 필드가 포함됐습니다.")
        return self
