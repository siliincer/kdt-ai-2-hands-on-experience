from __future__ import annotations

import pytest

from security.redteam.runner.target_model import (
    TargetModelMonitor,
    _TrackedRunnable,
)


class _SuccessRunnable:
    async def ainvoke(self, value):
        return {"value": value}

    def with_structured_output(self, _schema):
        return self


class _FailureRunnable:
    async def ainvoke(self, _value):
        raise RuntimeError("synthetic Target failure")


@pytest.mark.asyncio
async def test_tracked_target_model_records_success() -> None:
    monitor = TargetModelMonitor(
        base_url="http://127.0.0.1:11434",
        model="target-model",
    )
    runnable = _TrackedRunnable(
        _SuccessRunnable(),
        monitor,
    )

    result = await runnable.ainvoke("attack")

    assert result == {"value": "attack"}
    assert monitor.telemetry().model_dump() == {
        "model": "target-model",
        "attempts": 1,
        "successes": 1,
        "failures": 0,
        "fallbacks": 0,
    }


@pytest.mark.asyncio
async def test_tracked_target_model_records_failure() -> None:
    monitor = TargetModelMonitor(
        base_url="http://127.0.0.1:11434",
        model="target-model",
    )
    runnable = _TrackedRunnable(
        _FailureRunnable(),
        monitor,
    )

    with pytest.raises(
        RuntimeError,
        match="synthetic Target failure",
    ):
        await runnable.ainvoke("attack")

    assert monitor.telemetry().model_dump() == {
        "model": "target-model",
        "attempts": 1,
        "successes": 0,
        "failures": 1,
        "fallbacks": 0,
    }


@pytest.mark.asyncio
async def test_structured_runnable_keeps_target_tracking() -> None:
    monitor = TargetModelMonitor(
        base_url="http://127.0.0.1:11434",
        model="target-model",
    )
    runnable = _TrackedRunnable(
        _SuccessRunnable(),
        monitor,
    )

    structured = runnable.with_structured_output(dict)
    await structured.ainvoke("attack")

    telemetry = monitor.telemetry()

    assert telemetry.attempts == 1
    assert telemetry.successes == 1


def test_target_telemetry_delta_is_per_execution() -> None:
    monitor = TargetModelMonitor(
        base_url="http://127.0.0.1:11434",
        model="target-model",
    )
    before = monitor.snapshot()

    monitor._record_attempt()
    monitor._record_success()

    delta = monitor.delta(before)

    assert delta.model_dump() == {
        "model": "target-model",
        "attempts": 1,
        "successes": 1,
        "failures": 0,
        "fallbacks": 0,
    }
