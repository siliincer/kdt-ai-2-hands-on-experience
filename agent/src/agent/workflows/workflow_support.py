"""계약 기반 Workflow가 공유하는 State와 실행 Context 보조 함수."""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping
from datetime import date
from typing import Any, Literal, Protocol

from langchain_core.runnables import RunnableConfig

from agent.clients.backend.client import AgentToolApiError
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


class ToolCallDependencies(Protocol):
    """공통 Tool 호출에 필요한 최소 의존성."""

    @property
    def tool_request_id_factory(self) -> Callable[[str, str], str]: ...


class WebhookDependencies(Protocol):
    """공통 Webhook 발행에 필요한 최소 의존성."""

    @property
    def webhook_client(self) -> WebhookPublisher: ...


ToolErrorUpdate = Callable[[str, Exception], dict[str, Any]]
_MASKED_ACCOUNT_FIELDS = (
    "account_id",
    "bank_name",
    "account_alias",
    "account_type",
    "masked_account_number",
    "currency",
    "is_default",
)


def new_input_request_id() -> str:
    """사용자 입력 대기 단위를 식별하는 새 요청 ID를 만든다."""

    return f"input_{uuid.uuid4().hex}"


def step_request_id(parent_request_id: str, step_id: str) -> str:
    """부모 실행 요청과 Workflow Step을 연결하는 Tool 요청 ID를 만든다."""

    return f"{parent_request_id}:{step_id}"


def masked_account_options(raw_accounts: Any) -> list[dict[str, Any]]:
    """Backend 계좌 후보에서 UI 표시가 허용된 마스킹 필드만 반환한다."""

    accounts = raw_accounts if isinstance(raw_accounts, list) else []
    return [
        {field: account.get(field) for field in _MASKED_ACCOUNT_FIELDS}
        for account in accounts
        if isinstance(account, Mapping)
    ]


def required_input_request_id(data: Mapping[str, Any]) -> str:
    """Resume 대상과 연결할 비어 있지 않은 입력 요청 ID를 반환한다."""

    value = data.get("input_request_id")
    if not isinstance(value, str) or not value:
        raise ValueError("입력 요청 ID가 없습니다.")
    return value


def valid_iso_date(value: Any) -> str | None:
    """날짜 값이 유효할 때 ISO 날짜 문자열로 정규화한다."""

    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        try:
            return date.fromisoformat(value).isoformat()
        except ValueError:
            return None
    return None


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
    dependencies: ToolCallDependencies,
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
    dependencies: WebhookDependencies,
    event: AgentWebhookRequest,
    config: RunnableConfig,
) -> None:
    """현재 실행 Context를 보존해 Workflow Webhook 이벤트를 발행한다."""

    await dependencies.webhook_client.publish(
        event,
        execution_context_id=config_context(config, "execution_context_id"),
        request_id=config_context(config, "request_id"),
    )


def build_tool_error_update(default_message: str) -> ToolErrorUpdate:
    """업무별 기본 문구를 보존하는 공통 Tool 오류 State 생성기를 만든다."""

    def update(step_id: str, error: Exception) -> dict[str, Any]:
        message = (
            error.safe_message
            if isinstance(error, AgentToolApiError)
            else default_message
        )
        return {
            "current_step_id": step_id,
            "route_key": "error",
            "data": {"safe_error_message": message},
        }

    return update


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
