"""Write redacted machine-readable and human-readable execution reports."""

from __future__ import annotations

import json
import re
from html import escape
from pathlib import Path

from security.redteam.models import ScenarioResult
from security.redteam.runner.sanitizer import contains_sensitive_data, redact

_COMMONMARK_PUNCTUATION = re.compile(r"""([!"#$%&'()*+,\-./:;<=>?@\[\\\]^_`{|}~])""")


def _markdown_safe(value: object) -> str:
    escaped = _COMMONMARK_PUNCTUATION.sub(r"\\\1", str(value))
    return escaped.replace("\r", "\\r").replace("\n", "\\n")


def _markdown_code(value: object) -> str:
    return (
        escape(str(value), quote=True)
        .replace("`", "&#96;")
        .replace("\r", "\\r")
        .replace("\n", "\\n")
    )


def _markdown_report(data: dict) -> str:
    lines = [
        f"# Red Team Report: {_markdown_safe(data['scenario_name'])}",
        "",
        f"- Run ID: `{_markdown_code(data['run_id'])}`",
        f"- Started: `{_markdown_code(data['started_at'])}`",
        f"- Completed: `{_markdown_code(data['completed_at'])}`",
        f"- Duration seconds: `{data['duration_seconds']:.3f}`",
        f"- Target: `{_markdown_code(data['target_origin'])}`",
        f"- Severity: `{_markdown_code(data['severity'])}`",
        f"- Execution mode: `{_markdown_code(data['execution_mode'])}`",
        (
            "- Execution reason: "
            f"{_markdown_safe(data.get('execution_reason') or 'n/a')}"
        ),
        f"- Verdict: `{_markdown_code(data['verdict'])}`",
        "",
    ]
    telemetry = data.get("llm_telemetry")
    if telemetry:
        lines[10:10] = [
            f"- LLM attempts: `{telemetry['attempts']}`",
            f"- LLM successes: `{telemetry['successes']}`",
            f"- LLM failures: `{telemetry['failures']}`",
        ]
    attacker_telemetry = data.get("attacker_telemetry")
    if attacker_telemetry:
        lines[10:10] = [
            f"- Attacker model: `{_markdown_code(attacker_telemetry['model'])}`",
            f"- Attacker requests: `{attacker_telemetry['requests']}`",
            f"- Attacker generations: `{attacker_telemetry['attempts']}`",
            f"- Attacker successes: `{attacker_telemetry['successes']}`",
            f"- Attacker failures: `{attacker_telemetry['failures']}`",
            (
                "- Attacker out-of-scope rejections: "
                f"`{attacker_telemetry['rejected_out_of_scope']}`"
            ),
            (
                "- Attacker duplicate rejections: "
                f"`{attacker_telemetry['rejected_duplicates']}`"
            ),
            (
                "- Attacker rejection reasons: "
                f"`{_markdown_code(attacker_telemetry.get('rejection_reasons', {}))}`"
            ),
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
    lines.extend(["## Results", ""])
    for result in data["results"]:
        generation_seed = result.get("generation_seed")
        generation_strategy = _markdown_safe(result.get("generation_strategy") or "n/a")
        generation_style = _markdown_safe(result.get("generation_style") or "n/a")
        result_evidence = _markdown_safe(", ".join(result["evidence"]) or "none")
        execution_error = _markdown_safe(result.get("execution_error") or "none")
        generation_seed_text = (
            "n/a" if generation_seed is None else str(generation_seed)
        )
        generation_action = _markdown_safe(
            result.get("generation_requested_action") or "n/a"
        )
        generation_target = _markdown_safe(result.get("generation_target") or "n/a")
        generation_polarity = _markdown_safe(result.get("generation_polarity") or "n/a")
        generation_reported = result.get("generation_reported_speech")
        generation_reported_text = (
            "n/a" if generation_reported is None else str(generation_reported)
        )
        lines.extend(
            [
                (
                    f"### {_markdown_safe(result['attack_id'])} / iteration "
                    f"{result['iteration']}: {_markdown_safe(result['verdict'])}"
                ),
                "",
                f"- LLM generated: `{result['generated_by_llm']}`",
                f"- Generation strategy: {generation_strategy}",
                f"- Generation style: {generation_style}",
                f"- Generation seed: {generation_seed_text}",
                f"- Generation action: {generation_action}",
                f"- Generation target: {generation_target}",
                f"- Generation polarity: {generation_polarity}",
                f"- Generation reported speech: {generation_reported_text}",
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
            response_status = _markdown_safe(response.get("status", "n/a"))
            response_reply = _markdown_safe(response.get("reply", "n/a"))
            response_prompt_for = _markdown_safe(response.get("prompt_for") or "none")
            response_thread_id = _markdown_safe(response.get("thread_id", "n/a"))
            response_ui_type = _markdown_safe(
                (response.get("ui") or {}).get("type", "none")
            )
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
                    "",
                ]
            )
    return "\n".join(lines)


def write_report(
    result: ScenarioResult,
    output_dir: Path,
    redact_fields: set[str],
) -> tuple[Path, Path]:
    raw = result.model_dump(mode="json")
    data = redact(raw, redact_fields)
    if not isinstance(data, dict):
        raise TypeError("redacted report must remain a mapping")
    if contains_sensitive_data(data, redact_fields):
        raise ValueError("report still contains a sensitive value after redaction")

    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{result.run_id}-{result.scenario_id}"
    json_path = output_dir / f"{stem}.json"
    markdown_path = output_dir / f"{stem}.md"
    json_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(_markdown_report(data), encoding="utf-8")
    return json_path, markdown_path
