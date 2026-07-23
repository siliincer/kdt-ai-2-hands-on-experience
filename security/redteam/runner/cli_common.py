"""Shared CLI utilities for Agent V3 red-team commands."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import time
import uuid
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path

from pydantic import BaseModel

from security.redteam.config import RedTeamConfig
from security.redteam.models import ExecutionErrorReport
from security.redteam.runner.client import RequestBudget, RequestBudgetError
from security.redteam.runner.reporter import (
    ReportWriteError,
    write_execution_error_report,
)
from security.redteam.runner.sanitizer import redact

REDTEAM_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = REDTEAM_ROOT.parents[1]

DEFAULT_REDACT_FIELDS = {
    "account_number",
    "authorization",
    "cookie",
    "token",
}


def _redacted_error_message(
    error: object,
    redact_fields: set[str],
) -> str:
    message = str(error) or type(error).__name__
    redacted = redact(message, redact_fields)

    return redacted if isinstance(redacted, str) else type(error).__name__


def _model_name(value: str) -> str:
    if not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}",
        value,
    ):
        raise argparse.ArgumentTypeError("model contains unsupported characters")

    return value


def _with_model_overrides(
    config: RedTeamConfig,
    *,
    model: str | None = None,
    generator_model: str | None = None,
    target_model: str | None = None,
    judgment_model: str | None = None,
    seed: int | None = None,
) -> RedTeamConfig:
    if model is not None:
        raise ValueError("--model is disabled; generator, Target, and judgment models must differ")

    adaptive_updates: dict[str, object] = {}

    if generator_model is not None:
        adaptive_updates["model"] = generator_model

    if seed is not None:
        adaptive_updates["seed"] = seed

    safety_updates: dict[str, object] = {}

    if target_model is not None:
        safety_updates["required_ollama_model"] = target_model

    judgment_updates: dict[str, object] = {}

    if judgment_model is not None:
        judgment_updates["model"] = judgment_model

    raw = config.model_dump(mode="python")
    raw["adaptive_attack"].update(adaptive_updates)
    raw["safety"].update(safety_updates)
    raw["judgment"].update(judgment_updates)

    return RedTeamConfig.model_validate(raw)


def _canonical_sha256(value: object) -> str:
    def normalize(item: object) -> object:
        if isinstance(item, BaseModel):
            return normalize(item.model_dump(mode="python"))

        if isinstance(item, Enum):
            return normalize(item.value)

        if isinstance(item, Path):
            return str(item)

        if isinstance(item, dict):
            return {str(key): normalize(item[key]) for key in sorted(item, key=str)}

        if isinstance(item, (set, frozenset)):
            normalized = [normalize(value) for value in item]

            return sorted(
                normalized,
                key=lambda value: json.dumps(
                    value,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            )

        if isinstance(item, (list, tuple)):
            return [normalize(value) for value in item]

        if item is None or isinstance(
            item,
            (str, int, float, bool),
        ):
            return item

        return str(item)

    encoded = json.dumps(
        normalize(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    return hashlib.sha256(encoded).hexdigest()


def _git_state() -> tuple[str | None, bool | None]:
    try:
        commit = subprocess.run(
            [
                "git",
                "rev-parse",
                "HEAD",
            ],
            cwd=REPOSITORY_ROOT,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()

        status = subprocess.run(
            [
                "git",
                "status",
                "--porcelain",
            ],
            cwd=REPOSITORY_ROOT,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout

    except (
        OSError,
        subprocess.SubprocessError,
    ):
        return None, None

    if not re.fullmatch(
        r"[0-9a-f]{40,64}",
        commit,
    ):
        return None, None

    return commit, bool(status.strip())


def _record_cli_error(
    *,
    scenario_name: str,
    stage: str,
    error: Exception,
    started_at: datetime,
    started_monotonic: float,
    output_dir: Path,
    redact_fields: set[str],
    finalization_timeout_seconds: float = 10,
) -> tuple[Path, Path] | None:
    report = ExecutionErrorReport(
        run_id=f"rt_{uuid.uuid4().hex[:12]}",
        started_at=started_at,
        completed_at=datetime.now(UTC),
        duration_seconds=max(
            0.0,
            time.monotonic() - started_monotonic,
        ),
        scenario_name=scenario_name,
        stage=stage,
        error_type=type(error).__name__,
        error_message=(str(error) or type(error).__name__),
    )

    finalization_budget = RequestBudget(
        1,
        finalization_timeout_seconds,
    )

    try:
        return write_execution_error_report(
            report,
            output_dir,
            redact_fields,
            finalization_budget.check_deadline,
        )

    except (
        OSError,
        TypeError,
        ValueError,
        ReportWriteError,
        RequestBudgetError,
    ) as report_error:
        message = _redacted_error_message(
            report_error,
            redact_fields,
        )

        print(f"ERROR: failed to write execution error report: {message}")

        return None
