"""Backend HTTP Client가 공유하는 생명주기와 Header 기반 처리."""

from __future__ import annotations

import asyncio
from typing import Self

import httpx

from agent.clients.backend.client_config import BackendClientConfig


class BackendHttpClientBase:
    """Backend Client의 HTTP 자원 소유권과 공통 Header를 관리한다."""

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

    def _headers(
        self,
        *,
        authentication_header: tuple[str, str],
        execution_context_id: str,
        request_id: str,
        json_content: bool = False,
    ) -> dict[str, str]:
        authentication_name, authentication_value = authentication_header
        headers = {
            authentication_name: authentication_value,
            "X-Execution-Context-Id": execution_context_id,
            "X-Request-Id": request_id,
            "Accept": "application/json",
        }
        if json_content:
            headers["Content-Type"] = "application/json"
        return headers

    async def _backoff(self) -> None:
        if self._config.retry_backoff_seconds:
            await asyncio.sleep(self._config.retry_backoff_seconds)

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()
