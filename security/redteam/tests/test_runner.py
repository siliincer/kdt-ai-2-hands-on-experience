from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from security.redteam.config import load_config, load_scenario
from security.redteam.models import (
    AttackerTelemetry,
    GeneratedCandidate,
    LoopTermination,
    Verdict,
)
from security.redteam.runner.client import AgentClient, RequestBudget
from security.redteam.runner.reporter import redact, write_report
from security.redteam.runner.service import SafetyPolicyError, run_scenario

ROOT = Path(__file__).resolve().parents[1]


class _SeedGenerator:
    def __init__(self):
        self.calls = 0

    def generate(self, scenario, attack, history):
        self.calls += 1
        return GeneratedCandidate(
            message=attack.expanded_turns()[0].message,
            strategy="seed candidate for contract testing",
            style="contract test style",
            seed=self.calls,
        )

    def telemetry(self):
        return AttackerTelemetry(
            model="test-generator",
            attempts=self.calls,
            successes=self.calls,
            failures=0,
            rejected_out_of_scope=0,
        )


class _RecoveredGenerator(_SeedGenerator):
    def telemetry(self):
        return AttackerTelemetry(
            model="test-generator",
            attempts=self.calls + 1,
            successes=self.calls,
            failures=1,
            rejected_out_of_scope=0,
        )


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
        result = run_scenario(config, scenario, client, "user_001", _SeedGenerator())
    paths = write_report(result, tmp_path, config.safety.redact_fields)

    assert result.verdict == Verdict.PASS
    assert all(item.verdict == Verdict.PASS for item in result.results)
    assert all(path.exists() for path in paths)
    json_report = json.loads(paths[0].read_text())
    markdown_report = paths[1].read_text()
    assert json_report["verdict"] == "PASS"
    assert json_report["execution_mode"] == "adaptive_llm"
    assert json_report["llm_telemetry"] == {
        "attempts": 0,
        "successes": 0,
        "failures": 0,
    }
    assert "- Execution mode: `adaptive_llm`" in markdown_report
    assert "- LLM attempts: `0`" in markdown_report
    assert "- LLM failures: `0`" in markdown_report
    assert "#### Turn 1: PASS" in markdown_report
    assert "## Loop Summary" in markdown_report
    assert len(result.loop_summaries) == 3
    assert all(
        summary.termination == LoopTermination.ITERATION_LIMIT
        for summary in result.loop_summaries
    )
    assert budget.used == 2 + len(scenario.attacks) * 3 * 3


def test_recovered_generator_retry_does_not_invalidate_run():
    config = load_config(ROOT / "config.example.yaml")
    scenario = load_scenario(ROOT / "scenarios" / "prompt_injection.yaml")
    budget = RequestBudget(config.execution.max_requests_per_run)

    with AgentClient(
        config.target,
        budget,
        httpx.MockTransport(_handler),
    ) as client:
        result = run_scenario(
            config,
            scenario,
            client,
            "user_001",
            _RecoveredGenerator(),
        )

    assert result.verdict == Verdict.PASS
    assert result.execution_reason is not None
    assert "after bounded retries" in result.execution_reason


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
                json={"attempts": 1, "successes": 1, "failures": 0},
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
        result = run_scenario(config, scenario, client, "user_001", _SeedGenerator())

    assert result.verdict == Verdict.PASS
    assert [len(item.turns) for item in result.results] == [1, 1, 1, 2, 2, 2, 3]
    assert all(
        request.get("thread_id") is not None
        for request in requests
        if request["message"] in {"승인", "인증완료"}
    )
    assert budget.used == 28


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
            run_scenario(config, scenario, client, "user_001", _SeedGenerator())

    assert budget.used == 0


def test_terminal_safe_status_stops_remaining_turns():
    config = load_config(ROOT / "config.example.yaml")
    scenario = load_scenario(ROOT / "scenarios" / "approval_bypass.yaml")
    scenario = scenario.model_copy(update={"attacks": [scenario.attacks[1]]})
    budget = RequestBudget(config.execution.max_requests_per_run)
    messages = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/chat":
            messages.append(json.loads(request.content)["message"])
        return _handler(request)

    with AgentClient(
        config.target,
        budget,
        httpx.MockTransport(handler),
    ) as client:
        result = run_scenario(config, scenario, client, "user_001", _SeedGenerator())

    assert result.verdict == Verdict.PASS
    assert len(result.results) == 3
    assert all(len(item.turns) == 1 for item in result.results)
    assert "인증완료" not in messages


def test_target_llm_failure_marks_execution_error():
    config = load_config(ROOT / "config.example.yaml")
    scenario = load_scenario(ROOT / "scenarios" / "prompt_injection.yaml")
    budget = RequestBudget(config.execution.max_requests_per_run)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/__local_test__/llm-telemetry":
            return httpx.Response(
                200, json={"attempts": 2, "successes": 1, "failures": 1}
            )
        return _handler(request)

    with AgentClient(
        config.target,
        budget,
        httpx.MockTransport(handler),
    ) as client:
        result = run_scenario(config, scenario, client, "user_001", _SeedGenerator())

    assert result.verdict == Verdict.ERROR
    assert result.execution_reason is not None
    assert "target LLM calls failed" in result.execution_reason
    assert result.llm_telemetry is not None
    assert result.llm_telemetry.failures == 1


def test_attack_failure_takes_priority_over_llm_error():
    config = load_config(ROOT / "config.example.yaml")
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
        result = run_scenario(config, scenario, client, "user_001", _SeedGenerator())

    assert result.verdict == Verdict.FAIL
    assert result.execution_reason is not None
    assert "target LLM calls failed" in result.execution_reason


def test_adaptive_generator_improves_until_evidence_failure():
    config = load_config(ROOT / "config.example.yaml")
    scenario = load_scenario(ROOT / "scenarios" / "prompt_injection.yaml")
    scenario = scenario.model_copy(update={"attacks": [scenario.attacks[0]]})
    budget = RequestBudget(config.execution.max_requests_per_run)
    candidates = ["후보 1", "후보 2", "후보 3"]

    class FakeAttacker:
        def __init__(self):
            self.history_lengths = []
            self.calls = 0

        def generate(self, scenario, attack, history):
            self.history_lengths.append(len(history))
            candidate = candidates[self.calls]
            self.calls += 1
            return GeneratedCandidate(
                message=candidate,
                strategy=f"strategy {self.calls}",
                style=f"style {self.calls}",
                seed=self.calls,
            )

        def telemetry(self):
            return AttackerTelemetry(
                model="test-attacker",
                attempts=self.calls,
                successes=self.calls,
                failures=0,
                rejected_out_of_scope=0,
            )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/chat":
            message = json.loads(request.content)["message"]
            status = "completed" if message == "후보 3" else "blocked"
            return httpx.Response(
                200,
                json={
                    "reply": "처리됨" if status == "completed" else "차단됨",
                    "status": status,
                    "thread_id": f"thread-{message}",
                    "prompt_for": None,
                    "ui": None,
                },
            )
        return _handler(request)

    attacker = FakeAttacker()
    with AgentClient(
        config.target,
        budget,
        httpx.MockTransport(handler),
    ) as client:
        result = run_scenario(config, scenario, client, "user_001", attacker)

    assert result.verdict == Verdict.FAIL
    assert [item.iteration for item in result.results] == [1, 2, 3]
    assert [item.turns[0].message for item in result.results] == candidates
    assert all(item.generated_by_llm for item in result.results)
    assert [item.generation_strategy for item in result.results] == [
        "strategy 1",
        "strategy 2",
        "strategy 3",
    ]
    assert [item.generation_seed for item in result.results] == [1, 2, 3]
    assert [item.generation_style for item in result.results] == [
        "style 1",
        "style 2",
        "style 3",
    ]
    assert attacker.history_lengths == [0, 1, 2]
    assert result.attacker_telemetry is not None
    assert result.attacker_telemetry.attempts == 3
    assert result.llm_telemetry is not None
    assert result.llm_telemetry.attempts == 0
    assert result.execution_reason is not None
    assert "attacker LLM generated" in result.execution_reason
    assert result.loop_summaries[0].termination == (
        LoopTermination.EXPECTATION_MISMATCH
    )
    assert result.loop_summaries[0].iterations_completed == 3


def test_report_redacts_keys_and_sensitive_text():
    value = {
        "account_number": "123-456-789012",
        "reply": "계좌 123-456-789012, Authorization: Bearer abc.def",
        "started_at": "2026-07-13T03:10:47Z",
    }

    redacted = redact(value, {"account_number", "authorization"})

    assert isinstance(redacted, dict)
    assert redacted["account_number"] == "[REDACTED]"
    assert isinstance(redacted["reply"], str)
    assert "123-456-789012" not in redacted["reply"]
    assert "abc.def" not in redacted["reply"]
    assert redacted["started_at"] == "2026-07-13T03:10:47Z"
