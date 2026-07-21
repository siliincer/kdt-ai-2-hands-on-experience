"""계약 기반 Workflow 공통 State와 실행 Context 보조 함수 테스트."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from langchain_core.runnables import RunnableConfig

from agent.clients.backend.client import AgentToolApiError
from agent.contracts.backend import AgentToolErrorData, AgentWebhookRequest
from agent.state import AgentState
from agent.workflows.workflow_support import (
    build_tool_error_update,
    config_context,
    masked_account_options,
    new_input_request_id,
    publish_event,
    route_key,
    state_data,
    step_request_id,
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


def test_common_request_id_factories_preserve_trace_format() -> None:
    first = new_input_request_id()
    second = new_input_request_id()

    assert first.startswith("input_")
    assert second.startswith("input_")
    assert first != second
    assert step_request_id("request_123", "query_accounts") == (
        "request_123:query_accounts"
    )


def test_masked_account_options_excludes_sensitive_and_unknown_fields() -> None:
    result = masked_account_options(
        [
            {
                "account_id": "account_123",
                "bank_name": "우리은행",
                "account_alias": "생활비",
                "account_type": "checking",
                "masked_account_number": "123-****-789",
                "currency": "KRW",
                "is_default": True,
                "account_number": "123456789",
                "owner_name": "홍길동",
            }
        ]
    )

    assert result == [
        {
            "account_id": "account_123",
            "bank_name": "우리은행",
            "account_alias": "생활비",
            "account_type": "checking",
            "masked_account_number": "123-****-789",
            "currency": "KRW",
            "is_default": True,
        }
    ]


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
        idempotency_key="test",
    )

    assert call.execution_context_id == "execution_123"
    assert call.request_id == "request_123:query_accounts"
    assert call.arguments == {"account_hint": "주거래"}
    assert call.idempotency_key == "test"


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


def test_tool_error_update_prefers_safe_api_message() -> None:
    update = build_tool_error_update("기본 오류 안내")
    error = AgentToolApiError(
        status_code=409,
        request_id="request_123",
        error=AgentToolErrorData(
            category="business",
            code="ACCOUNT_NOT_AVAILABLE",
            message="선택한 계좌를 사용할 수 없습니다.",
        ),
    )

    assert update("query_accounts", error) == {
        "current_step_id": "query_accounts",
        "route_key": "error",
        "data": {"safe_error_message": "선택한 계좌를 사용할 수 없습니다."},
    }


def test_tool_error_update_uses_workflow_default_for_internal_error() -> None:
    update = build_tool_error_update("기본 오류 안내")

    assert update("query_accounts", RuntimeError("내부 상세")) == {
        "current_step_id": "query_accounts",
        "route_key": "error",
        "data": {"safe_error_message": "기본 오류 안내"},
    }


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
