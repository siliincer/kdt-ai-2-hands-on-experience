from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum as PyEnum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.postgres import Base

if TYPE_CHECKING:
    from .chat_session import ChatSession
    from .user import User


class ExecutionContextStatus(PyEnum):
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"


# Agent Tool API(/api/v1/agent-tools/*)의 사용자·실행 권한 Context.
# Agent 는 요청 본문에 user_id 를 보내지 않고, Backend 가 X-Execution-Context-Id 로
# 이 행을 찾아 사용자·스코프·세션 연결을 결정한다(계약 5장). 발급 정본은 Backend.
class ExecutionContext(Base):
    __tablename__ = "execution_contexts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    chat_session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chat_sessions.id"), nullable=False, index=True
    )
    # LangGraph Checkpointer 키. Agent 실행 시작 응답으로 돌아오므로 발급 시점엔 없다.
    agent_thread_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    # 예: ["account:read", "transfer:request"]. 엔드포인트별 필요 스코프 검증에 사용.
    scopes: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    status: Mapped[ExecutionContextStatus] = mapped_column(
        Enum(ExecutionContextStatus, name="execution_context_status"),
        nullable=False,
        default=ExecutionContextStatus.ACTIVE,
    )
    # 기간 합계 등에서 종료일 경계를 변환할 때 기준이 되는 타임존(계약 12장).
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Asia/Seoul")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # 서비스는 user_id/chat_session_id 컬럼만 쓰므로 관계를 자동 로딩하지 않는다(R4).
    # 매 Agent Tool 호출의 resolve_context 에서 불필요한 +2 SELECT 를 제거하고, 실수로
    # 접근하면 명시적으로 에러난다(silent N+1 방지). 필요 시 selectinload 로 명시.
    user: Mapped["User"] = relationship(lazy="raise")
    chat_session: Mapped["ChatSession"] = relationship(lazy="raise")
