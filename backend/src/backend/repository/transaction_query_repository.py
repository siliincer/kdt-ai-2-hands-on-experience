"""거래내역 Query Context DB 접근.

첫 페이지 조회 시 재조회 조건을 저장한다(계약 11.2). 이후 페이지용 조회 API 는
Frontend 단계에서 추가한다(현재는 create 만 필요).
"""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ..models.transaction_query_context import TransactionQueryContext


async def create_transaction_query_context(
    session: AsyncSession,
    user_id: UUID,
    account_ids: list[str],
    start_date: date,
    end_date: date,
    keyword: str | None,
    transaction_type: str | None,
    page_size: int,
    expires_at: datetime,
) -> TransactionQueryContext:
    """거래내역 조회 조건을 고정 저장하고 생성된 Context 를 반환한다."""
    context = TransactionQueryContext(
        user_id=user_id,
        account_ids=account_ids,
        start_date=start_date,
        end_date=end_date,
        keyword=keyword,
        transaction_type=transaction_type,
        page_size=page_size,
        expires_at=expires_at,
    )
    session.add(context)
    await session.commit()
    await session.refresh(context)
    return context
