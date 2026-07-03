from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.postgres import get_db
from ..schemas.response import CommonResponse
from ..schemas.user import UserLoginRequest, UserReadSchema, UserSignupRequest
from ..services.user_service import UserService
from ..utils.build_response import success_response

user_router = APIRouter(prefix="/users", tags=["Users"])


@user_router.post("/signup", response_model=CommonResponse[UserReadSchema])
async def signup(
    payload: UserSignupRequest,
    session: AsyncSession = Depends(get_db),
):
    service = UserService(session)
    user = await service.signup(payload.email, payload.password, payload.name)
    return success_response(
        message="회원가입이 완료되었습니다.",
        data=UserReadSchema.model_validate(user),
    )


@user_router.post("/login", response_model=CommonResponse[UserReadSchema])
async def login(
    payload: UserLoginRequest,
    session: AsyncSession = Depends(get_db),
):
    service = UserService(session)
    user = await service.login(payload.email, payload.password)
    return success_response(
        message="로그인에 성공했습니다.",
        data=UserReadSchema.model_validate(user),
    )
