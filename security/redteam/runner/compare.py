"""Fail-closed compatibility entry point for the legacy model comparison."""

from __future__ import annotations


def main() -> int:
    """Reject model comparison based on the removed /chat surrogate."""

    print(
        "ERROR: the legacy Target model comparison was removed for Agent V3. "
        "Run Agent V3 reference campaigns with "
        "`python -m security.redteam.runner.reference_cli`."
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
