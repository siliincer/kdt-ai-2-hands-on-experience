"""Fail when Pyright errors exceed the repository's recorded baseline."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ErrorKey = tuple[str, str]


def _load_baseline(path: Path) -> Counter[ErrorKey]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise ValueError(f"Unsupported Pyright baseline schema: {path}")

    baseline: Counter[ErrorKey] = Counter()
    for item in payload.get("errors", []):
        key = (str(item["path"]), str(item["rule"]))
        baseline[key] = int(item["count"])
    return baseline


def _relative_path(raw_path: str, root: Path) -> str:
    path = Path(raw_path)
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _collect_errors(payload: dict[str, Any], root: Path) -> Counter[ErrorKey]:
    errors: Counter[ErrorKey] = Counter()
    for diagnostic in payload.get("generalDiagnostics", []):
        if diagnostic.get("severity") != "error":
            continue
        key = (
            _relative_path(str(diagnostic["file"]), root),
            str(diagnostic.get("rule") or "unknown"),
        )
        errors[key] += 1
    return errors


def _run_pyright(root: Path) -> dict[str, Any]:
    executable = shutil.which("pyright")
    if executable is None:
        raise RuntimeError("pyright executable was not found on PATH")

    result = subprocess.run(
        [executable, "--outputjson"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"Pyright did not return JSON: {detail}") from error

    if result.returncode not in (0, 1):
        detail = result.stderr.strip() or "unknown Pyright failure"
        raise RuntimeError(detail)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--baseline",
        type=Path,
        default=Path(".github/pyright-baseline.json"),
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    baseline_path = args.baseline
    if not baseline_path.is_absolute():
        baseline_path = root / baseline_path

    baseline = _load_baseline(baseline_path)
    payload = _run_pyright(root)
    current = _collect_errors(payload, root)
    regressions = {key: (count, baseline.get(key, 0)) for key, count in current.items() if count > baseline.get(key, 0)}

    summary = payload.get("summary", {})
    print(
        "Pyright: "
        f"{summary.get('errorCount', sum(current.values()))} errors, "
        f"{summary.get('warningCount', 0)} warnings; "
        f"baseline allows {sum(baseline.values())} existing errors."
    )

    if regressions:
        print("New Pyright regressions:", file=sys.stderr)
        for (path, rule), (count, allowed) in sorted(regressions.items()):
            print(
                f"- {path}: {rule} has {count} error(s), baseline allows {allowed}",
                file=sys.stderr,
            )
        return 1

    reductions = sum(max(allowed - current.get(key, 0), 0) for key, allowed in baseline.items())
    if reductions:
        print(f"Pyright baseline debt was reduced by {reductions} error(s).")
    print("No new Pyright errors were introduced.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
