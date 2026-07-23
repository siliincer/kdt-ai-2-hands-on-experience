"""Fail-closed compatibility entry point for the removed legacy runner."""

from __future__ import annotations


def main() -> int:
    """Reject the removed synchronous /chat execution path."""

    print(
        "ERROR: the legacy red-team /chat runner was removed for Agent V3. "
        "Use `python -m security.redteam.runner.reference_cli`."
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
