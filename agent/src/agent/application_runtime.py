"""FastAPI 서비스가 사용하는 계약 기반 Execution Runtime을 조립한다."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

import httpx
from langgraph.checkpoint.memory import MemorySaver
from pydantic import SecretStr

from agent.clients.backend import (
    BackendAgentTools,
    BackendClientConfig,
    BackendToolClient,
    BackendWebhookClient,
)
from agent.runtime import (
    ExecutionRuntime,
    InteractionPauseRuntime,
    InteractionWebhookBuilder,
    ResumeStateMapper,
    WebhookExecutionCompletionReporter,
    WebhookExecutionFailureReporter,
)
from agent.tools.backend_agent_tools import register_backend_agent_tools
from agent.tools.contract_registry import (
    ContractToolRegistrationError,
    ContractToolRegistry,
)
from agent.workflow_contracts import WorkflowContractStore
from agent.workflows.contract_agent import (
    ContractAgentDependencies,
    build_contract_agent_graph,
)

logger = logging.getLogger(__name__)


class AgentRuntimeConfigurationError(RuntimeError):
    """서비스용 Runtime 필수 환경변수가 준비되지 않은 경우."""


@dataclass(slots=True)
class AgentRuntimeResources:
    """FastAPI lifespan 동안 유지하고 종료 시 정리할 Runtime 자원."""

    execution_runtime: ExecutionRuntime
    http_client: httpx.AsyncClient

    async def aclose(self) -> None:
        await self.http_client.aclose()


async def create_agent_runtime_resources() -> AgentRuntimeResources:
    """환경변수와 공통 Adapter를 사용해 서비스용 Runtime을 생성한다."""

    config = _backend_client_config_from_environment()
    http_client = httpx.AsyncClient(
        base_url=config.base_url.rstrip("/"),
        timeout=httpx.Timeout(
            timeout=config.request_timeout_seconds,
            connect=config.connect_timeout_seconds,
        ),
    )
    try:
        contract_store = WorkflowContractStore()
        tool_registry = ContractToolRegistry(contract_store)
        backend_tools = BackendAgentTools(BackendToolClient(config, client=http_client))
        register_backend_agent_tools(tool_registry, backend_tools)
        try:
            tool_registry.validate_workflow_contracts()
        except ContractToolRegistrationError as error:
            logger.critical(
                "Agent Runtime 필수 Tool 계약이 누락되어 시작할 수 없습니다.",
                extra={
                    "missing_contracts_by_workflow": error.missing_by_workflow,
                },
            )
            raise
        webhook_client = BackendWebhookClient(config, client=http_client)
        interaction_runtime = InteractionPauseRuntime(webhook_client)
        webhook_builder = InteractionWebhookBuilder(contract_store)
        graph = build_contract_agent_graph(
            ContractAgentDependencies(
                tool_registry=tool_registry,
                webhook_client=webhook_client,
                interaction_runtime=interaction_runtime,
                webhook_builder=webhook_builder,
            ),
            checkpointer=MemorySaver(),
        )
        execution_runtime = ExecutionRuntime(
            graph=graph,
            interaction_runtime=interaction_runtime,
            resume_mapper=ResumeStateMapper(contract_store),
            failure_reporter=WebhookExecutionFailureReporter(
                webhook_client,
                webhook_builder,
            ),
            completion_reporter=WebhookExecutionCompletionReporter(
                webhook_client,
            ),
        )
    except Exception:
        await http_client.aclose()
        raise
    return AgentRuntimeResources(
        execution_runtime=execution_runtime,
        http_client=http_client,
    )


def _backend_client_config_from_environment() -> BackendClientConfig:
    required_names = (
        "BACKEND_BASE_URL",
        "AGENT_SERVICE_TOKEN",
        "AGENT_WEBHOOK_SECRET",
    )
    values = {name: os.getenv(name, "").strip() for name in required_names}
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise AgentRuntimeConfigurationError(
            "Agent Runtime 필수 환경변수가 없습니다: " + ", ".join(missing)
        )
    return BackendClientConfig(
        base_url=values["BACKEND_BASE_URL"],
        agent_service_token=SecretStr(values["AGENT_SERVICE_TOKEN"]),
        agent_webhook_secret=SecretStr(values["AGENT_WEBHOOK_SECRET"]),
    )
