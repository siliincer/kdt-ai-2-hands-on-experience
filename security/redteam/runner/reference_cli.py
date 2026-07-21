"""Run Agent reference cases with separate local generation and judgment models."""

from __future__ import annotations

import argparse
import asyncio
import re
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from security.redteam.config import (
    RedTeamConfig,
    load_config,
    load_redact_fields,
    load_scenario,
)
from security.redteam.runner.agent_reference import AgentReferenceExecutor
from security.redteam.runner.attacker import OllamaAttackGenerator
from security.redteam.runner.cli import (
    DEFAULT_REDACT_FIELDS,
    _canonical_sha256,
    _git_state,
    _model_name,
    _record_cli_error,
    _redacted_error_message,
    _with_model_overrides,
)
from security.redteam.runner.client import RequestBudget
from security.redteam.runner.judge import OllamaResponseJudge
from security.redteam.runner.managed_agent import (
    ManagedAgentError,
    require_ollama_models,
)
from security.redteam.runner.reference_campaign import (
    ReferenceCampaignMetadata,
    run_reference_campaign,
)
from security.redteam.runner.reference_cases import (
    MAX_REFERENCE_CASE_SET_BYTES,
    load_reference_case,
)
from security.redteam.runner.reporter import (
    ReportWriteError,
    write_reference_campaign_report,
)

REDTEAM_ROOT = Path(__file__).resolve().parents[1]


def _commit(value: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{7,64}", value):
        raise argparse.ArgumentTypeError("Agent source commit must be a Git object id")
    return value


def _source_commit() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "origin/main"],
        cwd=REDTEAM_ROOT.parents[1],
        check=True,
        capture_output=True,
        text=True,
        timeout=5,
    )
    return _commit(completed.stdout.strip())


def _resolve_commit(value: str) -> str:
    candidate = _commit(value)
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--verify", f"{candidate}^{{commit}}"],
            cwd=REDTEAM_ROOT.parents[1],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except subprocess.SubprocessError as exc:
        raise argparse.ArgumentTypeError(
            "Agent source commit does not exist in this repository"
        ) from exc
    return _commit(completed.stdout.strip())


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run local Agent reference cases and write one campaign report",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=REDTEAM_ROOT / "config.example.yaml",
    )
    parser.add_argument(
        "--cases-dir",
        type=Path,
        default=REDTEAM_ROOT / "reference_cases",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REDTEAM_ROOT / "reports",
    )
    parser.add_argument("--generator-model", type=_model_name)
    parser.add_argument("--judgment-model", type=_model_name)
    parser.add_argument(
        "--agent-source-commit",
        "--source-commit",
        dest="agent_source_commit",
        type=_resolve_commit,
        help="Git commit containing the Agent testbeds (defaults to origin/main)",
    )
    return parser


def _error_stage(error: Exception) -> str:
    if isinstance(error, ReportWriteError):
        return "report_finalization"
    if isinstance(error, ManagedAgentError):
        return "model_preflight"
    if isinstance(error, RuntimeError) and "Agent" in str(error):
        return "agent_import"
    if isinstance(error, (FileNotFoundError, ValidationError, ValueError)):
        return "input_validation"
    return "reference_campaign"


def _load_reference_config(args: argparse.Namespace) -> RedTeamConfig:
    return _with_model_overrides(
        load_config(args.config),
        generator_model=args.generator_model,
        judgment_model=args.judgment_model,
    )


async def _run(
    args: argparse.Namespace,
    config: RedTeamConfig | None = None,
) -> int:
    config = config or _load_reference_config(args)
    case_paths = sorted(args.cases_dir.glob("*.yaml"))
    if len(case_paths) > 100:
        raise ValueError("reference campaign supports at most 100 cases")
    case_set_bytes = sum(path.stat().st_size for path in case_paths)
    if case_set_bytes > MAX_REFERENCE_CASE_SET_BYTES:
        raise ValueError(
            f"reference campaign case files exceed {MAX_REFERENCE_CASE_SET_BYTES} bytes"
        )
    cases = [load_reference_case(path) for path in case_paths]
    if not cases:
        raise ValueError("reference cases directory is empty")
    scenarios = {
        name: load_scenario(REDTEAM_ROOT / "scenarios" / f"{name}.yaml")
        for name in ("prompt_injection", "tool_governance", "data_confidentiality")
    }
    budget = RequestBudget(
        config.execution.max_requests_per_run,
        config.execution.max_run_seconds,
    )
    model_digests = require_ollama_models(
        config,
        budget,
        {config.adaptive_attack.model, config.judgment.model},
    )
    runner_git_commit, runner_git_dirty = _git_state()
    config_sha256 = _canonical_sha256(config)
    case_set_sha256 = _canonical_sha256(cases)
    agent_source_commit = (
        args.agent_source_commit
        if args.agent_source_commit is not None
        else _source_commit()
    )
    with OllamaAttackGenerator(
        config.adaptive_attack,
        budget,
        classifier_model=config.judgment.model,
    ) as generator:
        with OllamaResponseJudge(config.judgment, budget) as judge:
            executor = AgentReferenceExecutor(
                generator,
                judge,
                scenarios,
                config.safety.redact_fields,
                budget,
            )
            if executor.agent_source_commit != agent_source_commit:
                raise ValueError(
                    "imported Agent checkout does not match --agent-source-commit"
                )
            if executor.agent_source_dirty:
                raise ValueError("imported Agent source directory has local changes")
            result = await run_reference_campaign(
                cases,
                executor,
                metadata_factory=lambda: ReferenceCampaignMetadata(
                    agent_source_commit=agent_source_commit,
                    case_set_kind=(
                        "default"
                        if args.cases_dir.resolve()
                        == (REDTEAM_ROOT / "reference_cases").resolve()
                        else "custom"
                    ),
                    runner_git_commit=runner_git_commit,
                    runner_git_dirty=runner_git_dirty,
                    config_sha256=config_sha256,
                    case_set_sha256=case_set_sha256,
                    generator_model=config.adaptive_attack.model,
                    generator_model_digest=model_digests[config.adaptive_attack.model],
                    judgment_model=config.judgment.model,
                    judgment_model_digest=model_digests[config.judgment.model],
                    generator_telemetry=generator.telemetry(),
                    judgment_telemetry=judge.telemetry(),
                ),
                deadline_check=budget.check_deadline,
                remaining_seconds=lambda: budget.remaining_seconds,
                timeout_entry_factory=executor.timeout_entry,
            )
    paths = write_reference_campaign_report(
        result,
        args.output_dir,
        config.safety.redact_fields,
        RequestBudget(
            1,
            config.execution.report_finalization_timeout_seconds,
        ).check_deadline,
    )
    print(f"Campaign: {result.campaign_id}")
    print(f"Totals: {result.totals}")
    print(f"Reports: {paths[0]} {paths[1]}")
    if result.totals["ERROR"] or result.totals["not_supported"]:
        return 2
    if result.totals["FAIL"] or result.totals["review_required"]:
        return 1
    return 0


def main() -> int:
    args = _parser().parse_args()
    started_at = datetime.now(UTC)
    started_monotonic = time.monotonic()
    initial_redact_fields = DEFAULT_REDACT_FIELDS | load_redact_fields(args.config)
    try:
        config = _load_reference_config(args)
    except (
        FileNotFoundError,
        RuntimeError,
        ValidationError,
        ValueError,
    ) as exc:
        print(f"ERROR: {_redacted_error_message(exc, initial_redact_fields)}")
        paths = _record_cli_error(
            scenario_name="reference_campaign",
            stage="config_loading",
            error=exc,
            started_at=started_at,
            started_monotonic=started_monotonic,
            output_dir=args.output_dir,
            redact_fields=initial_redact_fields,
        )
        if paths is not None:
            print(f"Error report: {paths[0]} {paths[1]}")
        return 2
    try:
        return asyncio.run(_run(args, config))
    except (
        FileNotFoundError,
        ReportWriteError,
        RuntimeError,
        subprocess.SubprocessError,
        ValidationError,
        ValueError,
    ) as exc:
        redact_fields = config.safety.redact_fields
        print(f"ERROR: {_redacted_error_message(exc, redact_fields)}")
        paths = _record_cli_error(
            scenario_name="reference_campaign",
            stage=_error_stage(exc),
            error=exc,
            started_at=started_at,
            started_monotonic=started_monotonic,
            output_dir=args.output_dir,
            redact_fields=redact_fields,
            finalization_timeout_seconds=(
                config.execution.report_finalization_timeout_seconds
            ),
        )
        if paths is not None:
            print(f"Error report: {paths[0]} {paths[1]}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
