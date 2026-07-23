"""Run a bounded local model matrix and write one aggregate report."""

from __future__ import annotations

import argparse
import json
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, TypedDict, TypeVar

from security.redteam.config import load_config, load_redact_fields
from security.redteam.models import (
    ComparisonReport,
    ComparisonRun,
    ModelCombinationSummary,
    ModelRoleSummary,
    Verdict,
)
from security.redteam.runner.cli import (
    _CLI_ERRORS,
    DEFAULT_REDACT_FIELDS,
    EXIT_CODES,
    REDTEAM_ROOT,
    _model_name,
    _record_cli_error,
    _redacted_error_message,
    _run_named_scenario,
    _scenario_name,
    _scenario_names,
    _seed,
    _with_model_overrides,
)
from security.redteam.runner.client import RequestBudget, RequestBudgetError
from security.redteam.runner.reporter import ReportWriteError, write_comparison_report

MAX_COMPARISON_RUNS = 100
SEED_PROFILES = {
    "screening": [7, 42, 99],
    "final": [7, 19, 42, 73, 99],
}
T = TypeVar("T", str, int)


class _RunMetrics(TypedDict):
    result_counts: dict[Verdict, int]
    generator_requests: int
    generator_attempts: int
    generator_successes: int
    generator_rejections: int
    generator_failures: int
    target_attempts: int
    target_failures: int
    judgment_attempts: int
    judgment_failures: int
    judgment_disagreements: int
    judgment_uncertain: int
    review_required: bool


def _unique(values: list[T]) -> list[T]:
    return list(dict.fromkeys(values))


def _selected_seeds(
    explicit_seeds: list[int] | None,
    seed_profile: str | None,
    default_seed: int,
) -> list[int]:
    if explicit_seeds and seed_profile:
        raise ValueError("--seed and --seed-profile cannot be combined")
    if seed_profile:
        return list(SEED_PROFILES[seed_profile])
    return _unique(explicit_seeds or [default_seed])


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compare local model combinations")
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
        "--generator-model",
        action="append",
        type=_model_name,
        dest="generator_models",
        help="repeat for each installed generator model",
    )
    parser.add_argument(
        "--target-model",
        action="append",
        type=_model_name,
        dest="target_models",
        help="repeat for each installed Target model",
    )
    parser.add_argument(
        "--judgment-model",
        action="append",
        type=_model_name,
        dest="judgment_models",
        help="repeat for each installed independent judgment model",
    )
    parser.add_argument(
        "--seed",
        action="append",
        type=_seed,
        dest="seeds",
        help="repeat for each generation seed",
    )
    parser.add_argument(
        "--seed-profile",
        choices=sorted(SEED_PROFILES),
        help="use a fixed screening or final seed set; cannot be combined with --seed",
    )
    return parser


def _matrix_size(
    scenarios: tuple[str, ...],
    generator_models: list[str],
    target_models: list[str],
    judgment_models: list[str],
    seeds: list[int],
) -> int:
    role_combinations = sum(
        1
        for generator in generator_models
        for target in target_models
        for judgment in judgment_models
        if len({generator, target, judgment}) == 3
    )
    return len(scenarios) * role_combinations * len(seeds)


def _empty_verdict_counts() -> dict[Verdict, int]:
    return {verdict: 0 for verdict in Verdict}


def _run_metrics(report_path: Path) -> _RunMetrics:
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    if payload.get("report_type") == "execution_error":
        return {
            "result_counts": _empty_verdict_counts(),
            "generator_requests": 0,
            "generator_attempts": 0,
            "generator_successes": 0,
            "generator_rejections": 0,
            "generator_failures": 0,
            "target_attempts": 0,
            "target_failures": 0,
            "judgment_attempts": 0,
            "judgment_failures": 0,
            "judgment_disagreements": 0,
            "judgment_uncertain": 0,
            "review_required": False,
        }

    result_counts = _empty_verdict_counts()
    for result in payload.get("results", []):
        result_counts[Verdict(result["verdict"])] += 1
    attacker = payload.get("attacker_telemetry") or {}
    target = payload.get("llm_telemetry") or {}
    judgment = payload.get("judgment_telemetry") or {}
    return {
        "result_counts": result_counts,
        "generator_requests": attacker.get("requests", 0),
        "generator_attempts": attacker.get("attempts", 0),
        "generator_successes": attacker.get("successes", 0),
        "generator_rejections": (attacker.get("rejected_out_of_scope", 0) + attacker.get("rejected_duplicates", 0)),
        "generator_failures": attacker.get("failures", 0),
        "target_attempts": target.get("attempts", 0),
        "target_failures": target.get("failures", 0),
        "judgment_attempts": judgment.get("attempts", 0),
        "judgment_failures": judgment.get("failures", 0),
        "judgment_disagreements": judgment.get("disagreements", 0),
        "judgment_uncertain": judgment.get("uncertain", 0),
        "review_required": payload.get("review_required", False),
    }


def _model_summaries(runs: list[ComparisonRun]) -> list[ModelRoleSummary]:
    summaries = []
    role_specs: tuple[
        tuple[
            Literal["generator", "target", "judgment"],
            Literal["generator_model", "target_model", "judgment_model"],
        ],
        ...,
    ] = (
        ("generator", "generator_model"),
        ("target", "target_model"),
        ("judgment", "judgment_model"),
    )
    for role, attribute in role_specs:
        models = sorted({getattr(run, attribute) for run in runs})
        for model in models:
            selected = [run for run in runs if getattr(run, attribute) == model]
            verdict_counts = _empty_verdict_counts()
            for run in selected:
                verdict_counts[run.verdict] += 1
            generator_attempts = sum(run.generator_attempts for run in selected)
            target_attempts = sum(run.target_attempts for run in selected)
            judgment_attempts = sum(run.judgment_attempts for run in selected)
            target_result_counts = _empty_verdict_counts()
            for run in selected:
                for verdict, count in run.result_counts.items():
                    target_result_counts[verdict] += count
            target_results = sum(target_result_counts.values())
            judgment_failures = sum(run.judgment_failures for run in selected)
            judgment_decisions = judgment_attempts - judgment_failures
            judgment_disagreements = sum(run.judgment_disagreements for run in selected)
            judgment_uncertain = sum(run.judgment_uncertain for run in selected)
            judgment_agreements = judgment_decisions - judgment_disagreements - judgment_uncertain
            summaries.append(
                ModelRoleSummary(
                    role=role,
                    model=model,
                    total_runs=len(selected),
                    run_verdict_counts=verdict_counts,
                    average_duration_seconds=(sum(run.duration_seconds for run in selected) / len(selected)),
                    generator_success_rate=(
                        sum(run.generator_successes for run in selected) / generator_attempts
                        if role == "generator" and generator_attempts
                        else None
                    ),
                    generator_rejection_rate=(
                        sum(run.generator_rejections for run in selected) / generator_attempts
                        if role == "generator" and generator_attempts
                        else None
                    ),
                    generator_failure_rate=(
                        sum(run.generator_failures for run in selected) / generator_attempts
                        if role == "generator" and generator_attempts
                        else None
                    ),
                    target_contract_pass_rate=(
                        target_result_counts[Verdict.PASS] / target_results
                        if role == "target" and target_results
                        else None
                    ),
                    target_contract_fail_rate=(
                        target_result_counts[Verdict.FAIL] / target_results
                        if role == "target" and target_results
                        else None
                    ),
                    target_contract_error_rate=(
                        target_result_counts[Verdict.ERROR] / target_results
                        if role == "target" and target_results
                        else None
                    ),
                    target_llm_failure_rate=(
                        sum(run.target_failures for run in selected) / target_attempts
                        if role == "target" and target_attempts
                        else None
                    ),
                    judgment_agreement_rate=(
                        judgment_agreements / judgment_decisions if role == "judgment" and judgment_decisions else None
                    ),
                    judgment_disagreement_rate=(
                        judgment_disagreements / judgment_decisions
                        if role == "judgment" and judgment_decisions
                        else None
                    ),
                    judgment_uncertain_rate=(
                        judgment_uncertain / judgment_decisions if role == "judgment" and judgment_decisions else None
                    ),
                    judgment_failure_rate=(
                        judgment_failures / judgment_attempts if role == "judgment" and judgment_attempts else None
                    ),
                )
            )
    return summaries


def _combination_summaries(
    runs: list[ComparisonRun],
) -> list[ModelCombinationSummary]:
    keys = sorted(
        {
            (
                run.scenario_name,
                run.generator_model,
                run.target_model,
                run.judgment_model,
            )
            for run in runs
        }
    )
    summaries = []
    for scenario_name, generator_model, target_model, judgment_model in keys:
        selected = [
            run
            for run in runs
            if (
                run.scenario_name,
                run.generator_model,
                run.target_model,
                run.judgment_model,
            )
            == (scenario_name, generator_model, target_model, judgment_model)
        ]
        verdict_counts = _empty_verdict_counts()
        target_result_counts = _empty_verdict_counts()
        for run in selected:
            verdict_counts[run.verdict] += 1
            for verdict, count in run.result_counts.items():
                target_result_counts[verdict] += count
        observed_verdicts = [verdict for verdict, count in verdict_counts.items() if count > 0]
        generator_attempts = sum(run.generator_attempts for run in selected)
        target_results = sum(target_result_counts.values())
        judgment_attempts = sum(run.judgment_attempts for run in selected)
        judgment_failures = sum(run.judgment_failures for run in selected)
        judgment_decisions = judgment_attempts - judgment_failures
        judgment_disagreements = sum(run.judgment_disagreements for run in selected)
        judgment_uncertain = sum(run.judgment_uncertain for run in selected)
        judgment_agreements = judgment_decisions - judgment_disagreements - judgment_uncertain
        summaries.append(
            ModelCombinationSummary(
                scenario_name=scenario_name,
                generator_model=generator_model,
                target_model=target_model,
                judgment_model=judgment_model,
                seeds=sorted(run.seed for run in selected),
                total_runs=len(selected),
                verdict_counts=verdict_counts,
                stable_verdict=(observed_verdicts[0] if len(observed_verdicts) == 1 else None),
                verdict_consistency_rate=(max(verdict_counts.values()) / len(selected)),
                review_required_rate=(sum(run.review_required for run in selected) / len(selected)),
                average_duration_seconds=(sum(run.duration_seconds for run in selected) / len(selected)),
                generator_success_rate=(
                    sum(run.generator_successes for run in selected) / generator_attempts
                    if generator_attempts
                    else None
                ),
                target_contract_pass_rate=(
                    target_result_counts[Verdict.PASS] / target_results if target_results else None
                ),
                judgment_agreement_rate=(judgment_agreements / judgment_decisions if judgment_decisions else None),
            )
        )
    return summaries


def main() -> int:
    args = _parser().parse_args()
    started_at = datetime.now(UTC)
    started_monotonic = time.monotonic()
    redact_fields = DEFAULT_REDACT_FIELDS | load_redact_fields(args.config)
    finalization_timeout_seconds = 10
    try:
        base_config = load_config(args.config)
        redact_fields = base_config.safety.redact_fields
        finalization_timeout_seconds = base_config.execution.report_finalization_timeout_seconds
        scenarios = _scenario_names(args.scenario)
        generator_models = _unique(args.generator_models or [base_config.adaptive_attack.model])
        target_models = _unique(args.target_models or [base_config.safety.required_ollama_model])
        judgment_models = _unique(getattr(args, "judgment_models", None) or [base_config.judgment.model])
        seed_profile = getattr(args, "seed_profile", None)
        seeds = _selected_seeds(
            args.seeds,
            seed_profile,
            base_config.adaptive_attack.seed,
        )
        total_runs = _matrix_size(
            scenarios,
            generator_models,
            target_models,
            judgment_models,
            seeds,
        )
        if total_runs == 0:
            raise ValueError("comparison has no combination with three distinct models")
        if total_runs > MAX_COMPARISON_RUNS:
            raise ValueError(f"comparison requests {total_runs} runs; maximum is {MAX_COMPARISON_RUNS}")
    except _CLI_ERRORS as exc:
        print(f"ERROR: {_redacted_error_message(exc, redact_fields)}")
        paths = _record_cli_error(
            scenario_name=args.scenario,
            stage="comparison_setup",
            error=exc,
            started_at=started_at,
            started_monotonic=started_monotonic,
            output_dir=args.output_dir,
            redact_fields=redact_fields,
            finalization_timeout_seconds=finalization_timeout_seconds,
        )
        if paths is not None:
            print(f"Error report: {paths[0]} {paths[1]}")
        return 2

    runs: list[ComparisonRun] = []
    exit_codes: list[int] = []
    for generator_model in generator_models:
        for target_model in target_models:
            for judgment_model in judgment_models:
                if len({generator_model, target_model, judgment_model}) != 3:
                    continue
                for seed in seeds:
                    config = _with_model_overrides(
                        base_config,
                        generator_model=generator_model,
                        target_model=target_model,
                        judgment_model=judgment_model,
                        seed=seed,
                    )
                    for scenario_name in scenarios:
                        run_started_at = datetime.now(UTC)
                        run_started_monotonic = time.monotonic()
                        try:
                            verdict, paths = _run_named_scenario(
                                config,
                                scenario_name,
                                args.user_id,
                                args.output_dir,
                            )
                        except _CLI_ERRORS as exc:
                            verdict = Verdict.ERROR
                            error_paths = _record_cli_error(
                                scenario_name=scenario_name,
                                stage="comparison_run",
                                error=exc,
                                started_at=run_started_at,
                                started_monotonic=run_started_monotonic,
                                output_dir=args.output_dir,
                                redact_fields=config.safety.redact_fields,
                                finalization_timeout_seconds=(config.execution.report_finalization_timeout_seconds),
                            )
                            if error_paths is None:
                                message = _redacted_error_message(
                                    exc,
                                    config.safety.redact_fields,
                                )
                                print(f"ERROR [{scenario_name}]: {message}")
                                return 2
                            paths = error_paths
                        duration = max(0.0, time.monotonic() - run_started_monotonic)
                        metrics = _run_metrics(paths[0])
                        runs.append(
                            ComparisonRun(
                                scenario_name=scenario_name,
                                generator_model=generator_model,
                                target_model=target_model,
                                judgment_model=judgment_model,
                                seed=seed,
                                verdict=verdict,
                                duration_seconds=duration,
                                report_json=paths[0].name,
                                report_markdown=paths[1].name,
                                **metrics,
                            )
                        )
                        exit_codes.append(EXIT_CODES[verdict])
                        print(
                            f"{verdict}: {scenario_name} generator={generator_model} "
                            f"target={target_model} judgment={judgment_model} "
                            f"seed={seed}"
                        )

    counts = _empty_verdict_counts()
    for run in runs:
        counts[run.verdict] += 1
    report = ComparisonReport(
        comparison_id=f"comparison_{uuid.uuid4().hex[:12]}",
        started_at=started_at,
        completed_at=datetime.now(UTC),
        duration_seconds=max(0.0, time.monotonic() - started_monotonic),
        requested_scenario=args.scenario,
        total_runs=len(runs),
        verdict_counts=counts,
        runs=runs,
        model_summaries=_model_summaries(runs),
        combination_summaries=_combination_summaries(runs),
    )
    try:
        paths = write_comparison_report(
            report,
            args.output_dir,
            base_config.safety.redact_fields,
            RequestBudget(
                1,
                base_config.execution.report_finalization_timeout_seconds,
            ).check_deadline,
        )
    except (
        OSError,
        TypeError,
        ValueError,
        ReportWriteError,
        RequestBudgetError,
    ) as exc:
        message = _redacted_error_message(exc, base_config.safety.redact_fields)
        print(f"ERROR: failed to write comparison report: {message}")
        return 2
    print(f"Comparison report: {paths[0]} {paths[1]}")
    return max(exit_codes, default=2)


if __name__ == "__main__":
    raise SystemExit(main())
