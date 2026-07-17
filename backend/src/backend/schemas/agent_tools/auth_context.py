"""추가 인증 Context 생성 DTO (#7, 계약 15장).

송금 유형·사용자·송금 조건은 Confirmation 에 이미 고정되어 있으므로 요청에는
confirmation_id 만 담는다(`purpose`·`user_id`·송금 업무 필드를 중복 전달하지 않음).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class AuthOutcome:
    """`data.outcome` 값."""

    AUTHENTICATION_REQUIRED = "authentication_required"


class AuthStatus:
    """Backend 가 Agent 재개 시 전달하는 `auth_status` Enum(계약 15.4)."""

    VERIFIED = "verified"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class AuthContextCreateRequest(BaseModel):
    confirmation_id: str


class AuthRequestView(BaseModel):
    """Agent 가 인증 요청 Webhook 으로 전달할 표시 정보. 인증 원문은 포함하지 않는다."""

    title: str
    description: str | None = None
    available_methods: list[str]
    expires_at: datetime


class AuthContextCreateData(BaseModel):
    outcome: str
    auth_context_id: str
    auth_request_view: AuthRequestView
