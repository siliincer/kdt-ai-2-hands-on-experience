from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.postgres import Base

if TYPE_CHECKING:
    from .chat_session import ChatSession

# 상태는 PG enum 대신 문자열로 관리한다(값이 단순하고 마이그레이션 마찰을 줄임 —
# recipient_candidates 와 같은 방침).
PENDING_INPUT_STATUS_ACTIVE = "active"
PENDING_INPUT_STATUS_CONSUMED = "consumed"
PENDING_INPUT_STATUS_CANCELLED = "cancelled"


# 일반 사용자 입력 대기(UI-HITL 계약 1.3·1.5). Agent 가 need_input 을 보내면 Backend 가
# input_request_id 에 execution_context_id·agent_thread_id·ui_contract_id 와 대기 상태를
# 연결해 이 행으로 보관한다. Frontend 가 POST /agent/input 으로 제출하면 Backend 가 이
# 행을 검증·소비한 뒤 Agent 를 재개한다.
# - 한 chat_session(=agent_thread)에는 동시에 하나의 활성 대기만 허용한다(계약 1.3).
#   새 대기를 등록할 때 기존 활성 행은 cancelled 로 무효화한다.
# - 인증 원문·전체 계좌번호 등 민감정보는 저장하지 않는다(계약 7). 여기엔 참조 ID와
#   UI 계약 식별자만 둔다.
# - 작동 검증 후 Redis TTL 로 이전 가능하게 설계(C4·C5).
class PendingInput(Base):
    __tablename__ = "pending_inputs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Agent 가 발급한 입력 요청 식별자. Resume 매칭 키다(계약 1.3).
    input_request_id: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True
    )
    chat_session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chat_sessions.id"), nullable=False, index=True
    )
    # Backend 가 발급한 실행 Context. mock/초기 경로에서 아직 없을 수 있어 nullable.
    execution_context_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("execution_contexts.id"),
        nullable=True,
        index=True,
    )
    # Agent 내부 LangGraph Checkpointer 키.
    agent_thread_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # UI 계약 식별자(예: UI-BALANCE-ACCOUNT-SELECTION)와 UI 타입(예: account_card_list).
    ui_contract_id: Mapped[str] = mapped_column(String(100), nullable=False)
    ui_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # active(대기) | consumed(제출됨) | cancelled(새 대기로 대체·취소)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=PENDING_INPUT_STATUS_ACTIVE, index=True
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # 서비스는 컬럼만 사용 → 자동 로딩 안 함(R4).
    chat_session: Mapped["ChatSession"] = relationship(lazy="raise")
