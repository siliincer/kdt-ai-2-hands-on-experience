# api/users.py
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from ..schemas.response import CommonResponse
from ..utils.build_response import success_response

user_router = APIRouter(prefix="/users", tags=["Users"])

# 테스트용 가짜 데이터 데이터베이스 역할
FAKE_USER_DB = {
    1: {"id": 1, "name": "김철수", "email": "chulsoo@example.com"},
    2: {"id": 2, "name": "이영희", "email": "younghee@example.com"},
}


# API 응답의 'data' 필드에 들어갈 스키마 정의
class UserReadSchema(BaseModel):
    id: int
    name: str
    email: str


# 1. 단일 데이터 조회 예시 (성공 및 실패 케이스 포함)
@user_router.get("/{user_id}", response_model=CommonResponse[UserReadSchema])
def get_user(user_id: int):
    user = FAKE_USER_DB.get(user_id)

    if not user:
        # 데이터를 찾지 못했을 때 HTTP 예외 발생
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="사용자를 찾을 수 없습니다."
        )

    # 성공 시 유틸리티 함수 사용
    return success_response(message="유저 정보를 가져오는데 성공했습니다.", data=user)


# 2. 리스트 데이터 조회 예시
@user_router.get("", response_model=CommonResponse[list[UserReadSchema]])
def get_all_users():
    users_list = list(FAKE_USER_DB.values())

    # 리스트 데이터 전달
    return success_response(
        message="모든 유저 정보를 가져오는데 성공했습니다.", data=users_list
    )
