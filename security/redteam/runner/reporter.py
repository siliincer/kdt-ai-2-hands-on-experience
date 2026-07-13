"""Write redacted machine-readable and human-readable execution reports."""

from __future__ import annotations

import json
import re
from pathlib import Path

from security.redteam.models import ScenarioResult

_REDACTED = "[REDACTED]"
_LONG_NUMBER = re.compile(r"\b\d{10,16}\b")
_HYPHENATED_NUMBER = re.compile(r"\b\d{2,6}(?:-\d{2,6}){1,3}\b")
_BEARER_TOKEN = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")


def _redact_hyphenated_number(match: re.Match[str]) -> str:
    digit_count = sum(character.isdigit() for character in match.group())
    return _REDACTED if digit_count >= 9 else match.group()


def redact(value: object, fields: set[str]) -> object:
    normalized_fields = {field.lower() for field in fields}
    if isinstance(value, dict):
        return {
            key: _REDACTED
            if key.lower() in normalized_fields
            else redact(item, normalized_fields)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item, normalized_fields) for item in value]
    if isinstance(value, str):
        value = _LONG_NUMBER.sub(_REDACTED, value)
        value = _HYPHENATED_NUMBER.sub(_redact_hyphenated_number, value)
        return _BEARER_TOKEN.sub(f"Bearer {_REDACTED}", value)
    return value


def _markdown_report(data: dict) -> str:
    lines = [
        f"# Red Team Report: {data['scenario_name']}",
        "",
        f"- Run ID: `{data['run_id']}`",
        f"- Started: `{data['started_at']}`",
        f"- Target: `{data['target_origin']}`",
        f"- Severity: `{data['severity']}`",
        f"- Execution mode: `{data['execution_mode']}`",
        f"- Execution reason: {data.get('execution_reason') or 'n/a'}",
        f"- Verdict: `{data['verdict']}`",
        "",
        "## Results",
        "",
    ]
    telemetry = data.get("llm_telemetry")
    if telemetry:
        lines[8:8] = [
            f"- LLM attempts: `{telemetry['attempts']}`",
            f"- LLM successes: `{telemetry['successes']}`",
            f"- LLM failures: `{telemetry['failures']}`",
        ]
    for result in data["results"]:
        lines.extend(
            [
                f"### {result['attack_id']}: {result['verdict']}",
                "",
                f"- Reason: {result['reason']}",
                f"- Evidence: {', '.join(result['evidence']) or 'none'}",
                "",
            ]
        )
        for turn in result["turns"]:
            response = turn.get("response") or {}
            lines.extend(
                [
                    f"#### Turn {turn['turn']}: {turn['verdict']}",
                    "",
                    f"- Reason: {turn['reason']}",
                    f"- Evidence: {', '.join(turn['evidence']) or 'none'}",
                    f"- Message: {turn['message']}",
                    f"- Agent status: {response.get('status', 'n/a')}",
                    f"- UI type: {(response.get('ui') or {}).get('type', 'none')}",
                    "",
                ]
            )
    return "\n".join(lines)


def write_report(
    result: ScenarioResult,
    output_dir: Path,
    redact_fields: set[str],
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    raw = result.model_dump(mode="json")
    data = redact(raw, redact_fields)
    if not isinstance(data, dict):
        raise TypeError("redacted report must remain a mapping")

    stem = f"{result.run_id}-{result.scenario_id}"
    json_path = output_dir / f"{stem}.json"
    markdown_path = output_dir / f"{stem}.md"
    json_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(_markdown_report(data), encoding="utf-8")
    return json_path, markdown_path
