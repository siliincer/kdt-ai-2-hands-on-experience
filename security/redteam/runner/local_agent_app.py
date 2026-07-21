"""Loopback-only Agent app with Fake Money and LLM execution evidence."""

from __future__ import annotations

from threading import Lock

import agent.llm
import agent.tools.bank_tools
import agent.workflow_matcher
from agent.data.mock_bank import AUDIT_LOG, MOCK_ACCOUNTS
from agent.main import app

_LLM_TELEMETRY = {"attempts": 0, "successes": 0, "failures": 0}
_LLM_TELEMETRY_LOCK = Lock()
_ORIGINAL_GET_LLM = agent.llm.get_llm


def _record_llm_result(success: bool) -> None:
    with _LLM_TELEMETRY_LOCK:
        _LLM_TELEMETRY["attempts"] += 1
        key = "successes" if success else "failures"
        _LLM_TELEMETRY[key] += 1


class _TrackedRunnable:
    def __init__(self, runnable) -> None:
        self._runnable = runnable

    def invoke(self, *args, **kwargs):
        try:
            result = self._runnable.invoke(*args, **kwargs)
        except Exception:
            _record_llm_result(False)
            raise
        _record_llm_result(True)
        return result

    def with_structured_output(self, *args, **kwargs):
        try:
            runnable = self._runnable.with_structured_output(*args, **kwargs)
        except Exception:
            _record_llm_result(False)
            raise
        return _TrackedRunnable(runnable)

    def __getattr__(self, name: str):
        return getattr(self._runnable, name)


def _tracked_get_llm(*args, **kwargs):
    try:
        runnable = _ORIGINAL_GET_LLM(*args, **kwargs)
    except Exception:
        _record_llm_result(False)
        raise
    return _TrackedRunnable(runnable)


agent.workflow_matcher.get_llm = _tracked_get_llm
agent.tools.bank_tools.get_llm = _tracked_get_llm


@app.get("/__local_test__/ledger", include_in_schema=False)
def ledger_snapshot() -> dict:
    return {
        "balances": {
            account["account_id"]: account["balance"] for accounts in MOCK_ACCOUNTS.values() for account in accounts
        },
        "audit_log_count": len(AUDIT_LOG),
    }


@app.get("/__local_test__/llm-telemetry", include_in_schema=False)
def llm_telemetry() -> dict:
    with _LLM_TELEMETRY_LOCK:
        return dict(_LLM_TELEMETRY)
