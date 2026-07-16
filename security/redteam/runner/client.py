"""HTTP client for the existing Agent service contract."""

from __future__ import annotations

import httpx

from security.redteam.config import TargetConfig
from security.redteam.models import AgentResponse, LedgerSnapshot, LlmTelemetry


class RequestBudgetError(RuntimeError):
    """Raised before an HTTP call that would exceed the run budget."""


class RequestBudget:
    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.used = 0

    @property
    def remaining(self) -> int:
        return self.limit - self.used

    def consume(self) -> None:
        if self.remaining <= 0:
            raise RequestBudgetError("red-team HTTP request budget exhausted")
        self.used += 1


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
        self._request_budget.consume()
        response = self._client.get(self._config.health_path)
        response.raise_for_status()
        if response.json().get("status") != "ok":
            raise RuntimeError("agent health response is not ok")

    def chat(
        self,
        message: str,
        user_id: str,
        thread_id: str | None = None,
    ) -> AgentResponse:
        self._request_budget.consume()
        body = {"message": message, "user_id": user_id}
        if thread_id is not None:
            body["thread_id"] = thread_id
        response = self._client.post(
            self._config.chat_path,
            json=body,
        )
        response.raise_for_status()
        return AgentResponse.model_validate(response.json())

    def ledger_snapshot(self) -> LedgerSnapshot:
        self._request_budget.consume()
        response = self._client.get(self._config.ledger_path)
        response.raise_for_status()
        return LedgerSnapshot.model_validate(response.json())

    def llm_telemetry(self) -> LlmTelemetry:
        self._request_budget.consume()
        response = self._client.get(self._config.llm_telemetry_path)
        response.raise_for_status()
        return LlmTelemetry.model_validate(response.json())

    @property
    def remaining_requests(self) -> int:
        return self._request_budget.remaining
