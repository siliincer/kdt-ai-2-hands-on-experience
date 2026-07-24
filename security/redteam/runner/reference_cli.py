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
    ReferenceCase,
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


def _iteration_count(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("iterations must be an integer") from exc
    if not 1 <= parsed <= 10:
        raise argparse.ArgumentTypeError("iterations must be between 1 and 10")
    return parsed


def _case_id(value: str) -> str:
    if not re.fullmatch(r"[a-z0-9_]+", value):
        raise argparse.ArgumentTypeError("case id must contain lowercase letters, numbers, and _")
    return value


def _select_cases(
    cases: list[ReferenceCase],
    case_id: str | None,
) -> list[ReferenceCase]:
    if case_id is None:
        return cases
    selected = [case for case in cases if case.id == case_id]
    if not selected:
        raise ValueError(f"reference cases do not contain case id: {case_id}")
    return selected


def _case_paths(cases_dir: Path, case_id: str | None) -> list[Path]:
    if case_id is None:
        return sorted(cases_dir.glob("*.yaml"))
    path = cases_dir / f"{case_id}.yaml"
    if not path.is_file():
        raise ValueError(f"reference cases do not contain case id: {case_id}")
    return [path]


def _required_reference_requests(
    config: RedTeamConfig,
    cases: list[ReferenceCase],
) -> int:
    generated = sum(case.generation is not None for case in cases)
    preflight_requests = 1 + len({config.adaptive_attack.model, config.judgment.model})
    generated_iteration_requests = (
        2 * config.adaptive_attack.max_generation_attempts
        + config.adaptive_attack.candidates_per_generation
        - 1
        + config.judgment.max_attempts_per_evaluation
    )
    return preflight_requests + (
        generated * config.adaptive_attack.max_iterations_per_attack * generated_iteration_requests
    )


def _resolve_commit(value: str) -> str:
    return _commit(value)


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
        "--max-iterations",
        type=_iteration_count,
        help=("maximum generated-input iterations per reference case (defaults to config)"),
    )
    parser.add_argument(
        "--case-id",
        type=_case_id,
        help="run only one reference case id",
    )
    parser.add_argument(
        "--agent-source-commit",
        "--source-commit",
        dest="agent_source_commit",
        type=_resolve_commit,
        help="expected Agent subtree revision (defaults to the imported Agent source)",
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
    config = _with_model_overrides(
        load_config(args.config),
        generator_model=args.generator_model,
        judgment_model=args.judgment_model,
    )
    max_iterations = getattr(args, "max_iterations", None)
    if max_iterations is None:
        return config
    raw = config.model_dump(mode="python")
    raw["adaptive_attack"]["max_iterations_per_attack"] = max_iterations
    return RedTeamConfig.model_validate(raw)


async def _run(
    args: argparse.Namespace,
    config: RedTeamConfig | None = None,
) -> int:
    config = config or _load_reference_config(args)
    case_id = getattr(args, "case_id", None)
    case_paths = _case_paths(args.cases_dir, case_id)
    if len(case_paths) > 100:
        raise ValueError("reference campaign supports at most 100 cases")
    try:
        case_set_bytes = sum(path.stat().st_size for path in case_paths)
    except OSError as exc:
        raise ValueError("failed to inspect reference case set") from exc
    if case_set_bytes > MAX_REFERENCE_CASE_SET_BYTES:
        raise ValueError(f"reference campaign case files exceed {MAX_REFERENCE_CASE_SET_BYTES} bytes")
    cases = [load_reference_case(path) for path in case_paths]
    if not cases:
        raise ValueError("reference cases directory is empty")
    cases = _select_cases(cases, case_id)
    generated_cases = sum(case.generation is not None for case in cases)
    planned_iterations = (
        generated_cases * config.adaptive_attack.max_iterations_per_attack + len(cases) - generated_cases
    )
    required_requests = _required_reference_requests(config, cases)
    request_limit = config.execution.max_reference_requests_per_run
    if required_requests > request_limit:
        raise ValueError(
            "reference request budget is smaller than the worst-case execution plan: "
            f"required={required_requests}, configured={request_limit}"
        )
    print(
        f"Plan [reference]: cases={len(cases)}, generated={generated_cases}, "
        f"max_case_runs={planned_iterations}, max_requests={required_requests}"
    )
    scenarios = {
        name: load_scenario(REDTEAM_ROOT / "scenarios" / f"{name}.yaml")
        for name in ("prompt_injection", "tool_governance", "data_confidentiality")
    }
    budget = RequestBudget(
        request_limit,
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
                max_iterations_per_generated_case=(config.adaptive_attack.max_iterations_per_attack),
            )
            agent_source_commit = executor.agent_source_commit
            if (
                args.agent_source_commit is not None
                and executor.resolve_source_commit(args.agent_source_commit) != agent_source_commit
            ):
                raise ValueError("imported Agent checkout does not match --agent-source-commit")
            if executor.agent_source_dirty:
                raise ValueError("imported Agent source directory has local changes")
            result = await run_reference_campaign(
                cases,
                executor,
                metadata_factory=lambda: ReferenceCampaignMetadata(
                    agent_source_commit=agent_source_commit,
                    case_set_kind=(
                        "default"
                        if case_id is None and args.cases_dir.resolve() == (REDTEAM_ROOT / "reference_cases").resolve()
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
                    max_iterations_per_generated_case=(config.adaptive_attack.max_iterations_per_attack),
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
        OSError,
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
        OSError,
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
            finalization_timeout_seconds=(config.execution.report_finalization_timeout_seconds),
        )
        if paths is not None:
            print(f"Error report: {paths[0]} {paths[1]}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
