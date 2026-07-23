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
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.category = category
        self.code = code
        self.message = message
        self.retryable = retryable
        self.details = details
        self.headers = headers

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
    def account_not_found(cls) -> AgentToolError:
        return cls(
            status_code=404,
            category=AgentErrorCategory.REQUEST_ERROR,
            code="ACCOUNT_NOT_FOUND",
            message="계좌를 찾을 수 없습니다.",
            retryable=False,
        )

    @classmethod
    def account_access_denied(cls) -> AgentToolError:
        return cls(
            status_code=403,
            category=AgentErrorCategory.AUTHORIZATION_ERROR,
            code="ACCOUNT_ACCESS_DENIED",
            message="계좌에 접근할 수 없습니다.",
            retryable=False,
        )

    @classmethod
    def invalid_request(cls, message: str) -> AgentToolError:
        return cls(
            status_code=400,
            category=AgentErrorCategory.REQUEST_ERROR,
            code="INVALID_REQUEST",
            message=message,
            retryable=False,
        )

    # ── Confirmation 생명주기 (계약 6.1) ─────────────────────────────────────

    @classmethod
    def confirmation_required(cls) -> AgentToolError:
        """승인 대기 중이거나 승인되지 않은 Confirmation 으로 Execute 를 시도."""
        return cls(
            status_code=409,
            category=AgentErrorCategory.STATE_ERROR,
            code="CONFIRMATION_REQUIRED",
            message="사용자 승인이 필요합니다.",
            retryable=False,
        )

    @classmethod
    def confirmation_expired(cls) -> AgentToolError:
        return cls(
            status_code=410,
            category=AgentErrorCategory.STATE_ERROR,
            code="CONFIRMATION_EXPIRED",
            message="승인 요청이 만료되었습니다.",
            retryable=False,
        )

    @classmethod
    def confirmation_mismatch(cls) -> AgentToolError:
        """대상·사용자·목적 불일치이거나 이미 소비된 Confirmation."""
        return cls(
            status_code=409,
            category=AgentErrorCategory.STATE_ERROR,
            code="CONFIRMATION_MISMATCH",
            message="승인 정보가 현재 요청과 일치하지 않습니다.",
            retryable=False,
        )

    @classmethod
    def recipient_not_found(cls) -> AgentToolError:
        """수취인 참조가 없거나 본인 거래 이력에 없는 계좌. 수취인 선택부터 재진행."""
        return cls(
            status_code=404,
            category=AgentErrorCategory.REQUEST_ERROR,
            code="RECIPIENT_NOT_FOUND",
            message="수취인을 찾을 수 없습니다.",
            retryable=False,
        )

    @classmethod
    def recipient_candidate_expired(cls) -> AgentToolError:
        """신규 수취 계좌 후보가 만료·소비됨. 신규 계좌 재검증 필요."""
        return cls(
            status_code=410,
            category=AgentErrorCategory.STATE_ERROR,
            code="RECIPIENT_CANDIDATE_EXPIRED",
            message="수취 계좌 검증이 만료되었습니다. 다시 검증해 주세요.",
            retryable=False,
        )

    @classmethod
    def auth_required(cls) -> AgentToolError:
        """추가 인증이 없거나 유효하지 않음. Agent 는 Auth Context 생성으로 이동."""
        return cls(
            status_code=409,
            category=AgentErrorCategory.STATE_ERROR,
            code="AUTH_REQUIRED",
            message="추가 인증이 필요합니다.",
            retryable=False,
        )

    # ── 멱등성 (계약 24.4) ───────────────────────────────────────────────────

    @classmethod
    def idempotency_key_conflict(cls) -> AgentToolError:
        """같은 멱등성 키에 다른 요청 Body 를 사용."""
        return cls(
            status_code=409,
            category=AgentErrorCategory.REQUEST_ERROR,
            code="IDEMPOTENCY_KEY_CONFLICT",
            message="같은 멱등성 키에 다른 요청을 사용할 수 없습니다.",
            retryable=False,
        )

    @classmethod
    def idempotency_request_in_progress(cls, retry_after_seconds: int = 1) -> AgentToolError:
        """같은 키의 요청이 처리 중. Retry-After 후 같은 키·Body 로 재호출."""
        return cls(
            status_code=409,
            category=AgentErrorCategory.REQUEST_ERROR,
            code="IDEMPOTENCY_REQUEST_IN_PROGRESS",
            message="같은 요청을 처리하고 있습니다.",
            retryable=True,
            headers={"Retry-After": str(retry_after_seconds)},
        )

    @classmethod
    def missing_idempotency_key(cls) -> AgentToolError:
        """상태 변경 API 에 Idempotency-Key 헤더가 없음(계약 4.2)."""
        return cls(
            status_code=400,
            category=AgentErrorCategory.REQUEST_ERROR,
            code="INVALID_REQUEST",
            message="Idempotency-Key 헤더가 필요합니다.",
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
