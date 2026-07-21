"""Account <-> mock-financial-service(계정계) 매핑 조회.

User(JWT UUID) 를 계정계 원장의 external_account_id 로 이어준다(결정 A).
Account.external_account_id 컬럼이 1차 저장소이며 회원가입 프로비저닝이 채운다.
(D5: FINANCIAL_DEMO_ACCOUNT_ID fallback 은 제거 — 매핑이 없으면 빈 목록.)
"""

from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.account import Account


async def get_external_account_ids(session: AsyncSession, user_id: UUID) -> list[str]:
    """user 의 계정계 account_id 목록. 매핑이 없으면 빈 목록."""
    stmt = (
        select(Account.external_account_id)
        .where(
            Account.user_id == user_id,
            Account.external_account_id.is_not(None),
        )
        .order_by(Account.account_number)
    )
    result = await session.execute(stmt)
    return [row for row in result.scalars().all() if row]


async def get_mapped_accounts(session: AsyncSession, user_id: UUID) -> list[Account]:
    """user 의 매핑된 Account 행 목록(bank_name/account_number 포함)."""
    stmt = (
        select(Account)
        .where(
            Account.user_id == user_id,
            Account.external_account_id.is_not(None),
        )
        .order_by(Account.account_number)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_primary_mapped_account(
    session: AsyncSession, user_id: UUID
) -> Account | None:
    """user 의 첫 매핑 계좌(송금 sender). 없으면 None."""
    accounts = await get_mapped_accounts(session, user_id)
    return accounts[0] if accounts else None


async def get_owned_accounts_by_ids(
    session: AsyncSession, user_id: UUID, account_ids: list[UUID]
) -> list[Account]:
    """user 소유이면서 요청한 로컬 Account.id 목록에 속하는 계좌만 반환한다.

    소유권 검증용. 다른 사용자 계좌 id 를 섞어 보내도 결과에 포함되지 않으므로,
    호출부는 반환 개수와 요청 개수를 비교해 접근 거부를 판단할 수 있다.
    """
    if not account_ids:
        return []
    stmt = (
        select(Account)
        .where(
            Account.user_id == user_id,
            Account.id.in_(account_ids),
        )
        .order_by(Account.account_number)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_owned_account(
    session: AsyncSession, user_id: UUID, account_id: UUID
) -> Account | None:
    """user 소유의 단일 계좌를 조회한다(설정 변경 대상 검증용). 없으면 None."""
    stmt = select(Account).where(
        Account.user_id == user_id,
        Account.id == account_id,
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_account_by_id(session: AsyncSession, account_id: UUID) -> Account | None:
    """소유권 필터 없이 계좌를 조회한다.

    **타인송금 수취인 검증 전용.** 수취 계좌는 다른 사용자 소유이므로 user_id 필터를
    걸 수 없다. 호출부는 반드시 참조 출처(본인의 실행 이력 또는 검증된 후보)를 먼저
    확인해 임의 계좌 열거에 쓰이지 않게 해야 한다.
    """
    stmt = select(Account).where(Account.id == account_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_account_by_number(
    session: AsyncSession, account_number: str
) -> Account | None:
    """계좌번호로 계좌를 조회한다(신규 수취 계좌 검증 전용, D5).

    Frontend 검증 API 에서만 사용한다. 검증 성공 시 원문 대신
    recipient_candidate_id 를 발급하므로 원문이 Agent 로 전달되지 않는다.
    TODO(계정계): 계좌번호 기반 조회 API 가 생기면 계정계 검증으로 위임한다.
    """
    stmt = select(Account).where(Account.account_number == account_number)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_default_account(session: AsyncSession, user_id: UUID) -> Account | None:
    """user 의 현재 기본 출금 계좌. 아직 없으면 None."""
    stmt = select(Account).where(
        Account.user_id == user_id,
        Account.is_default.is_(True),
    )
    result = await session.execute(stmt)
    return result.scalars().first()


async def set_default_account(
    session: AsyncSession, user_id: UUID, account: Account
) -> Account:
    """기존 기본계좌를 해제하고 대상 계좌를 기본으로 설정한다(한 트랜잭션).

    사용자당 기본계좌가 동시에 하나만 존재하도록 보장한다(계약 20.5). 해제를 먼저
    수행해야 부분 유니크 인덱스(ux_accounts_user_default) 와 충돌하지 않는다.
    """
    await session.execute(
        update(Account)
        .where(Account.user_id == user_id, Account.is_default.is_(True))
        .values(is_default=False)
    )
    account.is_default = True
    await session.commit()
    await session.refresh(account)
    return account


async def set_account_alias(
    session: AsyncSession, account: Account, alias: str
) -> Account:
    """계좌 별칭을 변경한다(로컬이 정본, D4)."""
    account.alias = alias
    await session.commit()
    await session.refresh(account)
    return account


async def alias_exists_for_user(
    session: AsyncSession, user_id: UUID, alias: str, exclude_account_id: UUID
) -> bool:
    """같은 사용자의 다른 계좌가 이미 같은 별칭을 쓰는지(중복 정책)."""
    stmt = select(Account.id).where(
        Account.user_id == user_id,
        Account.alias == alias,
        Account.id != exclude_account_id,
    )
    result = await session.execute(stmt)
    return result.first() is not None


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
    bank_name: str | None = None,
    balance: int = 0,
    currency: str = "KRW",
) -> Account:
    """계정계 계좌를 로컬 Account 행으로 매핑 저장(프로비저닝)."""
    account = Account(
        user_id=user_id,
        account_number=account_number,
        bank_name=bank_name,
        balance=balance,
        currency=currency,
        external_account_id=external_account_id,
    )
    session.add(account)
    await session.commit()
    await session.refresh(account)
    return account
