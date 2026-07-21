"""송금·추가 인증 Agent Tool API 요청·응답 계약."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Self, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

NonEmptyString = Annotated[str, Field(min_length=1)]
Currency = Literal["KRW"]
PrepareOutcome = Literal[
    "ready_for_confirmation",
    "correction_required",
    "blocked",
]
ExecuteOutcome = Literal[
    "completed",
    "correction_required",
    "reauthentication_required",
    "blocked",
]
ExternalChangeTarget = Literal["from_account", "recipient", "amount"]
InternalChangeTarget = Literal["from_account", "to_account", "amount"]
AuthenticationMethod = Literal["biometric", "password"]


class TransferToolContract(BaseModel):
    model_config = ConfigDict(extra="forbid")


UniqueString = TypeVar("UniqueString", bound=str)


def _ensure_unique(
    values: list[UniqueString],
    *,
    field_name: str,
) -> list[UniqueString]:
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name}에는 중복 값을 사용할 수 없습니다.")
    return values


class MaskedAccountView(TransferToolContract):
    account_id: NonEmptyString
    bank_name: NonEmptyString
    account_alias: str | None = None
    masked_account_number: NonEmptyString


class RecipientView(TransferToolContract):
    name: NonEmptyString
    bank_name: NonEmptyString
    masked_account_number: NonEmptyString


class BlockedView(TransferToolContract):
    title: NonEmptyString
    description: str | None = None


class ExternalCorrectionView(TransferToolContract):
    title: str | None = None
    allowed_change_targets: Annotated[list[ExternalChangeTarget], Field(min_length=1, max_length=3)]

    @field_validator("allowed_change_targets")
    @classmethod
    def validate_targets(cls, value: list[ExternalChangeTarget]) -> list[ExternalChangeTarget]:
        return _ensure_unique(
            value,
            field_name="allowed_change_targets",
        )


class InternalCorrectionView(TransferToolContract):
    title: str | None = None
    allowed_change_targets: Annotated[list[InternalChangeTarget], Field(min_length=1, max_length=3)]

    @field_validator("allowed_change_targets")
    @classmethod
    def validate_targets(cls, value: list[InternalChangeTarget]) -> list[InternalChangeTarget]:
        return _ensure_unique(
            value,
            field_name="allowed_change_targets",
        )


class ExternalTransferPrepareRequest(TransferToolContract):
    from_account_id: NonEmptyString
    to_recipient_id: NonEmptyString | None = None
    to_recipient_candidate_id: NonEmptyString | None = None
    amount: int = Field(gt=0)
    currency: Currency = "KRW"

    @model_validator(mode="after")
    def validate_recipient_reference(self) -> Self:
        references = [self.to_recipient_id, self.to_recipient_candidate_id]
        if sum(reference is not None for reference in references) != 1:
            raise ValueError("to_recipient_id와 to_recipient_candidate_id 중 하나만 필요합니다.")
        return self


class ExternalConfirmationView(TransferToolContract):
    from_account: MaskedAccountView
    recipient: RecipientView
    amount: int = Field(gt=0)
    fee: int = Field(ge=0)
    total_debit: int = Field(gt=0)
    currency: Currency
    variant: str | None = None
    warning_codes: list[NonEmptyString] = Field(default_factory=list)
    expires_at: datetime


class ExternalTransferPrepareResult(TransferToolContract):
    outcome: PrepareOutcome
    reason: str | None = None
    confirmation_id: NonEmptyString | None = None
    confirmation_view: ExternalConfirmationView | None = None
    correction_view: ExternalCorrectionView | None = None
    blocked_view: BlockedView | None = None

    @model_validator(mode="after")
    def validate_outcome_shape(self) -> Self:
        if self.outcome == "ready_for_confirmation":
            if self.confirmation_id is None or self.confirmation_view is None:
                raise ValueError("승인 준비 응답에는 Confirmation이 필요합니다.")
            if any([self.reason, self.correction_view, self.blocked_view]):
                raise ValueError("승인 준비 응답에 다른 Outcome 필드가 포함됐습니다.")
        elif self.outcome == "correction_required":
            if self.reason is None or self.correction_view is None:
                raise ValueError("수정 응답에는 reason과 correction_view가 필요합니다.")
            if any([self.confirmation_id, self.confirmation_view, self.blocked_view]):
                raise ValueError("수정 응답에 다른 Outcome 필드가 포함됐습니다.")
        else:
            if self.reason is None or self.blocked_view is None:
                raise ValueError("차단 응답에는 reason과 blocked_view가 필요합니다.")
            if any(
                [
                    self.confirmation_id,
                    self.confirmation_view,
                    self.correction_view,
                ]
            ):
                raise ValueError("차단 응답에 다른 Outcome 필드가 포함됐습니다.")
        return self


class AuthContextCreateRequest(TransferToolContract):
    confirmation_id: NonEmptyString


class AuthRequestView(TransferToolContract):
    title: NonEmptyString
    description: str | None = None
    available_methods: Annotated[list[AuthenticationMethod], Field(min_length=1)]
    expires_at: datetime

    @field_validator("available_methods")
    @classmethod
    def validate_methods(cls, value: list[AuthenticationMethod]) -> list[AuthenticationMethod]:
        return _ensure_unique(value, field_name="available_methods")


class AuthContextCreateResult(TransferToolContract):
    outcome: Literal["authentication_required"]
    auth_context_id: NonEmptyString
    auth_request_view: AuthRequestView


class TransferExecuteRequest(TransferToolContract):
    confirmation_id: NonEmptyString
    auth_context_id: NonEmptyString


class ExternalTransferExecuteResult(TransferToolContract):
    outcome: ExecuteOutcome
    reason: str | None = None
    transaction_id: NonEmptyString | None = None
    completed_at: datetime | None = None
    correction_view: ExternalCorrectionView | None = None
    blocked_view: BlockedView | None = None

    @model_validator(mode="after")
    def validate_outcome_shape(self) -> Self:
        if self.outcome == "completed":
            if self.transaction_id is None or self.completed_at is None:
                raise ValueError("완료 응답에는 거래 ID와 완료시각이 필요합니다.")
            if any([self.reason, self.correction_view, self.blocked_view]):
                raise ValueError("완료 응답에 다른 Outcome 필드가 포함됐습니다.")
        elif self.outcome == "correction_required":
            if self.reason is None or self.correction_view is None:
                raise ValueError("수정 응답에는 reason과 correction_view가 필요합니다.")
            if any([self.transaction_id, self.completed_at, self.blocked_view]):
                raise ValueError("수정 응답에 다른 Outcome 필드가 포함됐습니다.")
        elif self.outcome == "reauthentication_required":
            if self.reason is None:
                raise ValueError("재인증 응답에는 reason이 필요합니다.")
            if any(
                [
                    self.transaction_id,
                    self.completed_at,
                    self.correction_view,
                    self.blocked_view,
                ]
            ):
                raise ValueError("재인증 응답에 다른 Outcome 필드가 포함됐습니다.")
        else:
            if self.reason is None or self.blocked_view is None:
                raise ValueError("차단 응답에는 reason과 blocked_view가 필요합니다.")
            if any([self.transaction_id, self.completed_at, self.correction_view]):
                raise ValueError("차단 응답에 다른 Outcome 필드가 포함됐습니다.")
        return self


class InternalTransferPrepareRequest(TransferToolContract):
    from_account_id: NonEmptyString
    to_account_id: NonEmptyString
    amount: int = Field(gt=0)
    currency: Currency = "KRW"

    @model_validator(mode="after")
    def validate_accounts(self) -> Self:
        if self.from_account_id == self.to_account_id:
            raise ValueError("출금 계좌와 입금 계좌는 달라야 합니다.")
        return self


class InternalConfirmationView(TransferToolContract):
    from_account: MaskedAccountView
    to_account: MaskedAccountView
    amount: int = Field(gt=0)
    fee: int = Field(ge=0)
    total_debit: int = Field(gt=0)
    currency: Currency
    expires_at: datetime


class InternalTransferPrepareResult(TransferToolContract):
    outcome: PrepareOutcome
    reason: str | None = None
    confirmation_id: NonEmptyString | None = None
    confirmation_view: InternalConfirmationView | None = None
    correction_view: InternalCorrectionView | None = None
    blocked_view: BlockedView | None = None

    @model_validator(mode="after")
    def validate_outcome_shape(self) -> Self:
        if self.outcome == "ready_for_confirmation":
            if self.confirmation_id is None or self.confirmation_view is None:
                raise ValueError("승인 준비 응답에는 Confirmation이 필요합니다.")
            if any([self.reason, self.correction_view, self.blocked_view]):
                raise ValueError("승인 준비 응답에 다른 Outcome 필드가 포함됐습니다.")
        elif self.outcome == "correction_required":
            if self.reason is None or self.correction_view is None:
                raise ValueError("수정 응답에는 reason과 correction_view가 필요합니다.")
            if any([self.confirmation_id, self.confirmation_view, self.blocked_view]):
                raise ValueError("수정 응답에 다른 Outcome 필드가 포함됐습니다.")
        else:
            if self.reason is None or self.blocked_view is None:
                raise ValueError("차단 응답에는 reason과 blocked_view가 필요합니다.")
            if any(
                [
                    self.confirmation_id,
                    self.confirmation_view,
                    self.correction_view,
                ]
            ):
                raise ValueError("차단 응답에 다른 Outcome 필드가 포함됐습니다.")
        return self


class InternalTransferExecuteResult(TransferToolContract):
    outcome: ExecuteOutcome
    reason: str | None = None
    transaction_id: NonEmptyString | None = None
    completed_at: datetime | None = None
    correction_view: InternalCorrectionView | None = None
    blocked_view: BlockedView | None = None

    @model_validator(mode="after")
    def validate_outcome_shape(self) -> Self:
        if self.outcome == "completed":
            if self.transaction_id is None or self.completed_at is None:
                raise ValueError("완료 응답에는 거래 ID와 완료시각이 필요합니다.")
            if any([self.reason, self.correction_view, self.blocked_view]):
                raise ValueError("완료 응답에 다른 Outcome 필드가 포함됐습니다.")
        elif self.outcome == "correction_required":
            if self.reason is None or self.correction_view is None:
                raise ValueError("수정 응답에는 reason과 correction_view가 필요합니다.")
            if any([self.transaction_id, self.completed_at, self.blocked_view]):
                raise ValueError("수정 응답에 다른 Outcome 필드가 포함됐습니다.")
        elif self.outcome == "reauthentication_required":
            if self.reason is None:
                raise ValueError("재인증 응답에는 reason이 필요합니다.")
            if any(
                [
                    self.transaction_id,
                    self.completed_at,
                    self.correction_view,
                    self.blocked_view,
                ]
            ):
                raise ValueError("재인증 응답에 다른 Outcome 필드가 포함됐습니다.")
        else:
            if self.reason is None or self.blocked_view is None:
                raise ValueError("차단 응답에는 reason과 blocked_view가 필요합니다.")
            if any([self.transaction_id, self.completed_at, self.correction_view]):
                raise ValueError("차단 응답에 다른 Outcome 필드가 포함됐습니다.")
        return self
