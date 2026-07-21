"""거래내역 Workflow 전용 Testbed Factory."""

from __future__ import annotations

from datetime import datetime
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
    constant_factory as _constant_now,
)
from agent.testing.workflow_testbed import (
    sequence_factory as _sequence_factory,
)
from agent.workflows.transaction_history import (
    TransactionHistoryDependencies,
    build_transaction_history_graph,
)


def create_transaction_history_mock_testbed(
    backend: MockBackend,
    config: BackendClientConfig,
    *,
    thread_id: str | None = None,
    input_request_ids: list[str] | None = None,
    now: datetime | None = None,
) -> WorkflowTestbed:
    """Mock Backend를 사용하는 거래내역 Testbed를 만든다."""

    return create_workflow_testbed(
        config,
        graph_factory=_transaction_graph_factory(input_request_ids, now),
        transport=httpx.MockTransport(backend.handler),
        thread_id=thread_id,
    )


def create_transaction_history_backend_testbed(
    config: BackendClientConfig,
    *,
    thread_id: str | None = None,
    input_request_ids: list[str] | None = None,
    now: datetime | None = None,
) -> WorkflowTestbed:
    """실제 Backend를 사용하는 거래내역 Testbed를 만든다."""

    return create_workflow_testbed(
        config,
        graph_factory=_transaction_graph_factory(input_request_ids, now),
        thread_id=thread_id,
    )


def _transaction_graph_factory(
    input_request_ids: list[str] | None,
    now: datetime | None,
) -> TestbedGraphFactory:
    def factory(common: WorkflowTestbedDependencies) -> ExecutionGraph:
        if input_request_ids is not None and now is not None:
            dependencies = TransactionHistoryDependencies(
                tool_registry=common.tool_registry,
                webhook_client=common.webhook_client,
                interaction_runtime=common.interaction_runtime,
                webhook_builder=common.webhook_builder,
                input_request_id_factory=_sequence_factory(input_request_ids),
                now_factory=_constant_now(now),
            )
        elif input_request_ids is not None:
            dependencies = TransactionHistoryDependencies(
                tool_registry=common.tool_registry,
                webhook_client=common.webhook_client,
                interaction_runtime=common.interaction_runtime,
                webhook_builder=common.webhook_builder,
                input_request_id_factory=_sequence_factory(input_request_ids),
            )
        elif now is not None:
            dependencies = TransactionHistoryDependencies(
                tool_registry=common.tool_registry,
                webhook_client=common.webhook_client,
                interaction_runtime=common.interaction_runtime,
                webhook_builder=common.webhook_builder,
                now_factory=_constant_now(now),
            )
        else:
            dependencies = TransactionHistoryDependencies(
                tool_registry=common.tool_registry,
                webhook_client=common.webhook_client,
                interaction_runtime=common.interaction_runtime,
                webhook_builder=common.webhook_builder,
            )
        return cast(
            ExecutionGraph,
            build_transaction_history_graph(
                dependencies,
                checkpointer=common.checkpointer,
            ),
        )

    return factory
