"""Workflow Testbed 결정적 값 Factory 테스트."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from agent.testing.workflow_testbed import constant_factory, sequence_factory


def test_constant_factory_returns_same_value() -> None:
    now = datetime(2026, 7, 21, tzinfo=timezone.utc)
    factory = constant_factory(now)

    assert factory() is now
    assert factory() is now


def test_sequence_factory_returns_values_in_order() -> None:
    factory = sequence_factory(["input_1", "input_2"])

    assert factory() == "input_1"
    assert factory() == "input_2"
    with pytest.raises(StopIteration):
        factory()
