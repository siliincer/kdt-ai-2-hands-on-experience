"""Loopback-only Agent app with Fake Money and LLM execution evidence."""

from __future__ import annotations

import hashlib
import importlib
import json
import sys
from threading import Lock

import dotenv
from fastapi import FastAPI

from agent.schemas import ChatRequest
from security.redteam.runner.local_evidence import workflow_evidence
from security.redteam.runner.local_policy import inject_policy_marker


def _ignore_project_dotenv(*args, **kwargs) -> bool:
    """Keep the managed test process isolated from developer credentials."""
    return False


dotenv.load_dotenv = _ignore_project_dotenv

agent_llm = importlib.import_module("agent.llm")
bank_tools = importlib.import_module("agent.tools.bank_tools")
workflow_matcher = importlib.import_module("agent.workflow_matcher")
mock_bank = importlib.import_module("agent.data.mock_bank")
agent_service = importlib.import_module("agent.service")

app = FastAPI(title="Local Agent QA", version="0.1.0")

AUDIT_LOG = mock_bank.AUDIT_LOG
MOCK_ACCOUNTS = mock_bank.MOCK_ACCOUNTS
MOCK_RECIPIENTS = mock_bank.MOCK_RECIPIENTS
MOCK_TRANSACTIONS = mock_bank.MOCK_TRANSACTIONS

_LLM_TELEMETRY = {
    "attempts": 0,
    "successes": 0,
    "failures": 0,
    "policy_marker_injections": 0,
}
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
        if args:
            args = (inject_policy_marker(args[0]), *args[1:])
        elif "input" in kwargs:
            kwargs["input"] = inject_policy_marker(kwargs["input"])
        else:
            raise TypeError("local QA LLM invoke requires an input")
        with _LLM_TELEMETRY_LOCK:
            _LLM_TELEMETRY["policy_marker_injections"] += 1
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


for module_name, module in tuple(sys.modules.items()):
    if module_name.startswith("agent.") and getattr(module, "get_llm", None) is (
        _ORIGINAL_GET_LLM
    ):
        setattr(module, "get_llm", _tracked_get_llm)


def _workflow_evidence(thread_id: str, public_status: str) -> dict | None:
    snapshot = agent_service.GRAPH.get_state({"configurable": {"thread_id": thread_id}})
    return workflow_evidence(snapshot.values, public_status)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/chat")
def chat(request: ChatRequest) -> dict:
    result = agent_service.run_chat(
        request.message,
        request.user_id,
        request.thread_id,
    )
    evidence = _workflow_evidence(result["thread_id"], result["status"])
    if evidence is not None:
        result["execution_evidence"] = evidence
    return result


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

    account_rows = [
        account for accounts in MOCK_ACCOUNTS.values() for account in accounts
    ]
    account_ids = [account["account_id"] for account in account_rows]
    if len(account_ids) != len(set(account_ids)):
        raise RuntimeError("local bank contains duplicate account ids")

    accounts_without_balances = {
        user_id: [
            {key: value for key, value in account.items() if key != "balance"}
            for account in accounts
        ]
        for user_id, accounts in MOCK_ACCOUNTS.items()
    }
    return {
        "balances": {
            account["account_id"]: account["balance"] for account in account_rows
        },
        "account_state_digests": {
            account["account_id"]: digest(
                {key: value for key, value in account.items() if key != "balance"}
            )
            for account in account_rows
        },
        "collection_state_digests": {
            "accounts": digest(accounts_without_balances),
            "recipients": digest(MOCK_RECIPIENTS),
            "transactions": digest(MOCK_TRANSACTIONS),
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
