"""계약 기반 Workflow 공통 State와 실행 Context 보조 함수 테스트."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from langchain_core.runnables import RunnableConfig

from agent.contracts.backend import AgentWebhookRequest
from agent.state import AgentState
from agent.workflows.workflow_support import (
    config_context,
    publish_event,
    route_key,
    state_data,
    terminal_update,
    tool_call,
)


class _RecordingWebhookClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def publish(
        self,
        event: AgentWebhookRequest,
        *,
        execution_context_id: str,
        request_id: str,
    ) -> str:
        self.calls.append(
            {
                "event": event,
                "execution_context_id": execution_context_id,
                "request_id": request_id,
            }
        )
        return "message_123"


class _Dependencies:
    def __init__(self) -> None:
        self.tool_request_id_factory: Callable[[str, str], str] = (
            lambda request_id, step_id: f"{request_id}:{step_id}"
        )
        self.webhook_client = _RecordingWebhookClient()


def test_state_data_returns_copy_without_mutating_state() -> None:
    state: AgentState = {"data": {"account_id": "account_123"}}

    copied = state_data(state)
    copied["account_id"] = "account_456"

    assert state["data"] == {"account_id": "account_123"}


def test_route_key_defaults_to_error() -> None:
    assert route_key({}) == "error"
    assert route_key({"route_key": "succeeded"}) == "succeeded"


def test_config_context_requires_non_empty_string() -> None:
    config: RunnableConfig = {"configurable": {"request_id": "request_123"}}

    assert config_context(config, "request_id") == "request_123"
    with pytest.raises(ValueError, match="execution_context_id"):
        config_context(config, "execution_context_id")


def test_tool_call_preserves_execution_and_request_context() -> None:
    dependencies = _Dependencies()
    config: RunnableConfig = {
        "configurable": {
            "execution_context_id": "execution_123",
            "request_id": "request_123",
        }
    }

    call = tool_call(
        config,
        dependencies=dependencies,
        step_id="query_accounts",
        arguments={"account_hint": "주거래"},
    )

    assert call.execution_context_id == "execution_123"
    assert call.request_id == "request_123:query_accounts"
    assert call.arguments == {"account_hint": "주거래"}


@pytest.mark.asyncio
async def test_publish_event_preserves_execution_and_request_context() -> None:
    dependencies = _Dependencies()
    config: RunnableConfig = {
        "configurable": {
            "execution_context_id": "execution_123",
            "request_id": "request_123",
        }
    }
    event = AgentWebhookRequest(
        chat_session_id="chat_123",
        event_type="done",
        content="완료",
        metadata={},
    )

    await publish_event(dependencies, event, config)

    assert dependencies.webhook_client.calls == [
        {
            "event": event,
            "execution_context_id": "execution_123",
            "request_id": "request_123",
        }
    ]


def test_terminal_update_uses_requested_status() -> None:
    assert terminal_update("emit_result") == {
        "current_step_id": "emit_result",
        "route_key": "completed",
        "status": "completed",
    }
    assert terminal_update("emit_error", status="workflow_failed") == {
        "current_step_id": "emit_error",
        "route_key": "completed",
        "status": "workflow_failed",
    }
