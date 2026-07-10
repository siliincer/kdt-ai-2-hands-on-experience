from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import noload

from ..models.user import User


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    stmt = select(User).where(User.email == email)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def create_user(
    session: AsyncSession, email: str, password_hash: str, name: str | None = None
) -> User:
    user = User(email=email, password_hash=password_hash, name=name)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def get_user_by_id(session: AsyncSession, user_id: str) -> User | None:
    # 인증(get_current_user) 전용 조회. User 의 accounts/approvals/chat_sessions 는
    # lazy="selectin" 이라 기본적으로 매 요청마다 추가 SELECT 가 나간다.
    # 인증에는 신원(id/role)만 필요하므로 noload 로 관계 로딩을 끈다.
    stmt = (
        select(User)
        .where(User.id == user_id)
        .options(
            noload(User.accounts),
            noload(User.approvals),
            noload(User.chat_sessions),
        )
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()
