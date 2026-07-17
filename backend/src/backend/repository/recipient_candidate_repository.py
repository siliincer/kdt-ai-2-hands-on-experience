"""신규 수취 계좌 후보(recipient_candidate) DB 접근(D5)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.recipient_candidate import (
    CANDIDATE_STATUS_CONSUMED,
    RecipientCandidate,
)


async def create_recipient_candidate(
    session: AsyncSession,
    user_id: UUID,
    chat_session_id: UUID,
    recipient_account_id: UUID,
    resolved_name: str,
    bank_name: str | None,
    masked_account_number: str,
    expires_at: datetime,
) -> RecipientCandidate:
    """검증에 성공한 신규 수취 계좌 후보를 저장한다."""
    candidate = RecipientCandidate(
        user_id=user_id,
        chat_session_id=chat_session_id,
        recipient_account_id=recipient_account_id,
        resolved_name=resolved_name,
        bank_name=bank_name,
        masked_account_number=masked_account_number,
        expires_at=expires_at,
    )
    session.add(candidate)
    await session.commit()
    await session.refresh(candidate)
    return candidate


async def get_recipient_candidate_by_id(
    session: AsyncSession, candidate_id: UUID
) -> RecipientCandidate | None:
    """id 로 후보를 조회한다(없으면 None). 소유권 검증은 서비스가 담당한다."""
    stmt = select(RecipientCandidate).where(RecipientCandidate.id == candidate_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def mark_candidate_consumed(
    session: AsyncSession, candidate: RecipientCandidate
) -> RecipientCandidate:
    """Prepare 가 후보를 소비하면 재사용할 수 없게 처리한다."""
    candidate.status = CANDIDATE_STATUS_CONSUMED
    await session.commit()
    await session.refresh(candidate)
    return candidate
