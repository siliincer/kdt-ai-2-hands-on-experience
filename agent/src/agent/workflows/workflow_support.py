"""계약 기반 Workflow가 공유하는 State와 실행 Context 보조 함수."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, Literal, Protocol

from langchain_core.runnables import RunnableConfig

from agent.contracts.backend import AgentWebhookRequest
from agent.state import AgentState
from agent.tools.contract_registry import ContractToolCall


class WebhookPublisher(Protocol):
    """Workflow 공통 발행 함수가 사용하는 Webhook Client 최소 표면."""

    async def publish(
        self,
        event: AgentWebhookRequest,
        *,
        execution_context_id: str,
        request_id: str,
    ) -> str: ...


class WorkflowIoDependencies(Protocol):
    """공통 Tool 호출과 Webhook 발행에 필요한 최소 의존성."""

    @property
    def tool_request_id_factory(self) -> Callable[[str, str], str]: ...

    @property
    def webhook_client(self) -> WebhookPublisher: ...


def state_data(state: AgentState) -> dict[str, Any]:
    """누적 State의 data를 Node에서 안전하게 수정할 수 있는 복사본으로 반환한다."""

    return dict(state.get("data") or {})


def route_key(state: AgentState) -> str:
    """Route가 없으면 각 Workflow의 오류 경로로 보낼 기본값을 반환한다."""

    return str(state.get("route_key") or "error")


def config_context(config: RunnableConfig, key: str) -> str:
    """LangGraph configurable에서 비어 있지 않은 필수 문자열 Context를 읽는다."""

    configurable = config.get("configurable") or {}
    value = configurable.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"LangGraph 실행 Context가 없습니다: {key}")
    return value


def tool_call(
    config: RunnableConfig,
    *,
    dependencies: WorkflowIoDependencies,
    step_id: str,
    arguments: Mapping[str, Any],
    idempotency_key: str | None = None,
) -> ContractToolCall:
    """공통 실행 Context와 Step별 ID를 사용해 Tool 호출 요청을 만든다."""

    parent_request_id = config_context(config, "request_id")
    return ContractToolCall(
        execution_context_id=config_context(config, "execution_context_id"),
        request_id=dependencies.tool_request_id_factory(parent_request_id, step_id),
        arguments=arguments,
        idempotency_key=idempotency_key,
    )


async def publish_event(
    dependencies: WorkflowIoDependencies,
    event: AgentWebhookRequest,
    config: RunnableConfig,
) -> None:
    """현재 실행 Context를 보존해 Workflow Webhook 이벤트를 발행한다."""

    await dependencies.webhook_client.publish(
        event,
        execution_context_id=config_context(config, "execution_context_id"),
        request_id=config_context(config, "request_id"),
    )


def terminal_update(
    step_id: str,
    *,
    status: Literal["completed", "workflow_failed"] = "completed",
) -> dict[str, Any]:
    """종료 Node가 공통으로 반환하는 State 변경값을 만든다."""

    return {
        "current_step_id": step_id,
        "route_key": "completed",
        "status": status,
    }
