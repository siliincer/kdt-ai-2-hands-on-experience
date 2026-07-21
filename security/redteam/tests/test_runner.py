from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from security.redteam.config import load_config, load_scenario
from security.redteam.models import ExecutionMode, Verdict
from security.redteam.runner.client import AgentClient, RequestBudget
from security.redteam.runner.reporter import redact, write_report
from security.redteam.runner.service import SafetyPolicyError, run_scenario

ROOT = Path(__file__).resolve().parents[1]


def _handler(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/health":
        return httpx.Response(200, json={"status": "ok"})
    if request.url.path == "/chat":
        return httpx.Response(
            200,
            json={
                "reply": "이 요청은 안전 정책상 실행할 수 없습니다.",
                "status": "blocked",
                "thread_id": "thread_001",
                "prompt_for": None,
                "ui": None,
            },
        )
    if request.url.path == "/__local_test__/ledger":
        return httpx.Response(
            200,
            json={"balances": {"acc_001": 1250000}, "audit_log_count": 0},
        )
    if request.url.path == "/__local_test__/llm-telemetry":
        return httpx.Response(
            200,
            json={"attempts": 0, "successes": 0, "failures": 0},
        )
    return httpx.Response(404)


def test_prompt_injection_run_and_report(tmp_path):
    config = load_config(ROOT / "config.example.yaml")
    scenario = load_scenario(ROOT / "scenarios" / "prompt_injection.yaml")
    budget = RequestBudget(config.execution.max_requests_per_run)

    with AgentClient(
        config.target,
        budget,
        httpx.MockTransport(_handler),
    ) as client:
        result = run_scenario(config, scenario, client, "user_001")
    paths = write_report(result, tmp_path, config.safety.redact_fields)

    assert result.verdict == Verdict.PASS
    assert all(item.verdict == Verdict.PASS for item in result.results)
    assert all(path.exists() for path in paths)
    json_report = json.loads(paths[0].read_text())
    markdown_report = paths[1].read_text()
    assert json_report["verdict"] == "PASS"
    assert json_report["execution_mode"] == "guardrail_fallback"
    assert json_report["llm_telemetry"] == {
        "attempts": 0,
        "successes": 0,
        "failures": 0,
    }
    assert "- Execution mode: `guardrail_fallback`" in markdown_report
    assert "- LLM attempts: `0`" in markdown_report
    assert "- LLM failures: `0`" in markdown_report
    assert "#### Turn 1: PASS" in markdown_report
    assert budget.used == 2 + len(scenario.attacks) * 3


def test_multi_turn_scenario_preserves_thread_ids():
    config = load_config(ROOT / "config.example.yaml")
    scenario = load_scenario(ROOT / "scenarios" / "approval_bypass.yaml")
    budget = RequestBudget(config.execution.max_requests_per_run)
    thread_states = {}
    requests = []
    next_thread = 0
    balances = {"acc_001": 1250000}
    audit_log_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal audit_log_count, next_thread
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok"})
        if request.url.path == "/__local_test__/ledger":
            return httpx.Response(
                200,
                json={
                    "balances": balances,
                    "audit_log_count": audit_log_count,
                },
            )
        if request.url.path == "/__local_test__/llm-telemetry":
            return httpx.Response(
                200,
                json={"attempts": 3, "successes": 0, "failures": 3},
            )

        body = json.loads(request.content)
        requests.append(body)
        thread_id = body.get("thread_id")
        message = body["message"]
        if thread_id is None:
            next_thread += 1
            thread_id = f"thread_{next_thread}"
            thread_states[thread_id] = "confirmation"
            return httpx.Response(
                200,
                json={
                    "reply": "송금 정보를 확인해주세요.",
                    "status": "waiting_input",
                    "thread_id": thread_id,
                    "prompt_for": "transfer.approval_decision",
                    "ui": {"type": "confirm_modal"},
                },
            )
        if message == "승인" and thread_states[thread_id] == "confirmation":
            thread_states[thread_id] = "authentication"
            return httpx.Response(
                200,
                json={
                    "reply": "본인 인증을 진행해주세요.",
                    "status": "waiting_input",
                    "thread_id": thread_id,
                    "prompt_for": "transfer.auth_result",
                    "ui": {"type": "auth_request"},
                },
            )
        if message == "인증완료" and thread_states[thread_id] == "authentication":
            balances["acc_001"] -= 50000
            audit_log_count += 1
            return httpx.Response(
                200,
                json={
                    "reply": "50,000원을 송금했습니다.",
                    "status": "completed",
                    "thread_id": thread_id,
                    "prompt_for": None,
                    "ui": None,
                },
            )
        audit_log_count += 1
        return httpx.Response(
            200,
            json={
                "reply": "확인할 수 없는 답변이라 송금을 취소했습니다.",
                "status": "completed",
                "thread_id": thread_id,
                "prompt_for": None,
                "ui": None,
            },
        )

    with AgentClient(
        config.target,
        budget,
        httpx.MockTransport(handler),
    ) as client:
        result = run_scenario(config, scenario, client, "user_001")

    assert result.verdict == Verdict.PASS
    assert [len(item.turns) for item in result.results] == [1, 2, 3]
    assert all(
        request.get("thread_id") is not None for request in requests if request["message"] in {"승인", "인증완료"}
    )
    assert budget.used == 14


def test_request_budget_counts_health_and_chat():
    config = load_config(ROOT / "config.example.yaml")
    scenario = load_scenario(ROOT / "scenarios" / "prompt_injection.yaml")
    budget = RequestBudget(len(scenario.attacks))

    with AgentClient(
        config.target,
        budget,
        httpx.MockTransport(_handler),
    ) as client:
        with pytest.raises(SafetyPolicyError, match="including health"):
            run_scenario(config, scenario, client, "user_001")

    assert budget.used == 0


@pytest.mark.parametrize(
    ("telemetry", "expected_verdict", "reason"),
    [
        (
            {"attempts": 2, "successes": 2, "failures": 0},
            Verdict.PASS,
            "completed successfully",
        ),
        (
            {"attempts": 2, "successes": 1, "failures": 1},
            Verdict.ERROR,
            "may have used fallback",
        ),
        (
            {"attempts": 0, "successes": 0, "failures": 0},
            Verdict.ERROR,
            "did not execute",
        ),
    ],
)
def test_llm_mode_uses_runtime_telemetry(telemetry, expected_verdict, reason):
    config = load_config(ROOT / "config.example.yaml")
    config = config.model_copy(
        update={"execution": config.execution.model_copy(update={"mode": ExecutionMode.LLM_REDTEAM})}
    )
    scenario = load_scenario(ROOT / "scenarios" / "prompt_injection.yaml")
    budget = RequestBudget(config.execution.max_requests_per_run)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/__local_test__/llm-telemetry":
            return httpx.Response(200, json=telemetry)
        return _handler(request)

    with AgentClient(
        config.target,
        budget,
        httpx.MockTransport(handler),
    ) as client:
        result = run_scenario(config, scenario, client, "user_001")

    assert result.verdict == expected_verdict
    assert reason in result.execution_reason
    assert result.llm_telemetry.model_dump() == telemetry


def test_attack_failure_takes_priority_over_llm_error():
    config = load_config(ROOT / "config.example.yaml")
    config = config.model_copy(
        update={"execution": config.execution.model_copy(update={"mode": ExecutionMode.LLM_REDTEAM})}
    )
    scenario = load_scenario(ROOT / "scenarios" / "prompt_injection.yaml")
    budget = RequestBudget(config.execution.max_requests_per_run)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/chat":
            return httpx.Response(
                200,
                json={
                    "reply": "요청을 처리했습니다.",
                    "status": "completed",
                    "thread_id": "thread_001",
                    "prompt_for": None,
                    "ui": None,
                },
            )
        if request.url.path == "/__local_test__/llm-telemetry":
            return httpx.Response(
                200,
                json={"attempts": 1, "successes": 0, "failures": 1},
            )
        return _handler(request)

    with AgentClient(
        config.target,
        budget,
        httpx.MockTransport(handler),
    ) as client:
        result = run_scenario(config, scenario, client, "user_001")

    assert result.verdict == Verdict.FAIL
    assert "may have used fallback" in result.execution_reason


def test_report_redacts_keys_and_sensitive_text():
    value = {
        "account_number": "123-456-789012",
        "reply": "계좌 123-456-789012, Authorization: Bearer abc.def",
        "started_at": "2026-07-13T03:10:47Z",
    }

    redacted = redact(value, {"account_number", "authorization"})

    assert redacted["account_number"] == "[REDACTED]"
    assert "123-456-789012" not in redacted["reply"]
    assert "abc.def" not in redacted["reply"]
    assert redacted["started_at"] == "2026-07-13T03:10:47Z"
