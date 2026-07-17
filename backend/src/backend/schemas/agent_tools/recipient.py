"""수취인 자동 확정 DTO (#5, 계약 13장).

이 API 는 후보 목록·수취인 이름을 Agent 에 반환하지 않는다. 이름 힌트가 기존 타인송금
거래에서 정확히 하나의 수취인으로 확정되는지(resolved)만 판단한다. 확정 실패 시 Agent 는
`UI-RECIPIENT-SELECT` Webhook 만 보낸다(선택 UI 데이터는 Backend·Frontend 가 구성).
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class ResolveOutcome:
    """`data.outcome` 값(계약 13.3·13.4)."""

    RESOLVED = "resolved"
    SELECTION_REQUIRED = "selection_required"


class SelectionReason:
    """`data.selection_reason` 값(계약 13.4)."""

    MULTIPLE_MATCHES = "multiple_matches"
    NO_MATCH = "no_match"


class RecipientResolveRequest(BaseModel):
    # 공백 제거 후 1자 이상, 최대 100자(계약 13.2).
    recipient_name_hint: str = Field(max_length=100)

    @field_validator("recipient_name_hint")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("recipient_name_hint 는 공백일 수 없습니다.")
        return value


class RecipientResolveData(BaseModel):
    outcome: str
    # resolved 일 때만: 수취인 참조 ID(수취인의 로컬 Account.id, D5).
    to_recipient_id: str | None = None
    # selection_required 일 때만.
    selection_reason: str | None = None
