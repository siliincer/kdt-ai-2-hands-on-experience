"""HTTP client for the existing Agent service contract."""

from __future__ import annotations

import time

import httpx

from security.redteam.config import TargetConfig
from security.redteam.models import AgentResponse, LedgerSnapshot, LlmTelemetry


class RequestBudgetError(RuntimeError):
    """Raised before an HTTP call that would exceed the run budget."""


class RequestBudget:
    def __init__(self, limit: int, max_seconds: float | None = None) -> None:
        self.limit = limit
        self.used = 0
        self._deadline = time.monotonic() + max_seconds if max_seconds else None

    @property
    def remaining(self) -> int:
        return self.limit - self.used

    @property
    def remaining_seconds(self) -> float | None:
        if self._deadline is None:
            return None
        return max(0.0, self._deadline - time.monotonic())

    def check_deadline(self) -> None:
        if self.remaining_seconds == 0:
            raise RequestBudgetError("red-team run deadline exhausted")

    def consume(self, requested_timeout: float | None = None) -> float | None:
        self.check_deadline()
        remaining_seconds = self.remaining_seconds
        if self.remaining <= 0:
            raise RequestBudgetError("red-team HTTP request budget exhausted")
        self.used += 1
        if requested_timeout is None or remaining_seconds is None:
            return requested_timeout
        return min(requested_timeout, remaining_seconds)


class AgentClient:
    def __init__(
        self,
        config: TargetConfig,
        request_budget: RequestBudget,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._config = config
        self._request_budget = request_budget
        self._client = httpx.Client(
            base_url=config.base_url,
            timeout=config.request_timeout_seconds,
            transport=transport,
            trust_env=False,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> AgentClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def check_health(self) -> None:
        timeout = self._request_budget.consume(self._config.request_timeout_seconds)
        response = self._client.get(self._config.health_path, timeout=timeout)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("agent health response must be an object")
        if payload.get("status") != "ok":
            raise RuntimeError("agent health response is not ok")

    def chat(
        self,
        message: str,
        user_id: str,
        thread_id: str | None = None,
    ) -> AgentResponse:
        timeout = self._request_budget.consume(self._config.request_timeout_seconds)
        body = {"message": message, "user_id": user_id}
        if thread_id is not None:
            body["thread_id"] = thread_id
        response = self._client.post(
            self._config.chat_path,
            json=body,
            timeout=timeout,
        )
        response.raise_for_status()
        return AgentResponse.model_validate(response.json())

    def ledger_snapshot(self) -> LedgerSnapshot:
        timeout = self._request_budget.consume(self._config.request_timeout_seconds)
        response = self._client.get(self._config.ledger_path, timeout=timeout)
        response.raise_for_status()
        return LedgerSnapshot.model_validate(response.json())

    def llm_telemetry(self) -> LlmTelemetry:
        timeout = self._request_budget.consume(self._config.request_timeout_seconds)
        response = self._client.get(self._config.llm_telemetry_path, timeout=timeout)
        response.raise_for_status()
        return LlmTelemetry.model_validate(response.json())

    @property
    def remaining_requests(self) -> int:
        return self._request_budget.remaining
