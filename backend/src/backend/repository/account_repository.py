"""Account <-> mock-financial-service(계정계) 매핑 조회.

User(JWT UUID) 를 계정계 원장의 external_account_id 로 이어준다(결정 A).
Phase 1: Account.external_account_id 컬럼이 1차 저장소이며,
매핑된 행이 없을 때 settings.FINANCIAL_DEMO_ACCOUNT_ID 로 데모 fallback 한다.
Phase 2 에서 회원가입 시 프로비저닝으로 이 컬럼을 채운다.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.load_environment_var import settings
from ..models.account import Account


async def get_external_account_ids(session: AsyncSession, user_id: UUID) -> list[str]:
    """user 의 계정계 account_id 목록. 없으면 데모 시드 fallback."""
    stmt = (
        select(Account.external_account_id)
        .where(
            Account.user_id == user_id,
            Account.external_account_id.is_not(None),
        )
        .order_by(Account.account_number)
    )
    result = await session.execute(stmt)
    ids = [row for row in result.scalars().all() if row]
    if ids:
        return ids

    demo = settings.FINANCIAL_DEMO_ACCOUNT_ID.strip()
    return [demo] if demo else []
