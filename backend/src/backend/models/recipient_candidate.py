from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.postgres import Base

if TYPE_CHECKING:
    from .user import User

# 상태는 PG enum 대신 문자열로 관리한다(값이 단순하고 마이그레이션 마찰을 줄임).
CANDIDATE_STATUS_VERIFIED = "verified"
CANDIDATE_STATUS_CONSUMED = "consumed"


# 신규 수취 계좌 검증 결과의 단기 참조(D5, 계약 부록 29.2).
# Frontend 가 은행+계좌번호 원문을 Backend 검증 API 에 제출하면, Backend 가 검증 후
# 이 행을 만들어 `recipient_candidate_id` 만 돌려준다. 이후 Agent·Prepare 는 이 참조만
# 사용하므로 전체 계좌번호가 Agent State 를 통과하지 않는다.
# 사용자·Chat Session·만료시간에 바인딩되며, 작동 검증 후 Redis TTL 로 이전 가능(D5).
class RecipientCandidate(Base):
    __tablename__ = "recipient_candidates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    chat_session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chat_sessions.id"), nullable=False, index=True
    )
    # 검증된 수취 계좌의 로컬 Account.id(다른 사용자 소유). 원문 계좌번호는 저장하지
    # 않고 이 참조 + 마스킹본만 둔다(D5).
    recipient_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False
    )
    # 예금주 실명 스냅샷(승인 화면에서는 마스킹해 노출).
    resolved_name: Mapped[str] = mapped_column(String(100), nullable=False)
    bank_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    masked_account_number: Mapped[str] = mapped_column(String(30), nullable=False)
    # verified(사용 가능) | consumed(Prepare 에서 소비됨)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=CANDIDATE_STATUS_VERIFIED)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # 서비스는 user_id 컬럼만 사용 → 자동 로딩 안 함(R4).
    user: Mapped["User"] = relationship(lazy="raise")
