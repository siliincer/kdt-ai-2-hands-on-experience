# 공통 응답 형식 정의
# response.py
from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class CommonResponse(BaseModel, Generic[T]):
    success: bool  # 요청 성공 여부
    message: str | None  # 요청 처리 결과 메시지
    data: T | None  # 실제 반환될 데이터
