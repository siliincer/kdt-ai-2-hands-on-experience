"""기본 출금 계좌 변경 Workflow 전용 Testbed Factory."""

from __future__ import annotations

from typing import cast

import httpx

from agent.clients.backend import BackendClientConfig
from agent.runtime import ExecutionGraph
from agent.testing.mock_backend import MockBackend
from agent.testing.workflow_testbed import (
    TestbedGraphFactory,
    WorkflowTestbed,
    WorkflowTestbedDependencies,
    create_workflow_testbed,
)
from agent.testing.workflow_testbed import (
    constant_factory as _constant_factory,
)
from agent.workflows.set_default_account import (
    DefaultAccountChangeDependencies,
    build_set_default_account_graph,
)


def create_default_account_change_mock_testbed(
    backend: MockBackend,
    config: BackendClientConfig,
    *,
    thread_id: str | None = None,
    input_request_id: str | None = None,
) -> WorkflowTestbed:
    """Mock Backend를 사용하는 기본 출금 계좌 변경 Testbed를 만든다."""

    return create_workflow_testbed(
        config,
        graph_factory=_set_default_account_graph_factory(input_request_id),
        transport=httpx.MockTransport(backend.handler),
        thread_id=thread_id,
    )


def create_default_account_change_backend_testbed(
    config: BackendClientConfig,
    *,
    thread_id: str | None = None,
    input_request_id: str | None = None,
) -> WorkflowTestbed:
    """실제 Backend를 사용하는 기본 출금 계좌 변경 Testbed를 만든다."""

    return create_workflow_testbed(
        config,
        graph_factory=_set_default_account_graph_factory(input_request_id),
        thread_id=thread_id,
    )


def _set_default_account_graph_factory(
    input_request_id: str | None,
) -> TestbedGraphFactory:
    def factory(common: WorkflowTestbedDependencies) -> ExecutionGraph:
        if input_request_id is None:
            dependencies = DefaultAccountChangeDependencies(
                tool_registry=common.tool_registry,
                webhook_client=common.webhook_client,
                interaction_runtime=common.interaction_runtime,
                webhook_builder=common.webhook_builder,
            )
        else:
            dependencies = DefaultAccountChangeDependencies(
                tool_registry=common.tool_registry,
                webhook_client=common.webhook_client,
                interaction_runtime=common.interaction_runtime,
                webhook_builder=common.webhook_builder,
                input_request_id_factory=_constant_factory(input_request_id),
            )
        return cast(
            ExecutionGraph,
            build_set_default_account_graph(
                dependencies,
                checkpointer=common.checkpointer,
            ),
        )

    return factory
