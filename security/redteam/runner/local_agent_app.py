"""Loopback-only Agent app with Fake Money and LLM execution evidence."""

from __future__ import annotations

import hashlib
import importlib
import json
from threading import Lock

import dotenv


def _ignore_project_dotenv(*args, **kwargs) -> bool:
    """Keep the managed test process isolated from developer credentials."""
    return False


dotenv.load_dotenv = _ignore_project_dotenv

agent_llm = importlib.import_module("agent.llm")
bank_tools = importlib.import_module("agent.tools.bank_tools")
workflow_matcher = importlib.import_module("agent.workflow_matcher")
mock_bank = importlib.import_module("agent.data.mock_bank")
app = importlib.import_module("agent.main").app

AUDIT_LOG = mock_bank.AUDIT_LOG
MOCK_ACCOUNTS = mock_bank.MOCK_ACCOUNTS

_LLM_TELEMETRY = {"attempts": 0, "successes": 0, "failures": 0}
_LLM_TELEMETRY_LOCK = Lock()
_ORIGINAL_GET_LLM = agent_llm.get_llm


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


setattr(workflow_matcher, "get_llm", _tracked_get_llm)
setattr(bank_tools, "get_llm", _tracked_get_llm)


@app.get("/__local_test__/ledger", include_in_schema=False)
def ledger_snapshot() -> dict:
    def digest(value: object) -> str:
        payload = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    return {
        "balances": {
            account["account_id"]: account["balance"]
            for accounts in MOCK_ACCOUNTS.values()
            for account in accounts
        },
        "account_state_digests": {
            account["account_id"]: digest(
                {
                    key: value
                    for key, value in account.items()
                    if key not in {"balance", "account_number"}
                }
            )
            for accounts in MOCK_ACCOUNTS.values()
            for account in accounts
        },
        "audit_log_count": len(AUDIT_LOG),
        "audit_events": [
            {
                "event_type": str(entry.get("event_type") or "unknown"),
                "workflow_id": entry.get("workflow_id"),
                "tool_id": entry.get("tool_id"),
                "result_digest": digest(entry.get("result")),
            }
            for entry in AUDIT_LOG
            if isinstance(entry, dict)
        ],
    }


@app.get("/__local_test__/llm-telemetry", include_in_schema=False)
def llm_telemetry() -> dict:
    with _LLM_TELEMETRY_LOCK:
        return dict(_LLM_TELEMETRY)
