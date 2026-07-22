from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.postgres import Base

if TYPE_CHECKING:
    from .user import User


# 금융 감사 로그의 정본(계약 25장). append-only 이며 업무 API 에서 수정·삭제하지 않는다.
# Agent 트레이스(audit_logs, execution_id FK)와는 다른 책임이다:
#   audit_logs           = Agent 실행 Step/Route 관찰 기록 (정본 주체 Agent)
#   financial_audit_logs = 금융 조회·승인·인증·정책 판정·실행 사실 (정본 주체 Backend)
# 민감정보(전체 계좌번호·잔액 원문·토큰·인증 원문)는 기록하지 않는다(계약 25.3).
class FinancialAuditLog(Base):
    __tablename__ = "financial_audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    # confirmation_created / setting_change_completed 등(계약 25.2)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # Agent 합성 request_id("req_start_"+32자hex+":"+step_id)가 64자를 넘는 사례가
    # 있어(예: "prepare_account_alias_change", "prepare_external_transfer") 여유있게 둔다.
    request_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # 감사 기록은 Context/Confirmation 정리와 무관하게 남아야 하므로 FK 를 걸지 않는다.
    execution_context_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    chat_session_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    agent_thread_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    # agent_service | user | backend
    actor_type: Mapped[str] = mapped_column(String(32), nullable=False)
    operation: Mapped[str] = mapped_column(String(64), nullable=False)
    contract_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    confirmation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    auth_context_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    transaction_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # completed / blocked / correction_required / failed 등 업무 결과
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    policy_codes: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)

    # append-only insert 전용 — user 관계는 자동 로딩하지 않는다(R4, refresh +1 제거).
    user: Mapped["User"] = relationship(lazy="raise")

    def __repr__(self) -> str:  # pragma: no cover - 디버깅 편의용
        return f"<FinancialAuditLog {self.event_type} {self.operation} outcome={self.outcome}>"


# 계약 25.2 주요 Event Type 상수.
EVENT_FINANCIAL_DATA_ACCESSED = "financial_data_accessed"
EVENT_CONFIRMATION_CREATED = "confirmation_created"
EVENT_CONFIRMATION_APPROVED = "confirmation_approved"
EVENT_CONFIRMATION_INVALIDATED = "confirmation_invalidated"
EVENT_CONFIRMATION_CANCELLED = "confirmation_cancelled"
EVENT_AUTH_CONTEXT_CREATED = "auth_context_created"
EVENT_AUTHENTICATION_VERIFIED = "authentication_verified"
EVENT_AUTHENTICATION_FAILED = "authentication_failed"
EVENT_FINANCIAL_EXECUTION_COMPLETED = "financial_execution_completed"
EVENT_FINANCIAL_EXECUTION_BLOCKED = "financial_execution_blocked"
EVENT_SETTING_CHANGE_COMPLETED = "setting_change_completed"
EVENT_IDEMPOTENCY_CONFLICT = "idempotency_conflict"
