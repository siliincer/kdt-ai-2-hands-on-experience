# api 성공 / 실패에 따른 응답을 만드는 유틸함수
# util/build_response.py
from typing import Any

from ..schemas.response import CommonResponse


def success_response(message: str | None, data: Any = None) -> CommonResponse:
    """성공 응답을 생성하는 유틸리티 함수"""
    return CommonResponse(success=True, message=message, data=data)


def failure_response(message: str | None, data: Any = None) -> CommonResponse:
    """실패 응답을 생성하는 유틸리티 함수 (예외 처리 등에서 사용)"""
    return CommonResponse(success=False, message=message, data=data)
