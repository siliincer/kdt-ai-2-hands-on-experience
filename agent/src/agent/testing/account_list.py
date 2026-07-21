"""계좌 목록 Workflow 전용 Testbed Factory."""

from __future__ import annotations

from typing import cast

import httpx

from agent.clients.backend import BackendClientConfig
from agent.runtime import ExecutionGraph
from agent.testing.mock_backend import MockBackend
from agent.testing.workflow_testbed import (
    WorkflowTestbed,
    WorkflowTestbedDependencies,
    create_workflow_testbed,
)
from agent.workflows.account_list import (
    AccountListDependencies,
    build_account_list_graph,
)


def create_account_list_mock_testbed(
    backend: MockBackend,
    config: BackendClientConfig,
    *,
    thread_id: str | None = None,
) -> WorkflowTestbed:
    """Mock Backend를 사용하는 계좌 목록 Testbed를 만든다."""

    return create_workflow_testbed(
        config,
        graph_factory=_account_list_graph_factory,
        transport=httpx.MockTransport(backend.handler),
        thread_id=thread_id,
    )


def create_account_list_backend_testbed(
    config: BackendClientConfig,
    *,
    thread_id: str | None = None,
) -> WorkflowTestbed:
    """실제 Backend를 사용하는 계좌 목록 Testbed를 만든다."""

    return create_workflow_testbed(
        config,
        graph_factory=_account_list_graph_factory,
        thread_id=thread_id,
    )


def _account_list_graph_factory(
    common: WorkflowTestbedDependencies,
) -> ExecutionGraph:
    dependencies = AccountListDependencies(
        tool_registry=common.tool_registry,
        webhook_client=common.webhook_client,
        webhook_builder=common.webhook_builder,
    )
    return cast(
        ExecutionGraph,
        build_account_list_graph(
            dependencies,
            checkpointer=common.checkpointer,
        ),
    )
