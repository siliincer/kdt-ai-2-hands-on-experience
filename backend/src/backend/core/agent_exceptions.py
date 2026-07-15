"""Agent Tool API(/api/v1/agent-tools/*) 전용 예외.

계약 정본은 `agent-tools-api-spec.md`. 오류 응답 envelope 은 다른 라우터의
`error_response` 와 달리 `error.{category, code, message, retryable, details}` 형태다
(D2 확정). 이 예외를 던지면 `agent_tool_error_handler` 가 해당 envelope 으로 번역한다.

`correction_required` / `blocked` / `unchanged` 같은 정상 업무 판정은 예외가 아니라
`200 + success=true + data.outcome` 으로 반환한다(D2'). 이 예외는 실행 Context·서비스
인증·요청 스키마·권한·기술 오류 등 계약된 업무 결과를 반환하지 못한 경우에만 쓴다.
"""

from __future__ import annotations

from typing import Any


class AgentErrorCategory:
    """`error.category` 값 모음(문자열 상수)."""

    REQUEST_ERROR = "request_error"
    AUTHENTICATION_ERROR = "authentication_error"
    AUTHORIZATION_ERROR = "authorization_error"
    STATE_ERROR = "state_error"
    TECHNICAL_ERROR = "technical_error"


class AgentToolError(Exception):
    """Agent Tool API 오류. `agent_tool_error_handler` 가 envelope 으로 변환한다."""

    def __init__(
        self,
        *,
        status_code: int,
        category: str,
        code: str,
        message: str,
        retryable: bool = False,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.category = category
        self.code = code
        self.message = message
        self.retryable = retryable
        self.details = details

    # ── 자주 쓰는 오류 팩토리 ────────────────────────────────────────────────

    @classmethod
    def invalid_service_token(cls) -> AgentToolError:
        return cls(
            status_code=401,
            category=AgentErrorCategory.AUTHENTICATION_ERROR,
            code="INVALID_SERVICE_TOKEN",
            message="Agent 서비스 인증에 실패했습니다.",
            retryable=False,
        )

    @classmethod
    def invalid_execution_context(cls) -> AgentToolError:
        return cls(
            status_code=401,
            category=AgentErrorCategory.AUTHENTICATION_ERROR,
            code="INVALID_EXECUTION_CONTEXT",
            message="유효하지 않은 실행 Context 입니다.",
            retryable=False,
        )

    @classmethod
    def execution_context_expired(cls) -> AgentToolError:
        return cls(
            status_code=410,
            category=AgentErrorCategory.STATE_ERROR,
            code="EXECUTION_CONTEXT_EXPIRED",
            message="실행 Context 가 만료되었습니다.",
            retryable=False,
        )

    @classmethod
    def insufficient_scope(cls) -> AgentToolError:
        return cls(
            status_code=403,
            category=AgentErrorCategory.AUTHORIZATION_ERROR,
            code="INSUFFICIENT_SCOPE",
            message="이 작업에 필요한 권한(Scope)이 없습니다.",
            retryable=False,
        )

    @classmethod
    def backend_temporary_error(cls) -> AgentToolError:
        return cls(
            status_code=503,
            category=AgentErrorCategory.TECHNICAL_ERROR,
            code="BACKEND_TEMPORARY_ERROR",
            message="일시적으로 요청을 처리할 수 없습니다.",
            retryable=True,
        )
