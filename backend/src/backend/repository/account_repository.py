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


async def has_mapped_account(session: AsyncSession, user_id: UUID) -> bool:
    """이미 계정계 매핑된 Account 가 있는지(프로비저닝 멱등성)."""
    stmt = select(Account.id).where(
        Account.user_id == user_id,
        Account.external_account_id.is_not(None),
    )
    result = await session.execute(stmt)
    return result.first() is not None


async def create_mapped_account(
    session: AsyncSession,
    user_id: UUID,
    external_account_id: str,
    account_number: str,
    balance: int = 0,
    currency: str = "KRW",
) -> Account:
    """계정계 계좌를 로컬 Account 행으로 매핑 저장(프로비저닝)."""
    account = Account(
        user_id=user_id,
        account_number=account_number,
        balance=balance,
        currency=currency,
        external_account_id=external_account_id,
    )
    session.add(account)
    await session.commit()
    await session.refresh(account)
    return account
