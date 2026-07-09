from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.postgres import get_db
from ..schemas.response import CommonResponse
from ..schemas.user import (
    LoginResponse,
    UserLoginRequest,
    UserReadSchema,
    UserSignupRequest,
)
from ..security.jwt import get_current_user
from ..services.user_service import login_user, signup_user
from ..utils.build_response import success_response

user_router = APIRouter(prefix="/users", tags=["Users"])


@user_router.post("/signup", response_model=CommonResponse[UserReadSchema])
async def signup(
    payload: UserSignupRequest,
    session: AsyncSession = Depends(get_db),
):
    user = await signup_user(session, payload.email, payload.password, payload.name)
    return success_response(
        message="회원가입이 완료되었습니다.",
        data=UserReadSchema.model_validate(user),
    )


@user_router.post("/login", response_model=CommonResponse[LoginResponse])
async def login(
    payload: UserLoginRequest,
    session: AsyncSession = Depends(get_db),
):
    user, access_token = await login_user(session, payload.email, payload.password)

    login_response = LoginResponse(
        access_token=access_token,
        token_type="bearer",
        user=UserReadSchema.model_validate(user),
    )

    return success_response(
        message="로그인에 성공했습니다.",
        data=login_response,
    )


@user_router.post("/logout", response_model=CommonResponse[dict])
async def logout(
    current_user=Depends(get_current_user),
):
    """로그아웃 엔드포인트 (프론트에서 토큰 삭제)"""
    return success_response(
        message=f"{current_user.email} 사용자가 로그아웃했습니다.",
        data={},
    )
