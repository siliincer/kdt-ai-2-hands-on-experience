"""요청/응답 스키마 (시트 API Spec 탭 계약)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class TransferRequest(BaseModel):
    """POST /api/transactions/transfer-external 요청.

    시트 API Spec 대비 user_id가 추가되어 있다 (원장이 user_id 키 구조).
    """

    user_id: str
    from_account_id: str
    to_recipient_id: str
    amount: int = Field(gt=0, description="송금 금액(원). 0보다 커야 한다")
    memo: str | None = None


class TransferResponse(BaseModel):
    transaction_id: str
    status: str


class AuditLogRequest(BaseModel):
    event_type: str
    workflow_id: str | None = None
    tool_id: str | None = None
    result: dict | None = None


class AuditLogResponse(BaseModel):
    log_id: str
