"""Fail-closed telemetry for the real Agent target model."""

from __future__ import annotations

import importlib
import os
import sys
from contextlib import AbstractContextManager
from types import ModuleType
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TargetModelExecutionError(RuntimeError):
    """Raised when a Red Team run cannot prove real Target model execution."""


class TargetModelTelemetry(BaseModel):
    """Target model inference evidence preserved in Red Team reports."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model: str
    attempts: int = Field(default=0, ge=0)
    successes: int = Field(default=0, ge=0)
    failures: int = Field(default=0, ge=0)
    fallbacks: int = Field(default=0, ge=0)


class _TrackedRunnable:
    """Transparent Runnable proxy that records real inference calls."""

    def __init__(
        self,
        runnable: Any,
        monitor: TargetModelMonitor,
    ) -> None:
        self._runnable = runnable
        self._monitor = monitor

    def invoke(self, *args: Any, **kwargs: Any) -> Any:
        self._monitor._record_attempt()

        try:
            result = self._runnable.invoke(*args, **kwargs)
        except Exception:
            self._monitor._record_failure()
            raise

        self._monitor._record_success()
        return result

    async def ainvoke(self, *args: Any, **kwargs: Any) -> Any:
        self._monitor._record_attempt()

        try:
            result = await self._runnable.ainvoke(*args, **kwargs)
        except Exception:
            self._monitor._record_failure()
            raise

        self._monitor._record_success()
        return result

    def with_structured_output(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> _TrackedRunnable:
        return _TrackedRunnable(
            self._runnable.with_structured_output(*args, **kwargs),
            self._monitor,
        )

    def bind_tools(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> _TrackedRunnable:
        return _TrackedRunnable(
            self._runnable.bind_tools(*args, **kwargs),
            self._monitor,
        )

    def bind(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> _TrackedRunnable:
        return _TrackedRunnable(
            self._runnable.bind(*args, **kwargs),
            self._monitor,
        )

    def with_config(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> _TrackedRunnable:
        return _TrackedRunnable(
            self._runnable.with_config(*args, **kwargs),
            self._monitor,
        )

    def with_retry(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> _TrackedRunnable:
        return _TrackedRunnable(
            self._runnable.with_retry(*args, **kwargs),
            self._monitor,
        )

    def __getattr__(self, name: str) -> Any:
        return getattr(self._runnable, name)


class TargetModelMonitor(
    AbstractContextManager["TargetModelMonitor"],
):
    """Force and verify the configured Ollama Target model during Agent runs."""

    _ENV_KEYS = (
        "LLM_PROVIDER",
        "OLLAMA_BASE_URL",
        "OLLAMA_MODEL",
        "LLM_MODEL",
        "LANGCHAIN_TRACING_V2",
        "LANGSMITH_TRACING",
    )

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
    ) -> None:
        self.base_url = base_url
        self.model = model

        self._attempts = 0
        self._successes = 0
        self._failures = 0
        self._fallbacks = 0

        self._old_environment: dict[str, str | None] = {}
        self._patches: list[tuple[ModuleType, str, Any]] = []

        self._original_get_llm: Any = None
        self._original_invoke_structured: Any = None
        self._tracked_get_llm: Any = None
        self._strict_invoke_structured: Any = None

    def telemetry(self) -> TargetModelTelemetry:
        return TargetModelTelemetry(
            model=self.model,
            attempts=self._attempts,
            successes=self._successes,
            failures=self._failures,
            fallbacks=self._fallbacks,
        )

    def snapshot(self) -> TargetModelTelemetry:
        return self.telemetry()

    def delta(
        self,
        before: TargetModelTelemetry,
    ) -> TargetModelTelemetry:
        if before.model != self.model:
            raise ValueError("Target model telemetry snapshot uses another model")

        current = self.telemetry()

        return TargetModelTelemetry(
            model=self.model,
            attempts=current.attempts - before.attempts,
            successes=current.successes - before.successes,
            failures=current.failures - before.failures,
            fallbacks=current.fallbacks - before.fallbacks,
        )

    def _record_attempt(self) -> None:
        self._attempts += 1

    def _record_success(self) -> None:
        self._successes += 1

    def _record_failure(self) -> None:
        self._failures += 1

    def _record_fallback(self) -> None:
        self._fallbacks += 1

    def _set_environment(self) -> None:
        self._old_environment = {key: os.environ.get(key) for key in self._ENV_KEYS}

        os.environ["LLM_PROVIDER"] = "ollama"
        os.environ["OLLAMA_BASE_URL"] = self.base_url
        os.environ["OLLAMA_MODEL"] = self.model
        os.environ["LLM_MODEL"] = self.model
        os.environ["LANGCHAIN_TRACING_V2"] = "false"
        os.environ["LANGSMITH_TRACING"] = "false"

    def _restore_environment(self) -> None:
        for key, value in self._old_environment.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def _patch_attribute(
        self,
        module: ModuleType,
        name: str,
        expected: Any,
        replacement: Any,
    ) -> None:
        if getattr(module, name, None) is not expected:
            return

        self._patches.append(
            (
                module,
                name,
                expected,
            )
        )
        setattr(module, name, replacement)

    def _patch_loaded_modules(self) -> None:
        for module_name, module in tuple(sys.modules.items()):
            if not module_name.startswith("agent.") or not isinstance(module, ModuleType):
                continue

            self._patch_attribute(
                module,
                "get_llm",
                self._original_get_llm,
                self._tracked_get_llm,
            )
            self._patch_attribute(
                module,
                "invoke_structured",
                self._original_invoke_structured,
                self._strict_invoke_structured,
            )

    def __enter__(self) -> TargetModelMonitor:
        self._set_environment()

        try:
            agent_llm = importlib.import_module("agent.llm")
            slot_support = importlib.import_module("agent.workflows.slot_extraction_support")
            importlib.import_module("agent.workflows.query_slot_extraction")

            self._original_get_llm = agent_llm.get_llm
            self._original_invoke_structured = slot_support.invoke_structured

            cache_clear = getattr(
                self._original_get_llm,
                "cache_clear",
                None,
            )
            if callable(cache_clear):
                cache_clear()

            def tracked_get_llm(
                *args: Any,
                **kwargs: Any,
            ) -> _TrackedRunnable:
                runnable = self._original_get_llm(
                    *args,
                    **kwargs,
                )
                return _TrackedRunnable(
                    runnable,
                    self,
                )

            async def strict_invoke_structured(
                *args: Any,
                **kwargs: Any,
            ) -> Any:
                result = await self._original_invoke_structured(
                    *args,
                    **kwargs,
                )

                if result is None:
                    self._record_fallback()
                    raise TargetModelExecutionError(
                        "Target model structured output failed; rule fallback is forbidden during Red Team execution"
                    )

                return result

            self._tracked_get_llm = tracked_get_llm
            self._strict_invoke_structured = strict_invoke_structured

            self._patch_loaded_modules()

        except BaseException:
            self._restore_environment()
            raise

        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: Any,
    ) -> bool:
        del exc_type, exc_value, traceback

        for module, name, original in reversed(self._patches):
            setattr(
                module,
                name,
                original,
            )

        self._patches.clear()

        for module_name, module in tuple(sys.modules.items()):
            if not module_name.startswith("agent.") or not isinstance(module, ModuleType):
                continue

            if (
                getattr(
                    module,
                    "get_llm",
                    None,
                )
                is self._tracked_get_llm
            ):
                setattr(
                    module,
                    "get_llm",
                    self._original_get_llm,
                )

            if (
                getattr(
                    module,
                    "invoke_structured",
                    None,
                )
                is self._strict_invoke_structured
            ):
                setattr(
                    module,
                    "invoke_structured",
                    self._original_invoke_structured,
                )

        cache_clear = getattr(
            self._original_get_llm,
            "cache_clear",
            None,
        )
        if callable(cache_clear):
            cache_clear()

        self._restore_environment()
        return False
