"""Agent Tool API 공통 HTTP Client."""

from __future__ import annotations

import asyncio
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError

from agent.contracts.backend import (
    AgentToolEnvelope,
    AgentToolErrorData,
)


class BackendClientConfig(BaseModel):
    """Agent가 Backend에 요청을 보낼 때 사용하는 공통 설정."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    base_url: str
    agent_service_token: SecretStr
    agent_webhook_secret: SecretStr
    connect_timeout_seconds: float = Field(default=3.0, gt=0)
    request_timeout_seconds: float = Field(default=10.0, gt=0)
    retry_backoff_seconds: float = Field(default=0.1, ge=0)
    max_retries: int = Field(default=1, ge=0, le=1)


class AgentToolIntegrationError(RuntimeError):
    """Backend 통신 계층의 사용자 비노출 오류."""


class AgentToolApiError(AgentToolIntegrationError):
    """Backend가 구조화된 오류 응답을 반환한 경우."""

    def __init__(self, *, status_code: int, request_id: str, error: AgentToolErrorData):
        super().__init__(f"Backend Tool API 오류: {error.code}")
        self.status_code = status_code
        self.request_id = request_id
        self.category = error.category
        self.code = error.code
        self.safe_message = error.message
        self.retryable = error.retryable
        self.details = error.details


class AgentToolProtocolError(AgentToolIntegrationError):
    """Backend 응답이 공통 계약과 일치하지 않는 경우."""

    def __init__(self, *, request_id: str, reason: str):
        super().__init__(f"Backend 응답 계약 오류: {reason}")
        self.request_id = request_id
        self.reason = reason


class AgentToolTransportError(AgentToolIntegrationError):
    """Timeout 또는 연결 실패로 응답을 받지 못한 경우."""

    def __init__(self, *, request_id: str):
        super().__init__("Backend Tool API 통신에 실패했습니다.")
        self.request_id = request_id


HttpMethod = Literal["GET", "POST"]
RETRYABLE_STATUS_CODES = {502, 503, 504}
AGENT_TOOL_PREFIX = "/api/v1/agent-tools"


class BackendToolClient:
    """모든 Workflow가 공유하는 Backend Tool API Client."""

    def __init__(
        self,
        config: BackendClientConfig,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._config = config
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=config.base_url.rstrip("/"),
            timeout=httpx.Timeout(
                timeout=config.request_timeout_seconds,
                connect=config.connect_timeout_seconds,
            ),
        )

    async def request(
        self,
        method: HttpMethod,
        path: str,
        *,
        execution_context_id: str,
        request_id: str,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        self._validate_path(path)
        headers = {
            "Authorization": (
                "Bearer " + self._config.agent_service_token.get_secret_value()
            ),
            "X-Execution-Context-Id": execution_context_id,
            "X-Request-Id": request_id,
            "Accept": "application/json",
        }
        if body is not None:
            headers["Content-Type"] = "application/json"
        if idempotency_key is not None:
            headers["Idempotency-Key"] = idempotency_key

        response: httpx.Response | None = None
        attempts = self._config.max_retries + 1
        for attempt in range(attempts):
            try:
                response = await self._client.request(
                    method,
                    path,
                    headers=headers,
                    params=params,
                    json=body,
                )
            except (httpx.TimeoutException, httpx.TransportError) as error:
                if attempt + 1 >= attempts:
                    raise AgentToolTransportError(request_id=request_id) from error
                await self._backoff()
                continue

            if (
                response.status_code in RETRYABLE_STATUS_CODES
                and attempt + 1 < attempts
            ):
                await self._backoff()
                continue
            break

        if response is None:
            raise AgentToolTransportError(request_id=request_id)
        return self._parse_response(response, request_id=request_id)

    async def _backoff(self) -> None:
        if self._config.retry_backoff_seconds:
            await asyncio.sleep(self._config.retry_backoff_seconds)

    @staticmethod
    def _validate_path(path: str) -> None:
        if not path.startswith(f"{AGENT_TOOL_PREFIX}/"):
            raise ValueError(
                "Agent Tool API 공통 Prefix 밖의 Path는 호출할 수 없습니다."
            )
        if "://" in path or ".." in path:
            raise ValueError("동적 외부 URL이나 상위 경로는 호출할 수 없습니다.")

    @staticmethod
    def _parse_response(
        response: httpx.Response, *, request_id: str
    ) -> dict[str, Any]:
        try:
            raw_payload = response.json()
            envelope = AgentToolEnvelope.model_validate(raw_payload)
        except (ValueError, ValidationError) as error:
            raise AgentToolProtocolError(
                request_id=request_id,
                reason="공통 응답 Schema 불일치",
            ) from error

        if not envelope.success:
            if envelope.error is None:
                raise AgentToolProtocolError(
                    request_id=request_id,
                    reason="오류 응답의 error 필드 누락",
                )
            raise AgentToolApiError(
                status_code=response.status_code,
                request_id=request_id,
                error=envelope.error,
            )
        if not response.is_success:
            raise AgentToolProtocolError(
                request_id=request_id,
                reason="HTTP 상태와 success 값 불일치",
            )
        return envelope.data or {}

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> BackendToolClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()
