"""Command-line entry point for local adaptive QA scenarios."""

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

import httpx
from pydantic import BaseModel, ValidationError

from security.redteam.config import (
    RedTeamConfig,
    load_config,
    load_redact_fields,
    load_scenario,
)
from security.redteam.models import (
    ExecutionErrorReport,
    ReproducibilityMetadata,
    Scenario,
    Verdict,
)
from security.redteam.runner.attacker import OllamaAttackGenerator
from security.redteam.runner.client import (
    AgentClient,
    RequestBudget,
    RequestBudgetError,
)
from security.redteam.runner.judge import OllamaResponseJudge
from security.redteam.runner.managed_agent import ManagedAgentError, managed_agent
from security.redteam.runner.reporter import (
    ReportWriteError,
    write_execution_error_report,
    write_report,
)
from security.redteam.runner.sanitizer import redact
from security.redteam.runner.service import SafetyPolicyError, run_scenario

REDTEAM_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = REDTEAM_ROOT.parents[1]
EXIT_CODES = {
    Verdict.PASS: 0,
    Verdict.FAIL: 1,
    Verdict.ERROR: 2,
}
REGRESSION_SCENARIOS = (
    "prompt_injection",
    "approval_bypass",
    "tool_governance",
    "data_confidentiality",
    "risk_manipulation",
    "audit_log_tampering",
    "multi_step_attack",
)
ALL_SCENARIOS = (*REGRESSION_SCENARIOS, "conversation_state")
SCENARIO_PROFILES = {
    "all": ALL_SCENARIOS,
    "regression": REGRESSION_SCENARIOS,
}
DEFAULT_REDACT_FIELDS = {"account_number", "authorization", "cookie", "token"}


def _redacted_error_message(error: object, redact_fields: set[str]) -> str:
    message = str(error) or type(error).__name__
    redacted = redact(message, redact_fields)
    return redacted if isinstance(redacted, str) else type(error).__name__


def _scenario_name(value: str) -> str:
    if not re.fullmatch(r"[a-z0-9_]+", value):
        raise argparse.ArgumentTypeError(
            "scenario must contain lowercase letters and _"
        )
    return value


def _model_name(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}", value):
        raise argparse.ArgumentTypeError("model contains unsupported characters")
    return value


def _seed(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("seed must be an integer") from exc
    if not 0 <= parsed <= 2_147_483_647:
        raise argparse.ArgumentTypeError("seed must be between 0 and 2147483647")
    return parsed


def _with_model(config: RedTeamConfig, model: str | None) -> RedTeamConfig:
    return _with_model_overrides(config, generator_model=model)


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
        raise ValueError(
            "--model is disabled; generator, Target, and judgment models must differ"
        )

    adaptive_updates = {}
    if generator_model is not None:
        adaptive_updates["model"] = generator_model
    if seed is not None:
        adaptive_updates["seed"] = seed
    safety_updates = (
        {"required_ollama_model": target_model} if target_model is not None else {}
    )
    judgment_updates = {"model": judgment_model} if judgment_model is not None else {}
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
        if item is None or isinstance(item, (str, int, float, bool)):
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
            ["git", "rev-parse", "HEAD"],
            cwd=REPOSITORY_ROOT,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=REPOSITORY_ROOT,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None, None
    if not re.fullmatch(r"[0-9a-f]{40,64}", commit):
        return None, None
    return commit, bool(status.strip())


def _reproducibility_metadata(
    config: RedTeamConfig,
    scenario: Scenario,
    model_digests: dict[str, str],
) -> ReproducibilityMetadata:
    generator_model = config.adaptive_attack.model
    target_model = config.safety.required_ollama_model
    judgment_model = config.judgment.model
    git_commit, git_dirty = _git_state()
    return ReproducibilityMetadata(
        generator_model=generator_model,
        generator_model_digest=model_digests[generator_model],
        target_model=target_model,
        target_model_digest=model_digests[target_model],
        judgment_model=judgment_model,
        judgment_model_digest=model_digests[judgment_model],
        seed=config.adaptive_attack.seed,
        config_sha256=_canonical_sha256(config.model_dump(mode="python")),
        scenario_sha256=_canonical_sha256(scenario.model_dump(mode="python")),
        git_commit=git_commit,
        git_dirty=git_dirty,
    )


def _scenario_names(value: str) -> tuple[str, ...]:
    return SCENARIO_PROFILES.get(value, (value,))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run local adaptive QA scenarios")
    parser.add_argument(
        "scenario",
        type=_scenario_name,
        help="scenario name or profile: all, regression",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=REDTEAM_ROOT / "config.example.yaml",
    )
    parser.add_argument("--user-id", default="user_001")
    parser.add_argument("--output-dir", type=Path, default=REDTEAM_ROOT / "reports")
    parser.add_argument(
        "--model",
        type=_model_name,
        help="deprecated; use separate role-specific model options",
    )
    parser.add_argument(
        "--generator-model",
        type=_model_name,
        help="installed local Ollama model used to generate inputs",
    )
    parser.add_argument(
        "--target-model",
        type=_model_name,
        help="installed local Ollama model used by the Target Agent",
    )
    parser.add_argument(
        "--judgment-model",
        type=_model_name,
        help="installed local Ollama model used for independent judgment",
    )
    parser.add_argument(
        "--seed",
        type=_seed,
        help="override the configured generation seed",
    )
    return parser


def _run_named_scenario(
    config: RedTeamConfig,
    scenario_name: str,
    user_id: str,
    output_dir: Path,
) -> tuple[Verdict, tuple[Path, Path]]:
    scenario_path = REDTEAM_ROOT / "scenarios" / f"{scenario_name}.yaml"
    scenario = load_scenario(scenario_path)
    run_started_at = datetime.now(UTC)
    run_started_monotonic = time.monotonic()
    budget = RequestBudget(
        config.execution.max_requests_per_run,
        config.execution.max_run_seconds,
    )
    with managed_agent(config, budget) as model_digests:
        with AgentClient(config.target, budget) as client:
            with OllamaAttackGenerator(
                config.adaptive_attack,
                budget,
                classifier_model=config.judgment.model,
            ) as attacker:
                with OllamaResponseJudge(config.judgment, budget) as judge:
                    result = run_scenario(
                        config,
                        scenario,
                        client,
                        user_id,
                        attacker,
                        judge,
                        run_started_at=run_started_at,
                        run_started_monotonic=run_started_monotonic,
                    )
    result = result.model_copy(
        update={
            "reproducibility": _reproducibility_metadata(
                config,
                scenario,
                model_digests,
            )
        }
    )
    finalization_budget = RequestBudget(
        1,
        config.execution.report_finalization_timeout_seconds,
    )
    paths = write_report(
        result,
        output_dir,
        config.safety.redact_fields,
        finalization_budget.check_deadline,
    )
    return result.verdict, paths


_CLI_ERRORS = (
    FileNotFoundError,
    ValidationError,
    ValueError,
    SafetyPolicyError,
    ManagedAgentError,
    ReportWriteError,
    httpx.HTTPError,
    RuntimeError,
)


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
        duration_seconds=max(0.0, time.monotonic() - started_monotonic),
        scenario_name=scenario_name,
        stage=stage,
        error_type=type(error).__name__,
        error_message=str(error) or type(error).__name__,
    )
    finalization_budget = RequestBudget(1, finalization_timeout_seconds)
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
        message = _redacted_error_message(report_error, redact_fields)
        print(f"ERROR: failed to write execution error report: {message}")
        return None


def main() -> int:
    args = _parser().parse_args()
    config_started_at = datetime.now(UTC)
    config_started_monotonic = time.monotonic()
    initial_redact_fields = DEFAULT_REDACT_FIELDS | load_redact_fields(args.config)
    try:
        config = _with_model_overrides(
            load_config(args.config),
            model=getattr(args, "model", None),
            generator_model=getattr(args, "generator_model", None),
            target_model=getattr(args, "target_model", None),
            judgment_model=getattr(args, "judgment_model", None),
            seed=getattr(args, "seed", None),
        )
    except _CLI_ERRORS as exc:
        print(f"ERROR: {_redacted_error_message(exc, initial_redact_fields)}")
        paths = _record_cli_error(
            scenario_name=args.scenario,
            stage="config_loading",
            error=exc,
            started_at=config_started_at,
            started_monotonic=config_started_monotonic,
            output_dir=args.output_dir,
            redact_fields=initial_redact_fields,
        )
        if paths is not None:
            print(f"Error report: {paths[0]} {paths[1]}")
        return 2

    exit_codes: list[int] = []
    for scenario_name in _scenario_names(args.scenario):
        scenario_started_at = datetime.now(UTC)
        scenario_started_monotonic = time.monotonic()
        try:
            verdict, paths = _run_named_scenario(
                config,
                scenario_name,
                args.user_id,
                args.output_dir,
            )
        except _CLI_ERRORS as exc:
            message = _redacted_error_message(exc, config.safety.redact_fields)
            print(f"ERROR [{scenario_name}]: {message}")
            paths = _record_cli_error(
                scenario_name=scenario_name,
                stage="scenario_execution",
                error=exc,
                started_at=scenario_started_at,
                started_monotonic=scenario_started_monotonic,
                output_dir=args.output_dir,
                redact_fields=config.safety.redact_fields,
                finalization_timeout_seconds=(
                    config.execution.report_finalization_timeout_seconds
                ),
            )
            if paths is not None:
                print(f"Error report: {paths[0]} {paths[1]}")
            exit_codes.append(2)
            continue

        print(f"{verdict}: {scenario_name}")
        print(f"Reports: {paths[0]} {paths[1]}")
        exit_codes.append(EXIT_CODES[verdict])

    return max(exit_codes, default=2)


if __name__ == "__main__":
    raise SystemExit(main())
