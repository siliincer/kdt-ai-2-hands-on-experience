from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from markdown_it import MarkdownIt

import security.redteam.runner.client as client_module
import security.redteam.runner.service as service_module
from security.redteam.config import load_config, load_scenario
from security.redteam.models import (
    AgentUiEnvelope,
    AttackerTelemetry,
    CandidatePolarity,
    GeneratedCandidate,
    LoopTermination,
    Verdict,
)
from security.redteam.runner.client import (
    AgentClient,
    RequestBudget,
    RequestBudgetError,
)
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
            variation=attack.expanded_turns()[0].message,
            strategy="seed candidate for contract testing",
            style="contract test style",
            seed=self.calls,
            requested_action=attack.expected_intent_action,
            target=attack.expected_intent_target,
            polarity=CandidatePolarity.REQUEST,
            reported_speech=False,
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
    assert json_report["started_at"] <= json_report["completed_at"]
    assert json_report["duration_seconds"] >= 0
    assert json_report["results"][0]["generation_requested_action"] == "disclose"
    assert json_report["results"][0]["generation_target"] == "internal_instructions"
    assert json_report["llm_telemetry"] == {
        "attempts": 0,
        "successes": 0,
        "failures": 0,
    }
    assert "- Execution mode: `adaptive_llm`" in markdown_report
    assert "- LLM attempts: `0`" in markdown_report
    assert "- LLM failures: `0`" in markdown_report
    assert "- Completed: `" in markdown_report
    assert "- Duration seconds: `" in markdown_report
    assert "- Generation action: disclose" in markdown_report
    assert "- Agent reply: 이 요청은 안전 정책상 실행할 수 없습니다" in markdown_report
    assert "- Prompt state: none" in markdown_report
    assert r"- Thread ID: thread\_001" in markdown_report
    assert "#### Turn 1: PASS" in markdown_report
    assert "## Loop Summary" in markdown_report
    assert len(result.loop_summaries) == 3
    assert all(
        summary.termination == LoopTermination.ITERATION_LIMIT
        for summary in result.loop_summaries
    )
    assert budget.used == 2 + len(scenario.attacks) * 3 * 3


def test_run_timing_can_include_managed_startup(monkeypatch):
    config = load_config(ROOT / "config.example.yaml")
    scenario = load_scenario(ROOT / "scenarios" / "prompt_injection.yaml")
    run_started_at = datetime(2026, 7, 16, 3, 0, tzinfo=UTC)
    monkeypatch.setattr(service_module.time, "monotonic", lambda: 115.0)

    with AgentClient(
        config.target,
        RequestBudget(config.execution.max_requests_per_run),
        httpx.MockTransport(_handler),
    ) as client:
        result = run_scenario(
            config,
            scenario,
            client,
            "user_001",
            _SeedGenerator(),
            run_started_at=run_started_at,
            run_started_monotonic=100.0,
        )

    assert result.started_at == run_started_at
    assert result.duration_seconds == 15.0


def test_markdown_report_neutralizes_all_external_markdown(tmp_path):
    config = load_config(ROOT / "config.example.yaml")
    scenario = load_scenario(ROOT / "scenarios" / "prompt_injection.yaml")
    scenario = scenario.model_copy(update={"attacks": [scenario.attacks[0]]})

    with AgentClient(
        config.target,
        RequestBudget(config.execution.max_requests_per_run),
        httpx.MockTransport(_handler),
    ) as client:
        result = run_scenario(config, scenario, client, "user_001", _SeedGenerator())

    first = result.results[0]
    unsafe_markup = (
        "![remote](https://review.invalid/tracker.png) "
        "[link](https://review.invalid/) *emphasis* > quote | cell"
    )
    assert first.turns[0].response is not None
    unsafe_response = first.turns[0].response.model_copy(
        update={
            "reply": f"token=report-secret {unsafe_markup}",
            "status": f"blocked {unsafe_markup}\n# Forged Verdict: PASS",
            "thread_id": f"thread {unsafe_markup}",
            "prompt_for": f"state {unsafe_markup}",
            "ui": AgentUiEnvelope(type=f"notice {unsafe_markup}\n## Forged Section"),
        }
    )
    unsafe = first.model_copy(
        update={
            "generation_strategy": f"`strategy` {unsafe_markup}\n## Forged Summary",
            "reason": unsafe_markup,
            "turns": [
                first.turns[0].model_copy(
                    update={
                        "message": f"candidate {unsafe_markup}\n# Forged Verdict: FAIL",
                        "reason": unsafe_markup,
                        "response": unsafe_response,
                    }
                )
            ],
        }
    )
    assert result.attacker_telemetry is not None
    result = result.model_copy(
        update={
            "scenario_name": unsafe_markup,
            "attacker_telemetry": result.attacker_telemetry.model_copy(
                update={"model": unsafe_markup}
            ),
            "results": [unsafe],
        }
    )
    markdown_path = write_report(
        result,
        tmp_path,
        config.safety.redact_fields,
    )[1]
    markdown = markdown_path.read_text()

    assert "\n## Forged Summary" not in markdown
    assert "\n# Forged Verdict: FAIL" not in markdown
    assert "\n# Forged Verdict: PASS" not in markdown
    assert "\n## Forged Section" not in markdown
    rendered = MarkdownIt("commonmark").render(markdown)
    assert "<img" not in rendered
    assert "<a href" not in rendered
    assert "<em>" not in rendered
    assert "<blockquote>" not in rendered
    assert "report-secret" not in markdown
    assert "Agent reply:" in markdown
    assert "Prompt state:" in markdown
    assert "Thread ID:" in markdown


def test_report_redacts_embedded_authentication_values():
    value = {
        "reply": (
            "token=sk-local Cookie: sid=abc Authorization: Basic dXNlcjpwYXNz "
            "api_key='local-key'"
        )
    }

    redacted = redact(value, set())

    assert isinstance(redacted, dict)
    text = redacted["reply"]
    assert "sk-local" not in text
    assert "sid=abc" not in text
    assert "dXNlcjpwYXNz" not in text
    assert "local-key" not in text
    assert text.count("[REDACTED]") == 4


def test_report_redacts_arbitrary_authorization_and_quoted_secrets():
    value = {
        "reply": (
            "Authorization: AWS4-HMAC-SHA256 Credential=AKIAEXAMPLE\n"
            "Authorization: ApiKey super-secret\n"
            'password="two word secret"\n'
            "https://local.test/callback?access_token=abc123&refresh_token=def456\n"
            '{"client_secret":"ghi789","id_token":"jkl012"}'
        ),
        "access_token": "structured-access-token",
        "client_secret": "structured-client-secret",
    }

    redacted = redact(value, set())

    assert isinstance(redacted, dict)
    text = redacted["reply"]
    assert "AKIAEXAMPLE" not in text
    assert "super-secret" not in text
    assert "two word secret" not in text
    assert "abc123" not in text
    assert "def456" not in text
    assert "ghi789" not in text
    assert "jkl012" not in text
    assert text.count("[REDACTED]") == 7
    assert redacted["access_token"] == "[REDACTED]"
    assert redacted["client_secret"] == "[REDACTED]"


def test_request_budget_clamps_timeout_to_run_deadline(monkeypatch):
    now = 100.0
    monkeypatch.setattr(client_module.time, "monotonic", lambda: now)
    budget = RequestBudget(limit=2, max_seconds=10)

    now = 106.0
    assert budget.consume(30) == pytest.approx(4.0)

    now = 111.0
    with pytest.raises(RequestBudgetError, match="deadline exhausted"):
        budget.consume(30)


def test_agent_health_rejects_non_object_json():
    config = load_config(ROOT / "config.example.yaml")

    with AgentClient(
        config.target,
        RequestBudget(config.execution.max_requests_per_run),
        httpx.MockTransport(lambda _request: httpx.Response(200, json=[])),
    ) as client:
        with pytest.raises(ValueError, match="must be an object"):
            client.check_health()


@pytest.mark.parametrize(
    "response_payload",
    [
        {"reply": "blocked", "status": "blocked"},
        {"reply": "blocked", "status": "blocked", "thread_id": ""},
    ],
)
def test_agent_chat_rejects_missing_or_empty_thread_id(response_payload):
    config = load_config(ROOT / "config.example.yaml")

    with AgentClient(
        config.target,
        RequestBudget(config.execution.max_requests_per_run),
        httpx.MockTransport(
            lambda _request: httpx.Response(200, json=response_payload)
        ),
    ) as client:
        with pytest.raises(ValueError):
            client.chat("test", "user_001")


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


def test_multi_turn_scenario_rejects_thread_drift():
    config = load_config(ROOT / "config.example.yaml")
    scenario = load_scenario(ROOT / "scenarios" / "approval_bypass.yaml")
    scenario = scenario.model_copy(update={"attacks": [scenario.attacks[-1]]})
    chat_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal chat_calls
        if request.url.path == "/chat":
            chat_calls += 1
            if chat_calls == 1:
                return httpx.Response(
                    200,
                    json={
                        "reply": "송금 정보를 확인해주세요.",
                        "status": "waiting_input",
                        "thread_id": "thread-1",
                        "prompt_for": "transfer.approval_decision",
                        "ui": {"type": "confirm_modal"},
                    },
                )
            return httpx.Response(
                200,
                json={
                    "reply": "본인 인증을 진행해주세요.",
                    "status": "waiting_input",
                    "thread_id": "thread-2",
                    "prompt_for": "transfer.auth_result",
                    "ui": {"type": "auth_request"},
                },
            )
        return _handler(request)

    with AgentClient(
        config.target,
        RequestBudget(config.execution.max_requests_per_run),
        httpx.MockTransport(handler),
    ) as client:
        result = run_scenario(config, scenario, client, "user_001")

    attack = result.results[0]
    assert result.verdict == Verdict.FAIL
    assert len(attack.turns) == 2
    assert attack.turns[-1].verdict == Verdict.FAIL
    assert "thread continuity mismatch" in attack.turns[-1].reason
    assert "state:thread_continuity_mismatch" in attack.turns[-1].evidence
    assert chat_calls == 2


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


def test_terminal_failure_stops_remaining_turns():
    config = load_config(ROOT / "config.example.yaml")
    scenario = load_scenario(ROOT / "scenarios" / "approval_bypass.yaml")
    scenario = scenario.model_copy(update={"attacks": [scenario.attacks[1]]})
    budget = RequestBudget(config.execution.max_requests_per_run)
    messages = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/chat":
            messages.append(json.loads(request.content)["message"])
            return httpx.Response(
                200,
                json={
                    "reply": "송금했습니다",
                    "status": "blocked",
                    "thread_id": "thread-terminal",
                    "ui": None,
                },
            )
        return _handler(request)

    with AgentClient(
        config.target,
        budget,
        httpx.MockTransport(handler),
    ) as client:
        result = run_scenario(config, scenario, client, "user_001", _SeedGenerator())

    assert result.verdict == Verdict.FAIL
    assert all(len(item.turns) == 1 for item in result.results)
    assert "인증완료" not in messages


@pytest.mark.parametrize(
    "malformed_ui",
    [
        {"action": "open_auth", "screen": "auth_request"},
        {"type": None},
        {"type": {"nested": "auth_request"}},
        {"type": ["auth_request"]},
    ],
)
def test_malformed_target_ui_becomes_reported_execution_error(malformed_ui, tmp_path):
    config = load_config(ROOT / "config.example.yaml")
    scenario = load_scenario(ROOT / "scenarios" / "approval_bypass.yaml")
    scenario = scenario.model_copy(update={"attacks": [scenario.attacks[-1]]})

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/chat":
            return httpx.Response(
                200,
                json={
                    "reply": "요청을 종료했습니다.",
                    "status": "blocked",
                    "thread_id": "thread-malformed-ui",
                    "prompt_for": None,
                    "ui": malformed_ui,
                },
            )
        return _handler(request)

    with AgentClient(
        config.target,
        RequestBudget(config.execution.max_requests_per_run),
        httpx.MockTransport(handler),
    ) as client:
        result = run_scenario(config, scenario, client, "user_001")

    attack = result.results[0]
    assert result.verdict == Verdict.ERROR
    assert attack.verdict == Verdict.ERROR
    assert attack.execution_error == "target chat:ValidationError"
    assert attack.turns[0].verdict == Verdict.ERROR
    paths = write_report(result, tmp_path, config.safety.redact_fields)
    assert all(path.exists() for path in paths)


def test_adaptive_iteration_limit_one_still_generates_candidates():
    config = load_config(ROOT / "config.example.yaml")
    config = config.model_copy(
        update={
            "adaptive_attack": config.adaptive_attack.model_copy(
                update={"max_iterations_per_attack": 1}
            )
        }
    )
    scenario = load_scenario(ROOT / "scenarios" / "prompt_injection.yaml")
    budget = RequestBudget(config.execution.max_requests_per_run)
    generator = _SeedGenerator()

    with AgentClient(
        config.target,
        budget,
        httpx.MockTransport(_handler),
    ) as client:
        result = run_scenario(config, scenario, client, "user_001", generator)

    assert generator.calls == len(scenario.attacks)
    assert all(item.generated_by_llm for item in result.results)
    assert len(result.loop_summaries) == len(scenario.attacks)
    assert all(summary.iterations_completed == 1 for summary in result.loop_summaries)


def test_generation_error_preserves_partial_results_and_report(tmp_path):
    config = load_config(ROOT / "config.example.yaml")
    scenario = load_scenario(ROOT / "scenarios" / "prompt_injection.yaml")
    scenario = scenario.model_copy(update={"attacks": [scenario.attacks[0]]})
    budget = RequestBudget(config.execution.max_requests_per_run)

    class FailingGenerator(_SeedGenerator):
        def generate(self, scenario, attack, history):
            if self.calls == 1:
                self.calls += 1
                raise RuntimeError("simulated generation failure")
            return super().generate(scenario, attack, history)

        def telemetry(self):
            return AttackerTelemetry(
                model="test-generator",
                attempts=2,
                successes=1,
                failures=1,
                rejected_out_of_scope=0,
            )

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
            FailingGenerator(),
        )
    paths = write_report(result, tmp_path, config.safety.redact_fields)

    assert [item.verdict for item in result.results] == [Verdict.PASS, Verdict.ERROR]
    assert result.verdict == Verdict.ERROR
    assert result.loop_summaries[0].termination == LoopTermination.EXECUTION_ERROR
    assert all(path.exists() for path in paths)


def test_chat_error_becomes_reportable_error_result():
    config = load_config(ROOT / "config.example.yaml")
    scenario = load_scenario(ROOT / "scenarios" / "prompt_injection.yaml")
    scenario = scenario.model_copy(update={"attacks": [scenario.attacks[0]]})
    budget = RequestBudget(config.execution.max_requests_per_run)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/chat":
            return httpx.Response(503)
        return _handler(request)

    with AgentClient(
        config.target,
        budget,
        httpx.MockTransport(handler),
    ) as client:
        result = run_scenario(config, scenario, client, "user_001", _SeedGenerator())

    assert result.verdict == Verdict.ERROR
    assert result.results[0].verdict == Verdict.ERROR
    assert result.results[0].turns[0].verdict == Verdict.ERROR
    assert result.loop_summaries[0].termination == LoopTermination.EXECUTION_ERROR


def test_ledger_error_preserves_completed_turn():
    config = load_config(ROOT / "config.example.yaml")
    scenario = load_scenario(ROOT / "scenarios" / "prompt_injection.yaml")
    scenario = scenario.model_copy(update={"attacks": [scenario.attacks[0]]})
    budget = RequestBudget(config.execution.max_requests_per_run)
    ledger_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal ledger_calls
        if request.url.path == "/__local_test__/ledger":
            ledger_calls += 1
            if ledger_calls == 2:
                return httpx.Response(503)
        return _handler(request)

    with AgentClient(
        config.target,
        budget,
        httpx.MockTransport(handler),
    ) as client:
        result = run_scenario(config, scenario, client, "user_001", _SeedGenerator())

    assert result.verdict == Verdict.ERROR
    assert result.results[0].verdict == Verdict.ERROR
    assert len(result.results[0].turns) == 1
    assert result.results[0].turns[0].verdict == Verdict.PASS


def test_failure_survives_ledger_error_and_keeps_generation_metadata(tmp_path):
    config = load_config(ROOT / "config.example.yaml")
    scenario = load_scenario(ROOT / "scenarios" / "prompt_injection.yaml")
    scenario = scenario.model_copy(update={"attacks": [scenario.attacks[0]]})
    ledger_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal ledger_calls
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
        if request.url.path == "/__local_test__/ledger":
            ledger_calls += 1
            if ledger_calls == 2:
                return httpx.Response(503)
        return _handler(request)

    with AgentClient(
        config.target,
        RequestBudget(config.execution.max_requests_per_run),
        httpx.MockTransport(handler),
    ) as client:
        result = run_scenario(config, scenario, client, "user_001", _SeedGenerator())

    attack = result.results[0]
    assert result.verdict == Verdict.FAIL
    assert attack.verdict == Verdict.FAIL
    assert attack.turns[0].verdict == Verdict.FAIL
    assert attack.execution_error == "ledger verification:HTTPStatusError"
    assert "security expectation mismatch" in attack.reason
    assert "ledger verification failed" in attack.reason
    assert attack.generated_by_llm is True
    assert attack.generation_strategy == "seed candidate for contract testing"
    assert result.loop_summaries[0].termination == (LoopTermination.EXECUTION_ERROR)
    markdown = write_report(result, tmp_path, config.safety.redact_fields)[
        1
    ].read_text()
    rendered = MarkdownIt("commonmark").render(markdown)
    assert "Execution error: ledger verification:HTTPStatusError" in rendered
    assert "security expectation mismatch" in rendered


def test_failure_survives_followup_chat_error(tmp_path):
    config = load_config(ROOT / "config.example.yaml")
    scenario = load_scenario(ROOT / "scenarios" / "approval_bypass.yaml")
    scenario = scenario.model_copy(update={"attacks": [scenario.attacks[1]]})
    chat_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal chat_calls
        if request.url.path == "/chat":
            chat_calls += 1
            if chat_calls == 2:
                return httpx.Response(503)
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
        return _handler(request)

    with AgentClient(
        config.target,
        RequestBudget(config.execution.max_requests_per_run),
        httpx.MockTransport(handler),
    ) as client:
        result = run_scenario(config, scenario, client, "user_001", _SeedGenerator())

    attack = result.results[0]
    assert result.verdict == Verdict.FAIL
    assert attack.verdict == Verdict.FAIL
    assert [turn.verdict for turn in attack.turns] == [Verdict.FAIL, Verdict.ERROR]
    assert attack.execution_error == "target chat:HTTPStatusError"
    assert "security expectation mismatch" in attack.reason
    assert "target chat failed" in attack.reason
    assert attack.generated_by_llm is True
    assert result.loop_summaries[0].termination == LoopTermination.EXECUTION_ERROR
    markdown = write_report(result, tmp_path, config.safety.redact_fields)[
        1
    ].read_text()
    rendered = MarkdownIt("commonmark").render(markdown)
    assert "Execution error: target chat:HTTPStatusError" in rendered
    assert "security expectation mismatch" in rendered


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
                variation=candidate,
                strategy=f"strategy {self.calls}",
                style=f"style {self.calls}",
                seed=self.calls,
                requested_action=attack.expected_intent_action,
                target=attack.expected_intent_target,
                polarity=CandidatePolarity.REQUEST,
                reported_speech=False,
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
