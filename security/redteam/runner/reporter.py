"""Write redacted machine-readable and human-readable execution reports."""

from __future__ import annotations

import json
import os
import re
import tempfile
from collections.abc import Callable
from html import escape
from pathlib import Path

from security.redteam.models import (
    ComparisonReport,
    ExecutionErrorReport,
    ScenarioResult,
)
from security.redteam.runner.reference_campaign import ReferenceCampaignResult
from security.redteam.runner.sanitizer import contains_sensitive_data, redact

_COMMONMARK_PUNCTUATION = re.compile(r"""([!"#$%&'()*+,\-./:;<=>?@\[\\\]^_`{|}~])""")


class ReportWriteError(RuntimeError):
    """Raised when a report pair cannot be finalized on disk."""


def _cleanup_paths(paths: list[Path]) -> None:
    for path in paths:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def _markdown_safe(value: object) -> str:
    escaped = _COMMONMARK_PUNCTUATION.sub(r"\\\1", str(value))
    return escaped.replace("\r", "\\r").replace("\n", "\\n")


def _markdown_code(value: object) -> str:
    return escape(str(value), quote=True).replace("`", "&#96;").replace("\r", "\\r").replace("\n", "\\n")


def _optional_rate(value: float | int | None) -> str:
    return "n/a" if value is None else f"{float(value):.3f}"


def _markdown_report(data: dict) -> str:
    lines = [
        f"# Red Team Report: {_markdown_safe(data['scenario_name'])}",
        "",
        f"- Run ID: `{_markdown_code(data['run_id'])}`",
        f"- Started: `{_markdown_code(data['started_at'])}`",
        f"- Completed: `{_markdown_code(data['completed_at'])}`",
        f"- Duration seconds: `{data['duration_seconds']:.3f}`",
        f"- Target: `{_markdown_code(data['target_origin'])}`",
        f"- Config version: `{data['config_version']}`",
        f"- Scenario version: `{data['scenario_version']}`",
        f"- Scenario type: `{_markdown_code(data['scenario_type'])}`",
        f"- Scenario category: `{_markdown_code(data['scenario_category'])}`",
        f"- Scenario coverage: `{_markdown_code(data['scenario_coverage'])}`",
        f"- Severity: `{_markdown_code(data['severity'])}`",
        f"- Execution mode: `{_markdown_code(data['execution_mode'])}`",
        (f"- Execution reason: {_markdown_safe(data.get('execution_reason') or 'n/a')}"),
        f"- Verdict: `{_markdown_code(data['verdict'])}`",
        "",
    ]
    reproducibility = data.get("reproducibility")
    if reproducibility:
        lines.extend(
            [
                "## Reproducibility",
                "",
                (f"- Generator model: `{_markdown_code(reproducibility['generator_model'])}`"),
                (f"- Generator digest: `{_markdown_code(reproducibility['generator_model_digest'])}`"),
                (f"- Target model: `{_markdown_code(reproducibility['target_model'])}`"),
                (f"- Target digest: `{_markdown_code(reproducibility['target_model_digest'])}`"),
                (f"- Judgment model: `{_markdown_code(reproducibility['judgment_model'])}`"),
                (f"- Judgment digest: `{_markdown_code(reproducibility['judgment_model_digest'])}`"),
                f"- Seed: `{reproducibility['seed']}`",
                (f"- Config SHA-256: `{_markdown_code(reproducibility['config_sha256'])}`"),
                (f"- Scenario SHA-256: `{_markdown_code(reproducibility['scenario_sha256'])}`"),
                (f"- Git commit: `{_markdown_code(reproducibility.get('git_commit') or 'unknown')}`"),
                (f"- Git dirty: `{_markdown_code(reproducibility.get('git_dirty'))}`"),
                "",
            ]
        )
    telemetry = data.get("llm_telemetry")
    if telemetry:
        lines[10:10] = [
            f"- LLM attempts: `{telemetry['attempts']}`",
            f"- LLM successes: `{telemetry['successes']}`",
            f"- LLM failures: `{telemetry['failures']}`",
            (f"- LLM policy marker injections: `{telemetry['policy_marker_injections']}`"),
        ]
    attacker_telemetry = data.get("attacker_telemetry")
    if attacker_telemetry:
        rejected_facts = attacker_telemetry.get(
            "rejected_business_fact_mentions",
            {},
        )
        done_reasons = attacker_telemetry.get("response_done_reasons", {})
        lines[10:10] = [
            f"- Attacker model: `{_markdown_code(attacker_telemetry['model'])}`",
            (f"- Candidate classifier model: `{_markdown_code(attacker_telemetry['classifier_model'])}`"),
            f"- Attacker requests: `{attacker_telemetry['requests']}`",
            f"- Attacker generations: `{attacker_telemetry['attempts']}`",
            f"- Attacker successes: `{attacker_telemetry['successes']}`",
            f"- Attacker failures: `{attacker_telemetry['failures']}`",
            (f"- Attacker out-of-scope rejections: `{attacker_telemetry['rejected_out_of_scope']}`"),
            (f"- Attacker duplicate rejections: `{attacker_telemetry['rejected_duplicates']}`"),
            (f"- Attacker rejection reasons: `{_markdown_code(attacker_telemetry.get('rejection_reasons', {}))}`"),
            (f"- Rejected business facts: `{_markdown_code(rejected_facts)}`"),
            (f"- Rejected intents: `{_markdown_code(attacker_telemetry.get('rejected_intents', {}))}`"),
            (f"- Ollama done reasons: `{_markdown_code(done_reasons)}`"),
            (f"- Maximum Ollama response characters: `{attacker_telemetry.get('max_response_chars', 0)}`"),
        ]
    judgment_telemetry = data.get("judgment_telemetry")
    if judgment_telemetry:
        lines[10:10] = [
            f"- Judgment model: `{_markdown_code(judgment_telemetry['model'])}`",
            f"- Judgment attempts: `{judgment_telemetry['attempts']}`",
            f"- Judgment failures: `{judgment_telemetry['failures']}`",
            f"- Judgment agreements: `{judgment_telemetry['agreements']}`",
            f"- Judgment disagreements: `{judgment_telemetry['disagreements']}`",
            f"- Judgment uncertain: `{judgment_telemetry['uncertain']}`",
            f"- Review required: `{data.get('review_required', False)}`",
        ]
    if data.get("loop_summaries"):
        lines.extend(["## Loop Summary", ""])
        for summary in data["loop_summaries"]:
            lines.append(
                f"- `{_markdown_code(summary['attack_id'])}`: "
                f"{summary['iterations_completed']} iterations, "
                f"best score `{summary['best_score']:.3f}`, "
                f"`{_markdown_code(summary['termination'])}`"
            )
        lines.append("")
    if data.get("workflow_verdicts"):
        lines.extend(["## Workflow Verdicts", ""])
        for workflow_id, verdict in sorted(data["workflow_verdicts"].items()):
            lines.append(f"- `{_markdown_code(workflow_id)}`: `{_markdown_code(verdict)}`")
        lines.append("")
    lines.extend(["## Results", ""])
    for result in data["results"]:
        generation_seed = result.get("generation_seed")
        generation_strategy = _markdown_safe(result.get("generation_strategy") or "n/a")
        generation_style = _markdown_safe(result.get("generation_style") or "n/a")
        result_evidence = _markdown_safe(", ".join(result["evidence"]) or "none")
        execution_error = _markdown_safe(result.get("execution_error") or "none")
        generation_seed_text = "n/a" if generation_seed is None else str(generation_seed)
        generation_action = _markdown_safe(result.get("generation_requested_action") or "n/a")
        generation_target = _markdown_safe(result.get("generation_target") or "n/a")
        generation_polarity = _markdown_safe(result.get("generation_polarity") or "n/a")
        generation_reported = result.get("generation_reported_speech")
        generation_reported_text = "n/a" if generation_reported is None else str(generation_reported)
        generation_facts = ", ".join(sorted(result.get("generation_business_fact_mentions") or []))
        lines.extend(
            [
                (
                    f"### {_markdown_safe(result['attack_id'])} / iteration "
                    f"{result['iteration']}: {_markdown_safe(result['verdict'])}"
                ),
                "",
                (f"- Target workflow: `{_markdown_code(result['target_workflow_id'])}`"),
                f"- LLM generated: `{result['generated_by_llm']}`",
                f"- Generation strategy: {generation_strategy}",
                f"- Generation style: {generation_style}",
                f"- Generation seed: {generation_seed_text}",
                f"- Generation action: {generation_action}",
                f"- Generation target: {generation_target}",
                f"- Generation polarity: {generation_polarity}",
                f"- Generation reported speech: {generation_reported_text}",
                (f"- Generation business facts: {_markdown_safe(generation_facts or 'none')}"),
                f"- Boundary score: `{result['boundary_score']:.3f}`",
                f"- Reason: {_markdown_safe(result['reason'])}",
                f"- Execution error: {execution_error}",
                f"- Evidence: {result_evidence}",
                "",
            ]
        )
        for turn in result["turns"]:
            response = turn.get("response") or {}
            turn_evidence = _markdown_safe(", ".join(turn["evidence"]) or "none")
            model_judgment = turn.get("model_judgment") or {}
            response_status = _markdown_safe(response.get("status", "n/a"))
            response_reply = _markdown_safe(response.get("reply", "n/a"))
            response_prompt_for = _markdown_safe(response.get("prompt_for") or "none")
            response_thread_id = _markdown_safe(response.get("thread_id", "n/a"))
            response_ui_type = _markdown_safe((response.get("ui") or {}).get("type", "none"))
            execution_evidence = response.get("execution_evidence") or {}
            workflow_lines = []
            if execution_evidence:
                tool_paths = ", ".join(execution_evidence.get("tool_request_paths") or [])
                contract_tools = ", ".join(execution_evidence.get("contract_tool_ids") or [])
                tool_requests = ", ".join(
                    (f"{request.get('method')} {request.get('path')}[{','.join(request.get('query_keys') or [])}]")
                    for request in execution_evidence.get("tool_requests") or []
                )
                webhook_steps = ", ".join(
                    ":".join(
                        filter(
                            None,
                            (event.get("event_type"), event.get("step_id")),
                        )
                    )
                    for event in execution_evidence.get("webhooks") or []
                )
                pending_keys = ", ".join(sorted(execution_evidence.get("pending_identifiers") or {}))
                trace = ", ".join(
                    ":".join(filter(None, (entry.get("step_id"), entry.get("route_key"))))
                    for entry in execution_evidence.get("trace") or []
                )
                request_ids = ", ".join(execution_evidence.get("request_ids") or [])
                context_ids = ", ".join(execution_evidence.get("execution_context_ids") or [])
                workflow_lines = [
                    (f"- Observed workflow: `{_markdown_code(execution_evidence['observed_workflow_id'])}`"),
                    (
                        "- Runtime/state status: `"
                        f"{_markdown_code(execution_evidence['runtime_status'])}` / `"
                        f"{_markdown_code(execution_evidence['state_status'])}`"
                    ),
                    (f"- Request IDs: {_markdown_safe(request_ids or 'none')}"),
                    (f"- Execution context IDs: {_markdown_safe(context_ids or 'none')}"),
                    f"- Tool request paths: {_markdown_safe(tool_paths or 'none')}",
                    f"- Tool requests: {_markdown_safe(tool_requests or 'none')}",
                    f"- Contract Tool IDs: {_markdown_safe(contract_tools or 'none')}",
                    f"- Webhook steps: {_markdown_safe(webhook_steps or 'none')}",
                    (f"- Pending identifier fields: {_markdown_safe(pending_keys or 'none')}"),
                    f"- Workflow trace: {_markdown_safe(trace or 'none')}",
                ]
            lines.extend(
                [
                    f"#### Turn {turn['turn']}: {_markdown_safe(turn['verdict'])}",
                    "",
                    f"- Boundary score: `{turn['boundary_score']:.3f}`",
                    f"- Reason: {_markdown_safe(turn['reason'])}",
                    f"- Evidence: {turn_evidence}",
                    f"- Message: {_markdown_safe(turn['message'])}",
                    f"- Agent status: {response_status}",
                    f"- Agent reply: {response_reply}",
                    f"- Prompt state: {response_prompt_for}",
                    f"- Thread ID: {response_thread_id}",
                    f"- UI type: {response_ui_type}",
                    *workflow_lines,
                    (f"- Model judgment: {_markdown_safe(model_judgment.get('outcome', 'n/a'))}"),
                    (f"- Judgment confidence: {_markdown_safe(model_judgment.get('confidence', 'n/a'))}"),
                    (f"- Judgment agrees with rules: {_markdown_safe(turn.get('judgment_agrees_with_rules'))}"),
                    "",
                ]
            )
    return "\n".join(lines)


def _markdown_error_report(data: dict) -> str:
    return "\n".join(
        [
            f"# Local QA Execution Error: {_markdown_safe(data['scenario_name'])}",
            "",
            f"- Run ID: `{_markdown_code(data['run_id'])}`",
            f"- Started: `{_markdown_code(data['started_at'])}`",
            f"- Completed: `{_markdown_code(data['completed_at'])}`",
            f"- Duration seconds: `{data['duration_seconds']:.3f}`",
            f"- Stage: `{_markdown_code(data['stage'])}`",
            f"- Error type: `{_markdown_code(data['error_type'])}`",
            f"- Error message: {_markdown_safe(data['error_message'])}",
            f"- Verdict: `{_markdown_code(data['verdict'])}`",
            "",
        ]
    )


def _markdown_comparison_report(data: dict) -> str:
    counts = data["verdict_counts"]
    lines = [
        f"# Local Model Comparison: {_markdown_safe(data['requested_scenario'])}",
        "",
        f"- Comparison ID: `{_markdown_code(data['comparison_id'])}`",
        f"- Started: `{_markdown_code(data['started_at'])}`",
        f"- Completed: `{_markdown_code(data['completed_at'])}`",
        f"- Duration seconds: `{data['duration_seconds']:.3f}`",
        f"- Total runs: `{data['total_runs']}`",
        f"- PASS: `{counts.get('PASS', 0)}`",
        f"- FAIL: `{counts.get('FAIL', 0)}`",
        f"- ERROR: `{counts.get('ERROR', 0)}`",
        "",
        "## Model Role Summary",
        "",
        "Overall run verdicts are shown in the Runs table. Role summaries use only the evidence produced by that role.",
        "",
        "| Role | Model | Runs | Avg seconds | Primary metric | Rate | Diagnostics |",
        "| --- | --- | ---: | ---: | --- | ---: | --- |",
    ]
    for summary in data["model_summaries"]:
        if summary["role"] == "generator":
            metric_name = "candidate acceptance"
            role_rate = summary.get("generator_success_rate")
            diagnostics = (
                f"rejected={_optional_rate(summary.get('generator_rejection_rate'))}; "
                f"errors={_optional_rate(summary.get('generator_failure_rate'))}"
            )
        elif summary["role"] == "target":
            metric_name = "contract PASS"
            role_rate = summary.get("target_contract_pass_rate")
            diagnostics = (
                f"contract FAIL="
                f"{_optional_rate(summary.get('target_contract_fail_rate'))}; "
                f"contract ERROR="
                f"{_optional_rate(summary.get('target_contract_error_rate'))}; "
                f"LLM errors="
                f"{_optional_rate(summary.get('target_llm_failure_rate'))}"
            )
        else:
            metric_name = "rule agreement"
            role_rate = summary.get("judgment_agreement_rate")
            diagnostics = (
                f"disagree="
                f"{_optional_rate(summary.get('judgment_disagreement_rate'))}; "
                f"uncertain="
                f"{_optional_rate(summary.get('judgment_uncertain_rate'))}; "
                f"errors={_optional_rate(summary.get('judgment_failure_rate'))}"
            )
        role_rate_text = "n/a" if role_rate is None else f"{role_rate:.3f}"
        lines.append(
            f"| {summary['role']} | {_markdown_safe(summary['model'])} "
            f"| {summary['total_runs']} | {summary['average_duration_seconds']:.3f} "
            f"| {metric_name} | {role_rate_text} | {diagnostics} |"
        )
    lines.extend(
        [
            "",
            "## Seed Stability",
            "",
            (
                "A stable verdict means every listed seed produced the same overall "
                "verdict. Stable FAIL is not a deployment candidate."
            ),
            "",
            (
                "| Scenario | Generator | Target | Judgment | Seeds | Stability "
                "| Consistency | Review | Gen acceptance | Contract PASS "
                "| Rule agreement | Avg seconds |"
            ),
            ("| --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |"),
        ]
    )
    for summary in data["combination_summaries"]:
        stable_verdict = summary.get("stable_verdict")
        stability = f"stable {stable_verdict}" if stable_verdict else "mixed"
        seeds = ",".join(str(seed) for seed in summary["seeds"])
        lines.append(
            f"| {_markdown_safe(summary['scenario_name'])} "
            f"| {_markdown_safe(summary['generator_model'])} "
            f"| {_markdown_safe(summary['target_model'])} "
            f"| {_markdown_safe(summary['judgment_model'])} "
            f"| {_markdown_safe(seeds)} | {stability} "
            f"| {summary['verdict_consistency_rate']:.3f} "
            f"| {summary['review_required_rate']:.3f} "
            f"| {_optional_rate(summary.get('generator_success_rate'))} "
            f"| {_optional_rate(summary.get('target_contract_pass_rate'))} "
            f"| {_optional_rate(summary.get('judgment_agreement_rate'))} "
            f"| {summary['average_duration_seconds']:.3f} |"
        )
    lines.extend(
        [
            "",
            "## Runs",
            "",
            (
                "| Scenario | Generator | Target | Judgment | Seed | Verdict | Seconds "
                "| Gen success | Target LLM errors | Judge disagreements "
                "| Review | Report |"
            ),
            ("| --- | --- | --- | --- | ---: | --- | ---: | ---: | ---: | ---: | --- | --- |"),
        ]
    )
    for run in data["runs"]:
        report = _markdown_safe(run["report_markdown"])
        lines.append(
            f"| {_markdown_safe(run['scenario_name'])} "
            f"| {_markdown_safe(run['generator_model'])} "
            f"| {_markdown_safe(run['target_model'])} "
            f"| {_markdown_safe(run['judgment_model'])} "
            f"| {run['seed']} | {run['verdict']} "
            f"| {run['duration_seconds']:.3f} "
            f"| {run['generator_successes']}/{run['generator_attempts']} "
            f"| {run['target_failures']}/{run['target_attempts']} "
            f"| {run['judgment_disagreements']}/{run['judgment_attempts']} "
            f"| {run['review_required']} "
            f"| `{report}` |"
        )
    lines.append("")
    return "\n".join(lines)


def _redacted_data(raw: dict, redact_fields: set[str]) -> dict:
    data = redact(raw, redact_fields)
    if not isinstance(data, dict):
        raise TypeError("redacted report must remain a mapping")
    if contains_sensitive_data(data, redact_fields):
        raise ValueError("report still contains a sensitive value after redaction")
    return data


def _write_report_files(
    stem: str,
    data: dict,
    markdown_text: str,
    output_dir: Path,
    check_deadline: Callable[[], None],
) -> tuple[Path, Path]:
    json_text = (
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    json_path = output_dir / f"{stem}.json"
    markdown_path = output_dir / f"{stem}.md"
    manifest_path = output_dir / f"{stem}.complete"
    manifest_text = (
        json.dumps(
            {
                "status": "complete",
                "files": [json_path.name, markdown_path.name],
            },
            sort_keys=True,
        )
        + "\n"
    )

    temporary_paths = []
    installed_paths = []
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        if any(path.exists() for path in (json_path, markdown_path, manifest_path)):
            raise FileExistsError("report output already exists")
        for destination, content in (
            (json_path, json_text),
            (markdown_path, markdown_text),
            (manifest_path, manifest_text),
        ):
            descriptor, temporary_name = tempfile.mkstemp(
                dir=output_dir,
                prefix=f".{destination.name}.",
            )
            temporary_path = Path(temporary_name)
            temporary_paths.append(temporary_path)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
        for temporary_path, destination in zip(
            temporary_paths,
            (json_path, markdown_path, manifest_path),
            strict=True,
        ):
            check_deadline()
            os.replace(temporary_path, destination)
            installed_paths.append(destination)
        directory_descriptor = os.open(output_dir, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except BaseException as exc:
        _cleanup_paths([*temporary_paths, *installed_paths])
        if isinstance(exc, OSError):
            raise ReportWriteError("failed to finalize report files") from exc
        raise
    return json_path, markdown_path


def write_report(
    result: ScenarioResult,
    output_dir: Path,
    redact_fields: set[str],
    deadline_check: Callable[[], None] | None = None,
) -> tuple[Path, Path]:
    check_deadline = deadline_check or (lambda: None)
    check_deadline()
    raw = result.model_dump(mode="json")
    data = _redacted_data(raw, redact_fields)
    check_deadline()
    markdown_text = _markdown_report(data)
    check_deadline()

    stem = f"{result.run_id}-{result.scenario_id}"
    return _write_report_files(
        stem,
        data,
        markdown_text,
        output_dir,
        check_deadline,
    )


def write_execution_error_report(
    result: ExecutionErrorReport,
    output_dir: Path,
    redact_fields: set[str],
    deadline_check: Callable[[], None] | None = None,
) -> tuple[Path, Path]:
    check_deadline = deadline_check or (lambda: None)
    check_deadline()
    data = _redacted_data(result.model_dump(mode="json"), redact_fields)
    check_deadline()
    markdown = _markdown_error_report(data)
    check_deadline()
    return _write_report_files(
        f"{result.run_id}-execution_error",
        data,
        markdown,
        output_dir,
        check_deadline,
    )


def write_comparison_report(
    result: ComparisonReport,
    output_dir: Path,
    redact_fields: set[str],
    deadline_check: Callable[[], None] | None = None,
) -> tuple[Path, Path]:
    check_deadline = deadline_check or (lambda: None)
    check_deadline()
    data = _redacted_data(result.model_dump(mode="json"), redact_fields)
    check_deadline()
    markdown = _markdown_comparison_report(data)
    check_deadline()
    return _write_report_files(
        result.comparison_id,
        data,
        markdown,
        output_dir,
        check_deadline,
    )


def _markdown_reference_campaign(data: dict) -> str:
    totals = data["totals"]
    metadata = data["metadata"]
    generator_telemetry = metadata["generator_telemetry"]
    judgment_telemetry = metadata["judgment_telemetry"]
    lines = [
        "# Reference Campaign Report",
        "",
        f"- Campaign ID: `{_markdown_code(data['campaign_id'])}`",
        (f"- Agent source commit: `{_markdown_code(metadata['agent_source_commit'])}`"),
        (f"- Runner commit: `{_markdown_code(metadata.get('runner_git_commit') or 'unknown')}`"),
        f"- Runner dirty: `{_markdown_code(metadata.get('runner_git_dirty'))}`",
        f"- Case set kind: `{_markdown_code(metadata['case_set_kind'])}`",
        f"- Config SHA-256: `{_markdown_code(metadata['config_sha256'])}`",
        f"- Case set SHA-256: `{_markdown_code(metadata['case_set_sha256'])}`",
        (
            "- Generator model: "
            f"`{_markdown_code(metadata['generator_model'])}` "
            f"(`{_markdown_code(metadata['generator_model_digest'])}`)"
        ),
        (
            "- Judgment model: "
            f"`{_markdown_code(metadata['judgment_model'])}` "
            f"(`{_markdown_code(metadata['judgment_model_digest'])}`)"
        ),
        (
            "- Generator attempts/successes/failures: "
            f"`{generator_telemetry['attempts']}` / "
            f"`{generator_telemetry['successes']}` / "
            f"`{generator_telemetry['failures']}`"
        ),
        (
            "- Judgment attempts/successes/failures: "
            f"`{judgment_telemetry['attempts']}` / "
            f"`{judgment_telemetry['successes']}` / "
            f"`{judgment_telemetry['failures']}`"
        ),
        (f"- Maximum adaptive iterations per generated case: `{metadata['max_iterations_per_generated_case']}`"),
        f"- Started: `{_markdown_code(data['started_at'])}`",
        f"- Completed: `{_markdown_code(data['completed_at'])}`",
        f"- Requested cases: `{data['requested_cases']}`",
        f"- Executed: `{totals['executed']}`",
        f"- Not supported: `{totals['not_supported']}`",
        f"- Not executed: `{totals['not_executed']}`",
        f"- PASS: `{totals['PASS']}`",
        f"- FAIL: `{totals['FAIL']}`",
        f"- ERROR: `{totals['ERROR']}`",
        f"- Review required: `{totals['review_required']}`",
        "",
    ]
    if metadata["case_set_kind"] == "custom":
        lines.extend(
            [
                "Custom case sets are exploratory runs and are not completion "
                "evidence for the default workflow coverage manifest.",
                "",
            ]
        )
    lines.extend(
        [
            "## Cases",
            "",
            "| Case | Workflow | Status | Result | Rule | Model | Iterations | Steps "
            "| Rejections | Error stage | Error reason | Review |",
            "| --- | --- | --- | --- | --- | --- | ---: | --- | --- | --- | --- | --- |",
        ]
    )
    for entry in data["entries"]:
        evaluation = entry.get("evaluation") or {}
        rule_evaluation = entry.get("rule_evaluation") or evaluation
        judgment = entry.get("model_judgment") or {}
        adaptive_attempts = entry.get("adaptive_attempts") or []
        generated = (entry.get("case_contract") or {}).get("generation") is not None
        iteration_count = len(adaptive_attempts) if generated else "n/a"
        steps = entry.get("steps") or []
        operations = ", ".join(step["operation"] for step in steps)
        rejections = ", ".join(step["rejection_code"] for step in steps if step.get("rejection_code") is not None)
        lines.append(
            f"| `{_markdown_code(entry['case_id'])}` "
            f"| `{_markdown_code(entry['workflow_id'])}` "
            f"| `{_markdown_code(entry['status'])}` "
            f"| `{_markdown_code(evaluation.get('verdict', 'n/a'))}` "
            f"| `{_markdown_code(rule_evaluation.get('verdict', 'n/a'))}` "
            f"| `{_markdown_code(judgment.get('outcome', 'n/a'))}` "
            f"| {iteration_count} "
            f"| `{_markdown_code(operations or 'n/a')}` "
            f"| `{_markdown_code(rejections or 'n/a')}` "
            f"| `{_markdown_code(entry.get('error_stage') or 'n/a')}` "
            f"| {_markdown_safe(entry.get('error_reason') or 'n/a')} "
            f"| `{entry['review_required']}` |"
        )
    adaptive_entries = [entry for entry in data["entries"] if entry.get("adaptive_attempts")]
    if adaptive_entries:
        lines.extend(
            [
                "",
                "## Adaptive Iterations",
                "",
                (
                    "Each iteration uses a fresh Agent testbed. The next candidate "
                    "receives the prior response and evaluation as bounded feedback."
                ),
                "",
                "| Case | Iteration | Candidate | Style | Strategy | Rule | Score | Model | Review | Error |",
                "| --- | ---: | --- | --- | --- | --- | ---: | --- | --- | --- |",
            ]
        )
        for entry in adaptive_entries:
            for attempt in entry["adaptive_attempts"]:
                candidate = attempt.get("candidate") or {}
                rule_evaluation = attempt.get("rule_evaluation") or attempt["evaluation"]
                judgment = attempt.get("model_judgment") or {}
                lines.append(
                    f"| `{_markdown_code(entry['case_id'])}` "
                    f"| {attempt['iteration']} "
                    f"| {_markdown_safe(candidate.get('message') or 'n/a')} "
                    f"| {_markdown_safe(candidate.get('style') or 'n/a')} "
                    f"| {_markdown_safe(candidate.get('strategy') or 'n/a')} "
                    f"| `{_markdown_code(rule_evaluation.get('verdict', 'n/a'))}` "
                    f"| {attempt['boundary_score']:.3f} "
                    f"| `{_markdown_code(judgment.get('outcome', 'n/a'))}` "
                    f"| `{attempt['review_required']}` "
                    f"| {_markdown_safe(attempt.get('error_reason') or 'n/a')} |"
                )
    lines.append("")
    return "\n".join(lines)


def write_reference_campaign_report(
    result: ReferenceCampaignResult,
    output_dir: Path,
    redact_fields: set[str],
    deadline_check: Callable[[], None] | None = None,
) -> tuple[Path, Path]:
    check_deadline = deadline_check or (lambda: None)
    check_deadline()
    data = _redacted_data(
        result.model_dump(
            mode="json",
            exclude={"entries": {"__all__": {"responses"}}},
        ),
        redact_fields,
    )
    data["report_schema_version"] = 3
    check_deadline()
    markdown = _markdown_reference_campaign(data)
    check_deadline()
    return _write_report_files(
        result.campaign_id,
        data,
        markdown,
        output_dir,
        check_deadline,
    )
