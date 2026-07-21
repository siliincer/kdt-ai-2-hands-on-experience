"""계약 기반 Workflow 공통 State와 실행 Context 보조 함수 테스트."""

from __future__ import annotations

import pytest
from langchain_core.runnables import RunnableConfig

from agent.state import AgentState
from agent.workflows.workflow_support import (
    config_context,
    route_key,
    state_data,
    terminal_update,
)


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
