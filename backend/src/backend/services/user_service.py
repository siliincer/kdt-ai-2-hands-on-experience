from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.security import get_password_hash, verify_password
from ..models.user import User
from ..repository.user_repository import create_user, get_user_by_email


async def signup_user(
    session: AsyncSession, email: str, password: str, name: str | None = None
) -> User:
    existing_user = await get_user_by_email(session, email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="이미 사용 중인 이메일입니다.",
        )

    password_hash = get_password_hash(password)

    user = await create_user(
        session, email=email, password_hash=password_hash, name=name
    )
    return user


async def login_user(session: AsyncSession, email: str, password: str) -> User:
    user = await get_user_by_email(session, email)
    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="이메일 또는 비밀번호가 잘못되었습니다.",
        )
    return user
