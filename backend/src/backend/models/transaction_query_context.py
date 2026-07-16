from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.postgres import Base

if TYPE_CHECKING:
    from .user import User


# 거래내역 첫 페이지 조회(API-TRANSACTION-QUERY) 시 Backend 가 저장하는 Query Context.
# Agent 는 첫 페이지만 받고, 이후 페이지는 Frontend 가 transaction_query_id + cursor 로
# 별도 API 를 호출한다(계약 11.2). 그 재조회에 필요한 조건을 여기 고정해 둔다.
class TransactionQueryContext(Base):
    __tablename__ = "transaction_query_contexts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    # 조회 대상 로컬 Account.id 목록(문자열 배열).
    account_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    keyword: Mapped[str | None] = mapped_column(String(100), nullable=True)
    transaction_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    page_size: Mapped[int] = mapped_column(Integer, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship(lazy="selectin")
