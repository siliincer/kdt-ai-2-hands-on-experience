"""Agent 이벤트를 Backend Webhook으로 전송하는 공통 Client."""

from __future__ import annotations

import asyncio

import httpx

from agent.clients.backend.client import (
    AgentToolProtocolError,
    AgentToolTransportError,
    BackendClientConfig,
)
from agent.contracts.backend import AgentWebhookRequest

WEBHOOK_PATH = "/api/v1/webhooks/agent"
RETRYABLE_EVENT_TYPES = {
    "status",
    "token",
    "tool_call",
    "component",
    "done",
    "error",
}


class BackendWebhookClient:
    """Webhook 인증과 제한된 읽기 이벤트 재시도를 공통 처리한다."""

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

    async def publish(
        self,
        event: AgentWebhookRequest,
        *,
        execution_context_id: str,
        request_id: str,
    ) -> str:
        headers = {
            "X-Agent-Secret": self._config.agent_webhook_secret.get_secret_value(),
            "X-Execution-Context-Id": execution_context_id,
            "X-Request-Id": request_id,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        retry_allowed = event.event_type in RETRYABLE_EVENT_TYPES
        attempts = self._config.max_retries + 1 if retry_allowed else 1
        response: httpx.Response | None = None

        for attempt in range(attempts):
            try:
                response = await self._client.post(
                    WEBHOOK_PATH,
                    headers=headers,
                    json=event.model_dump(mode="json"),
                )
            except (httpx.TimeoutException, httpx.TransportError) as error:
                if attempt + 1 >= attempts:
                    raise AgentToolTransportError(request_id=request_id) from error
                await self._backoff()
                continue

            if not response.is_success and attempt + 1 < attempts:
                await self._backoff()
                continue
            break

        if response is None:
            raise AgentToolTransportError(request_id=request_id)
        if not response.is_success:
            raise AgentToolProtocolError(
                request_id=request_id,
                reason=f"Webhook HTTP {response.status_code}",
            )
        try:
            payload = response.json()
            message_id = payload["data"]["message_id"]
        except (KeyError, TypeError, ValueError) as error:
            raise AgentToolProtocolError(
                request_id=request_id,
                reason="Webhook 응답의 message_id 누락",
            ) from error
        if not isinstance(message_id, str):
            raise AgentToolProtocolError(
                request_id=request_id,
                reason="Webhook message_id 형식 오류",
            )
        return message_id

    async def _backoff(self) -> None:
        if self._config.retry_backoff_seconds:
            await asyncio.sleep(self._config.retry_backoff_seconds)

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> BackendWebhookClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()
