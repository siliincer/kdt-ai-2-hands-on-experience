"""기간 거래 합계 Workflow 전용 Testbed Factory."""

from __future__ import annotations

from collections.abc import Callable
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
from agent.workflows.period_amount_summary import (
    PeriodAmountSummaryDependencies,
    build_period_amount_summary_graph,
)


def create_period_amount_summary_mock_testbed(
    backend: MockBackend,
    config: BackendClientConfig,
    *,
    thread_id: str | None = None,
    input_request_ids: list[str] | None = None,
    now: datetime | None = None,
) -> WorkflowTestbed:
    """Mock Backend를 사용하는 기간 합계 Testbed를 만든다."""

    return create_workflow_testbed(
        config,
        graph_factory=_summary_graph_factory(input_request_ids, now),
        transport=httpx.MockTransport(backend.handler),
        thread_id=thread_id,
    )


def create_period_amount_summary_backend_testbed(
    config: BackendClientConfig,
    *,
    thread_id: str | None = None,
    input_request_ids: list[str] | None = None,
    now: datetime | None = None,
) -> WorkflowTestbed:
    """실제 Backend를 사용하는 기간 합계 Testbed를 만든다."""

    return create_workflow_testbed(
        config,
        graph_factory=_summary_graph_factory(input_request_ids, now),
        thread_id=thread_id,
    )


def _summary_graph_factory(
    input_request_ids: list[str] | None,
    now: datetime | None,
) -> TestbedGraphFactory:
    def factory(common: WorkflowTestbedDependencies) -> ExecutionGraph:
        if input_request_ids is not None and now is not None:
            dependencies = PeriodAmountSummaryDependencies(
                tool_registry=common.tool_registry,
                webhook_client=common.webhook_client,
                interaction_runtime=common.interaction_runtime,
                webhook_builder=common.webhook_builder,
                input_request_id_factory=_sequence_factory(input_request_ids),
                now_factory=_constant_now(now),
            )
        elif input_request_ids is not None:
            dependencies = PeriodAmountSummaryDependencies(
                tool_registry=common.tool_registry,
                webhook_client=common.webhook_client,
                interaction_runtime=common.interaction_runtime,
                webhook_builder=common.webhook_builder,
                input_request_id_factory=_sequence_factory(input_request_ids),
            )
        elif now is not None:
            dependencies = PeriodAmountSummaryDependencies(
                tool_registry=common.tool_registry,
                webhook_client=common.webhook_client,
                interaction_runtime=common.interaction_runtime,
                webhook_builder=common.webhook_builder,
                now_factory=_constant_now(now),
            )
        else:
            dependencies = PeriodAmountSummaryDependencies(
                tool_registry=common.tool_registry,
                webhook_client=common.webhook_client,
                interaction_runtime=common.interaction_runtime,
                webhook_builder=common.webhook_builder,
            )
        return cast(
            ExecutionGraph,
            build_period_amount_summary_graph(
                dependencies,
                checkpointer=common.checkpointer,
            ),
        )

    return factory


def _sequence_factory(values: list[str]) -> Callable[[], str]:
    iterator = iter(values)
    return lambda: next(iterator)


def _constant_now(value: datetime) -> Callable[[], datetime]:
    return lambda: value
