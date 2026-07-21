"""Agent Tool API 전용 응답 빌더.

성공 envelope 은 다른 API와 동일한 `{success, message, data}`(계약 5.1)이므로
`success_response` 를 재사용한다. 오류 envelope 만 `error.{category, code, message,
retryable, details}` 로 달라(D2) 별도 빌더를 둔다.
"""

from __future__ import annotations

from typing import Any

from fastapi.responses import JSONResponse

from ..schemas.response import CommonResponse
from .build_response import success_response

# 성공 응답은 공통 envelope 과 동일하므로 이름만 노출(호출부 가독성용).
agent_success_response = success_response


def agent_error_response(
    status_code: int,
    category: str,
    code: str,
    message: str,
    retryable: bool = False,
    details: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """Agent Tool API 오류 envelope(JSONResponse) 을 생성한다.

    사용자에게 공개 가능한 문장만 포함한다. DB 오류, Stack Trace, 내부 URL, Secret 은
    담지 않는다(계약 6장). headers 는 `Retry-After` 처럼 계약이 요구하는 응답 헤더용.
    """
    error: dict[str, Any] = {
        "category": category,
        "code": code,
        "message": message,
        "retryable": retryable,
    }
    if details is not None:
        error["details"] = details
    return JSONResponse(
        status_code=status_code,
        content={"success": False, "error": error},
        headers=headers,
    )


__all__ = ["agent_success_response", "agent_error_response", "CommonResponse"]
