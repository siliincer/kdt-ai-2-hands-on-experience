# custom exceptions
from fastapi import HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError, ResponseValidationError
from fastapi.responses import JSONResponse

from ..services.financial import (
    FinancialServiceError,
    financial_service_error_handler,
)
from ..utils.agent_response import agent_error_response
from .agent_exceptions import AgentToolError


def error_response(status_code: int, code: str, message: str, **extra):
    return JSONResponse(
        status_code=status_code,
        content={
            "success": False,
            "error": {
                "code": code,
                "message": message,
                **extra,
            },
        },
    )


async def value_error_handler(request: Request, exc: ValueError):
    return error_response(
        status_code=400,
        code="BAD_REQUEST",
        message=f"잘못된 입력값입니다. {str(exc)}",
    )


async def custom_runtime_error_handler(request: Request, exc: RuntimeError):
    return error_response(
        status_code=500,
        code="RUNTIME_ERROR",
        message="서버 오류가 발생했습니다.",
    )


async def http_exception_handler(request: Request, exc: HTTPException):
    return error_response(
        status_code=exc.status_code,
        code="HTTP_ERROR",
        message=str(exc.detail),
    )


async def request_validation_error_handler(
    request: Request, exc: RequestValidationError
):
    return error_response(
        status_code=422,
        code="REQUEST_VALIDATION_ERROR",
        message="요청 형식이 올바르지 않습니다.",
        details=jsonable_encoder(exc.errors()),
    )


async def response_validation_error_handler(
    request: Request, exc: ResponseValidationError
):
    return error_response(
        status_code=500,
        code="RESPONSE_VALIDATION_ERROR",
        message="서버 응답 형식이 API 스키마와 일치하지 않습니다.",
        details=jsonable_encoder(exc.errors()),
    )


async def agent_tool_error_handler(request: Request, exc: AgentToolError):
    """Agent Tool API 오류를 계약 정본 envelope(category/retryable 포함)으로 번역."""
    return agent_error_response(
        status_code=exc.status_code,
        category=exc.category,
        code=exc.code,
        message=exc.message,
        retryable=exc.retryable,
        details=exc.details,
        headers=exc.headers,
    )


# main.py에서 한번에 등록하기 위한 매핑 딕셔너리 생성
exception_handlers = {
    HTTPException: http_exception_handler,
    RequestValidationError: request_validation_error_handler,
    ResponseValidationError: response_validation_error_handler,
    ValueError: value_error_handler,
    RuntimeError: custom_runtime_error_handler,
    FinancialServiceError: financial_service_error_handler,
    AgentToolError: agent_tool_error_handler,
}
