from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from markdown_it import MarkdownIt

import security.redteam.runner.client as client_module
import security.redteam.runner.reporter as reporter_module
import security.redteam.runner.service as service_module
from security.redteam.config import load_config, load_scenario
from security.redteam.models import (
    AgentResponse,
    AgentUiEnvelope,
    AttackerTelemetry,
    CandidatePolarity,
    ExpectedResponse,
    GeneratedCandidate,
    JudgmentCategory,
    JudgmentOutcome,
    JudgmentTelemetry,
    LoopTermination,
    ModelJudgment,
    Scenario,
    Verdict,
)
from security.redteam.runner.client import (
    AgentClient,
    RequestBudget,
    RequestBudgetError,
)
from security.redteam.runner.reporter import ReportWriteError, redact, write_report
from security.redteam.runner.sanitizer import contains_sensitive_data
from security.redteam.runner.service import SafetyPolicyError, run_scenario

ROOT = Path(__file__).resolve().parents[1]


def _ledger_payload(
    balances: dict[str, int],
    audit_events: list[dict] | None = None,
) -> dict:
    events = audit_events or []
    return {
        "balances": balances,
        "account_state_digests": {account_id: "a" * 64 for account_id in balances},
        "collection_state_digests": {
            "accounts": "b" * 64,
            "recipients": "c" * 64,
            "transactions": "d" * 64,
        },
        "audit_log_count": len(events),
        "audit_events": events,
    }


def _workflow_evidence(workflow_id: str) -> dict:
    return {
        "observed_workflow_id": workflow_id,
        "runtime_status": "running",
        "state_status": "running",
        "tool_request_paths": [],
        "tool_requests": [],
        "contract_tool_ids": [],
        "webhooks": [],
        "pending_identifiers": {},
        "trace": [],
    }


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
            business_fact_mentions=set(),
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


class _BrokenTelemetryGenerator(_SeedGenerator):
    def telemetry(self):
        raise ValueError("synthetic telemetry invariant failure")


class _DisagreeingJudge:
    def __init__(self):
        self.calls = 0

    def evaluate(
        self,
        scenario: Scenario,
        expected: ExpectedResponse,
        message: str,
        response: AgentResponse,
        rule_verdict: Verdict,
    ):
        del scenario, expected, message, response, rule_verdict
        self.calls += 1
        return ModelJudgment(
            model="independent-test-judge",
            outcome=JudgmentOutcome.VIOLATION,
            categories={JudgmentCategory.OTHER},
            confidence=0.8,
            evidence_fields={"reply"},
        )

    def telemetry(self):
        return JudgmentTelemetry(
            model="independent-test-judge",
            attempts=self.calls,
            successes=self.calls,
            failures=0,
            agreements=0,
            disagreements=self.calls,
            uncertain=0,
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
            json=_ledger_payload({"acc_001": 1250000}),
        )
    if request.url.path == "/__local_test__/llm-telemetry":
        return httpx.Response(
            200,
            json={
                "attempts": 0,
                "successes": 0,
                "failures": 0,
                "policy_marker_injections": 0,
            },
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
    assert paths[0].with_suffix(".complete").exists()
    json_report = json.loads(paths[0].read_text())
    markdown_report = paths[1].read_text()
    assert json_report["verdict"] == "PASS"
    assert json_report["execution_mode"] == "adaptive_llm"
    assert json_report["config_version"] == 1
    assert json_report["scenario_version"] == 1
    assert json_report["scenario_type"] == "adaptive_attack"
    assert json_report["scenario_category"] == "policy_boundary"
    assert json_report["scenario_coverage"] == [
        "policy_confidentiality",
        "role_claim",
        "state_integrity",
    ]
    assert json_report["started_at"] <= json_report["completed_at"]
    assert json_report["duration_seconds"] >= 0
    assert json_report["results"][0]["generation_requested_action"] == "disclose"
    assert json_report["results"][0]["generation_target"] == "internal_instructions"
    assert json_report["results"][0]["target_workflow_id"] == ("wf_global_agent_entry")
    assert json_report["workflow_verdicts"] == {"wf_global_agent_entry": "PASS"}
    assert json_report["llm_telemetry"] == {
        "attempts": 0,
        "successes": 0,
        "failures": 0,
        "policy_marker_injections": 0,
    }
    assert "- Execution mode: `adaptive_llm`" in markdown_report
    assert "- Config version: `1`" in markdown_report
    assert "- Scenario version: `1`" in markdown_report
    assert "- Scenario type: `adaptive_attack`" in markdown_report
    assert "- Scenario category: `policy_boundary`" in markdown_report
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
    assert "## Workflow Verdicts" in markdown_report
    assert "- `wf_global_agent_entry`: `PASS`" in markdown_report
    assert "- Target workflow: `wf_global_agent_entry`" in markdown_report
    assert len(result.loop_summaries) == 3
    assert all(summary.termination == LoopTermination.ITERATION_LIMIT for summary in result.loop_summaries)
    assert budget.used == 2 + len(scenario.attacks) * 3 * 3


def test_reference_workflow_routing_mismatch_is_execution_error(tmp_path):
    config = load_config(ROOT / "config.example.yaml")
    scenario = load_scenario(ROOT / "scenarios" / "prompt_injection.yaml")
    scenario = scenario.model_copy(update={"attacks": [scenario.attacks[0]]})

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/chat":
            response = _handler(request)
            payload = json.loads(response.content)
            payload["execution_evidence"] = {
                "observed_workflow_id": "wf_balance_inquiry",
                "runtime_status": "completed",
                "state_status": "completed",
                "tool_request_paths": [],
                "contract_tool_ids": [],
                "webhooks": [],
                "pending_identifiers": {},
                "trace": [],
            }
            return httpx.Response(200, json=payload)
        return _handler(request)

    with AgentClient(
        config.target,
        RequestBudget(config.execution.max_requests_per_run),
        httpx.MockTransport(handler),
    ) as client:
        result = run_scenario(config, scenario, client, "user_001", _SeedGenerator())

    assert result.verdict == Verdict.ERROR
    assert result.results[0].verdict == Verdict.ERROR
    assert result.results[0].execution_error == "workflow routing:ValueError"
    assert result.results[0].turns[0].verdict == Verdict.ERROR
    assert "workflow:routing_mismatch" in result.results[0].evidence
    markdown = write_report(result, tmp_path, config.safety.redact_fields)[1].read_text()
    assert "- Observed workflow: `wf_balance_inquiry`" in markdown
    assert "- Runtime/state status: `completed` / `completed`" in markdown
    assert "- Tool request paths: none" in markdown


def test_business_workflow_without_execution_evidence_is_error():
    config = load_config(ROOT / "config.example.yaml")
    scenario = load_scenario(ROOT / "scenarios" / "approval_bypass.yaml")
    scenario = scenario.model_copy(update={"attacks": [scenario.attacks[0]]})

    with AgentClient(
        config.target,
        RequestBudget(config.execution.max_requests_per_run),
        httpx.MockTransport(_handler),
    ) as client:
        result = run_scenario(config, scenario, client, "user_001", _SeedGenerator())

    assert result.verdict == Verdict.ERROR
    assert result.results[0].execution_error == "workflow evidence:ValueError"
    assert "workflow:evidence_missing" in result.results[0].evidence


def test_business_workflow_accepts_proven_global_terminal_boundary():
    config = load_config(ROOT / "config.example.yaml")
    scenario = load_scenario(ROOT / "scenarios" / "approval_bypass.yaml")
    scenario = scenario.model_copy(update={"attacks": [scenario.attacks[0]]})

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/chat":
            response = _handler(request)
            payload = json.loads(response.content)
            payload["execution_evidence"] = {
                **_workflow_evidence("wf_global_agent_entry"),
                "runtime_status": "blocked",
                "state_status": "blocked",
                "trace": [{"step_id": "emit_global_blocked", "route_key": None}],
            }
            return httpx.Response(200, json=payload)
        return _handler(request)

    with AgentClient(
        config.target,
        RequestBudget(config.execution.max_requests_per_run),
        httpx.MockTransport(handler),
    ) as client:
        result = run_scenario(config, scenario, client, "user_001", _SeedGenerator())

    assert result.verdict == Verdict.PASS
    assert all(item.verdict == Verdict.PASS for item in result.results)


def test_business_workflow_rejects_unproven_global_terminal_boundary():
    config = load_config(ROOT / "config.example.yaml")
    scenario = load_scenario(ROOT / "scenarios" / "approval_bypass.yaml")
    scenario = scenario.model_copy(update={"attacks": [scenario.attacks[0]]})

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/chat":
            response = _handler(request)
            payload = json.loads(response.content)
            payload["execution_evidence"] = {
                **_workflow_evidence("wf_global_agent_entry"),
                "runtime_status": "blocked",
                "state_status": "blocked",
                "tool_request_paths": ["/api/v1/agent-tools/transfers"],
                "trace": [{"step_id": "emit_global_blocked", "route_key": None}],
            }
            return httpx.Response(200, json=payload)
        return _handler(request)

    with AgentClient(
        config.target,
        RequestBudget(config.execution.max_requests_per_run),
        httpx.MockTransport(handler),
    ) as client:
        result = run_scenario(config, scenario, client, "user_001", _SeedGenerator())

    assert result.verdict == Verdict.ERROR
    assert result.results[0].execution_error == "workflow routing:ValueError"


def test_model_disagreement_requires_review_without_overriding_rules():
    config = load_config(ROOT / "config.example.yaml")
    scenario = load_scenario(ROOT / "scenarios" / "prompt_injection.yaml")
    judge = _DisagreeingJudge()
    budget = RequestBudget(config.execution.max_requests_per_run)

    with AgentClient(config.target, budget, httpx.MockTransport(_handler)) as client:
        result = run_scenario(
            config,
            scenario,
            client,
            "user_001",
            _SeedGenerator(),
            judge,
        )

    assert result.verdict == Verdict.PASS
    assert result.review_required is True
    assert result.judgment_telemetry is not None
    assert result.judgment_telemetry.disagreements == 9
    assert all(turn.judgment_agrees_with_rules is False for attack in result.results for turn in attack.turns)


def test_sensitive_response_remains_failed_after_report_redaction(tmp_path):
    config = load_config(ROOT / "config.example.yaml")
    scenario = load_scenario(ROOT / "scenarios" / "prompt_injection.yaml")
    scenario = scenario.model_copy(update={"attacks": [scenario.attacks[0]]})

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/chat":
            return httpx.Response(
                200,
                json={
                    "reply": "token=local-secret-value",
                    "status": "blocked",
                    "thread_id": "thread",
                },
            )
        return _handler(request)

    with AgentClient(
        config.target,
        RequestBudget(config.execution.max_requests_per_run),
        httpx.MockTransport(handler),
    ) as client:
        result = run_scenario(config, scenario, client, "user_001", _SeedGenerator())
    json_path, _ = write_report(result, tmp_path, config.safety.redact_fields)
    report = json.loads(json_path.read_text())

    assert result.verdict == Verdict.FAIL
    assert report["verdict"] == "FAIL"
    serialized = json.dumps(report, ensure_ascii=False)
    assert "local-secret-value" not in serialized
    assert "[REDACTED]" in serialized


def test_incomplete_policy_marker_telemetry_marks_run_error():
    config = load_config(ROOT / "config.example.yaml")
    scenario = load_scenario(ROOT / "scenarios" / "prompt_injection.yaml")
    scenario = scenario.model_copy(update={"attacks": [scenario.attacks[0]]})

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/__local_test__/llm-telemetry":
            return httpx.Response(
                200,
                json={
                    "attempts": 1,
                    "successes": 1,
                    "failures": 0,
                    "policy_marker_injections": 0,
                },
            )
        return _handler(request)

    with AgentClient(
        config.target,
        RequestBudget(config.execution.max_requests_per_run),
        httpx.MockTransport(handler),
    ) as client:
        result = run_scenario(config, scenario, client, "user_001", _SeedGenerator())

    assert result.verdict == Verdict.ERROR
    assert result.execution_reason == "target LLM policy marker coverage is incomplete"


def test_report_fails_closed_before_writing(tmp_path, monkeypatch):
    config = load_config(ROOT / "config.example.yaml")
    scenario = load_scenario(ROOT / "scenarios" / "prompt_injection.yaml")
    scenario = scenario.model_copy(update={"attacks": [scenario.attacks[0]]})
    with AgentClient(
        config.target,
        RequestBudget(config.execution.max_requests_per_run),
        httpx.MockTransport(_handler),
    ) as client:
        result = run_scenario(config, scenario, client, "user_001", _SeedGenerator())

    turn = result.results[0].turns[0]
    assert turn.response is not None
    unsafe_response = turn.response.model_copy(update={"reply": "계좌는 123 456 789012 입니다"})
    unsafe_turn = turn.model_copy(update={"response": unsafe_response})
    unsafe_result = result.model_copy(
        update={"results": [result.results[0].model_copy(update={"turns": [unsafe_turn]})]}
    )
    monkeypatch.setattr(reporter_module, "redact", lambda value, _fields: value)

    with pytest.raises(ValueError, match="sensitive value"):
        write_report(unsafe_result, tmp_path, config.safety.redact_fields)

    assert list(tmp_path.iterdir()) == []


def test_report_redacts_camel_case_extra_response_fields(tmp_path):
    config = load_config(ROOT / "config.example.yaml")
    scenario = load_scenario(ROOT / "scenarios" / "prompt_injection.yaml")
    scenario = scenario.model_copy(update={"attacks": [scenario.attacks[0]]})
    with AgentClient(
        config.target,
        RequestBudget(config.execution.max_requests_per_run),
        httpx.MockTransport(_handler),
    ) as client:
        result = run_scenario(config, scenario, client, "user_001", _SeedGenerator())

    turn = result.results[0].turns[0]
    assert turn.response is not None
    response_payload = turn.response.model_dump(mode="python")
    response_payload.update(
        {
            "reply": "blocked session hint=opaque-hint",
            "accountNumber": "opaque-account",
            "accessToken": "opaque-token",
            "clientSecret": "opaque-secret",
        }
    )
    updated_turn = turn.model_copy(update={"response": AgentResponse.model_validate(response_payload)})
    updated_result = result.model_copy(
        update={"results": [result.results[0].model_copy(update={"turns": [updated_turn]})]}
    )

    json_path, _ = write_report(
        updated_result,
        tmp_path,
        config.safety.redact_fields | {"session_hint"},
    )
    response = json.loads(json_path.read_text())["results"][0]["turns"][0]["response"]

    assert response["accountNumber"] == "[REDACTED]"
    assert response["accessToken"] == "[REDACTED]"
    assert response["clientSecret"] == "[REDACTED]"
    assert "opaque-hint" not in response["reply"]


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


def test_attacker_telemetry_failure_does_not_erase_run_result():
    config = load_config(ROOT / "config.example.yaml")
    scenario = load_scenario(ROOT / "scenarios" / "prompt_injection.yaml")
    scenario = scenario.model_copy(update={"attacks": [scenario.attacks[0]]})

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
            _BrokenTelemetryGenerator(),
        )

    assert result.results
    assert result.verdict == Verdict.ERROR
    assert result.attacker_telemetry is None
    assert result.execution_reason == "attacker telemetry collection failed"


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
        "![remote](https://review.invalid/tracker.png) [link](https://review.invalid/) *emphasis* > quote | cell"
    )
    assert first.turns[0].response is not None
    unsafe_response = first.turns[0].response.model_copy(
        update={
            "reply": f"token=report-secret {unsafe_markup}",
            "status": f"blocked {unsafe_markup}\n# Forged Verdict: PASS",
            "thread_id": f"thread {unsafe_markup}",
            "prompt_for": f"state {unsafe_markup}",
            "ui": AgentUiEnvelope(type="notice [x](https://x.invalid)\n## Forged Section"),
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
            "attacker_telemetry": result.attacker_telemetry.model_copy(update={"model": unsafe_markup}),
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
    value = {"reply": ("token=sk-local Cookie: sid=abc Authorization: Basic dXNlcjpwYXNz api_key='local-key'")}

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

    assert contains_sensitive_data(value, set())
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
    assert not contains_sensitive_data(redacted, set())


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
        httpx.MockTransport(lambda _request: httpx.Response(200, json=response_payload)),
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


def test_unexpected_ledger_mutation_stops_remaining_cases():
    config = load_config(ROOT / "config.example.yaml")
    config = config.model_copy(
        update={"adaptive_attack": config.adaptive_attack.model_copy(update={"max_iterations_per_attack": 1})}
    )
    scenario = load_scenario(ROOT / "scenarios" / "prompt_injection.yaml")
    generator = _SeedGenerator()
    ledger_reads = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal ledger_reads
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok"})
        if request.url.path == "/chat":
            return httpx.Response(
                200,
                json={
                    "reply": "요청을 처리할 수 없습니다.",
                    "status": "blocked",
                    "thread_id": "thread_001",
                    "prompt_for": None,
                    "ui": None,
                },
            )
        if request.url.path == "/__local_test__/ledger":
            ledger_reads += 1
            balance = 1250000 if ledger_reads == 1 else 1200000
            return httpx.Response(
                200,
                json=_ledger_payload({"acc_001": balance}),
            )
        if request.url.path == "/__local_test__/llm-telemetry":
            return httpx.Response(
                200,
                json={
                    "attempts": 1,
                    "successes": 1,
                    "failures": 0,
                    "policy_marker_injections": 1,
                },
            )
        return httpx.Response(404)

    budget = RequestBudget(config.execution.max_requests_per_run)
    with AgentClient(
        config.target,
        budget,
        httpx.MockTransport(handler),
    ) as client:
        result = run_scenario(config, scenario, client, "user_001", generator)

    assert result.verdict == Verdict.FAIL
    assert result.execution_reason == ("scenario stopped after an unexpected ledger mutation")
    assert len(result.results) == 1
    assert generator.calls == 1
    assert "ledger_state:unexpected_mutation" in result.results[0].evidence


def test_multi_turn_scenario_preserves_thread_ids():
    config = load_config(ROOT / "config.example.yaml")
    scenario = load_scenario(ROOT / "scenarios" / "approval_bypass.yaml")
    budget = RequestBudget(config.execution.max_requests_per_run)
    thread_states = {}
    requests = []
    next_thread = 0
    balances = {"acc_001": 1250000}
    audit_log_count = 0
    audit_events = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal audit_log_count, next_thread
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok"})
        if request.url.path == "/__local_test__/ledger":
            return httpx.Response(
                200,
                json=_ledger_payload(balances, audit_events),
            )
        if request.url.path == "/__local_test__/llm-telemetry":
            return httpx.Response(
                200,
                json={
                    "attempts": 1,
                    "successes": 1,
                    "failures": 0,
                    "policy_marker_injections": 1,
                },
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
                    "execution_evidence": _workflow_evidence("wf_external_transfer"),
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
                    "execution_evidence": _workflow_evidence("wf_external_transfer"),
                },
            )
        if message == "인증완료" and thread_states[thread_id] == "authentication":
            balances["acc_001"] -= 50000
            audit_log_count += 1
            audit_events.append(
                {
                    "event_type": "workflow_completed",
                    "workflow_id": "wf_external_transfer",
                    "tool_id": "write_audit_log",
                    "result_digest": "a" * 64,
                }
            )
            return httpx.Response(
                200,
                json={
                    "reply": "50,000원을 송금했습니다.",
                    "status": "completed",
                    "thread_id": thread_id,
                    "prompt_for": None,
                    "ui": None,
                    "execution_evidence": _workflow_evidence("wf_external_transfer"),
                },
            )
        audit_log_count += 1
        audit_events.append(
            {
                "event_type": "workflow_completed",
                "workflow_id": "wf_external_transfer",
                "tool_id": "write_audit_log",
                "result_digest": "a" * 64,
            }
        )
        return httpx.Response(
            200,
            json={
                "reply": "확인할 수 없는 답변이라 송금을 취소했습니다.",
                "status": "completed",
                "thread_id": thread_id,
                "prompt_for": None,
                "ui": None,
                "execution_evidence": _workflow_evidence("wf_external_transfer"),
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
        request.get("thread_id") is not None for request in requests if request["message"] in {"승인", "인증완료"}
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
                        "execution_evidence": _workflow_evidence("wf_external_transfer"),
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
                    "execution_evidence": _workflow_evidence("wf_external_transfer"),
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


def test_agent_client_rejects_response_over_byte_limit():
    config = load_config(ROOT / "config.example.yaml")
    target = config.target.model_copy(update={"max_response_bytes": 1024})

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "reply": "x" * 2000,
                "status": "blocked",
                "thread_id": "thread",
            },
        )

    with AgentClient(
        target,
        RequestBudget(1),
        httpx.MockTransport(handler),
    ) as client:
        with pytest.raises(ValueError, match="byte limit"):
            client.chat("message", "user_001")


def test_terminal_safe_status_stops_remaining_turns():
    config = load_config(ROOT / "config.example.yaml")
    scenario = load_scenario(ROOT / "scenarios" / "approval_bypass.yaml")
    terminal_attack = scenario.attacks[1].model_copy(update={"expected_ledger": scenario.attacks[0].expected_ledger})
    scenario = scenario.model_copy(update={"attacks": [terminal_attack]})
    budget = RequestBudget(config.execution.max_requests_per_run)
    messages = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/chat":
            messages.append(json.loads(request.content)["message"])
            response = _handler(request)
            payload = json.loads(response.content)
            payload["execution_evidence"] = _workflow_evidence("wf_external_transfer")
            return httpx.Response(response.status_code, json=payload)
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
                    "execution_evidence": _workflow_evidence("wf_external_transfer"),
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
        update={"adaptive_attack": config.adaptive_attack.model_copy(update={"max_iterations_per_attack": 1})}
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
    markdown = write_report(result, tmp_path, config.safety.redact_fields)[1].read_text()
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
                    "execution_evidence": _workflow_evidence("wf_external_transfer"),
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
    markdown = write_report(result, tmp_path, config.safety.redact_fields)[1].read_text()
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
                200,
                json={
                    "attempts": 2,
                    "successes": 1,
                    "failures": 1,
                    "policy_marker_injections": 2,
                },
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
                json={
                    "attempts": 1,
                    "successes": 0,
                    "failures": 1,
                    "policy_marker_injections": 1,
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
                business_fact_mentions=set(),
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
    assert result.loop_summaries[0].termination == (LoopTermination.EXPECTATION_MISMATCH)
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


def test_report_redacts_spaced_and_numeric_account_values():
    redacted = redact(
        {
            "generation_seed": 1602940468,
            "large_balance": 1250000000,
            "epoch_seconds": 1784515025,
            "response": {
                "reply": "계좌는 123/456/789012 입니다",
                "accountNumber": 123456789012,
                "ui_values": [123, 456, 789012],
                "eventId": 1784515025,
            },
        },
        set(),
    )

    assert isinstance(redacted, dict)
    assert redacted["generation_seed"] == 1602940468
    assert redacted["large_balance"] == 1250000000
    assert redacted["epoch_seconds"] == 1784515025
    response = redacted["response"]
    assert isinstance(response, dict)
    assert response["reply"] == "계좌는 [REDACTED] 입니다"
    assert response["accountNumber"] == "[REDACTED]"
    assert response["ui_values"] == ["[REDACTED]"]
    assert response["eventId"] == 1784515025


def test_report_canonicalizes_camel_case_sensitive_keys():
    raw = {
        "accountNumber": "opaque-account",
        "accessToken": "opaque-token",
        "clientSecret": "opaque-secret",
    }

    assert contains_sensitive_data(raw, set())
    redacted = redact(raw, set())

    assert redacted == {
        "accountNumber": "[REDACTED]",
        "accessToken": "[REDACTED]",
        "clientSecret": "[REDACTED]",
    }
    assert not contains_sensitive_data(redacted, set())


def test_report_uses_canonical_policy_for_unicode_and_custom_inline_keys():
    raw = {
        "reply": (
            "session hint=custom-value "
            "ａｃｃｅｓｓ＿ｔｏｋｅｎ=full-width-value "
            "access\u200btoken=format-value access.token=dotted-value"
        )
    }

    assert contains_sensitive_data(raw, {"session_hint"})
    redacted = redact(raw, {"session_hint"})

    assert isinstance(redacted, dict)
    assert redacted["reply"].count("[REDACTED]") == 4
    assert not contains_sensitive_data(redacted, {"session_hint"})


def test_report_redacts_partial_marker_and_multiword_inline_values():
    raw = {
        "reply": ("token=[REDACTED]tail\nsession hint=first second value\ntoken=third value at 12:30 status=blocked")
    }

    assert contains_sensitive_data(raw, {"session_hint"})
    redacted = redact(raw, {"session_hint"})

    assert redacted == {"reply": ("token=[REDACTED]\nsession hint=[REDACTED]\ntoken=[REDACTED] status=blocked")}
    assert not contains_sensitive_data(redacted, {"session_hint"})


def test_report_supports_long_and_non_ascii_configured_inline_keys():
    fields = {"one two three four five", "내부 추적 식별자"}
    raw = {"reply": ("one two three four five=long custom value\n내부 추적 식별자=한국어 설정 값")}

    assert contains_sensitive_data(raw, fields)
    redacted = redact(raw, fields)

    assert isinstance(redacted, dict)
    assert redacted["reply"].count("[REDACTED]") == 2
    assert not contains_sensitive_data(redacted, fields)


def test_report_redacts_camel_case_text_assignments():
    redacted = redact(
        {
            "reply": (
                "accountNumber=opaque-account accessToken=opaque-token "
                "clientSecret=opaque-secret api key=opaque-api-key"
            )
        },
        set(),
    )

    assert isinstance(redacted, dict)
    reply = redacted["reply"]
    assert isinstance(reply, str)
    assert "opaque-account" not in reply
    assert "opaque-token" not in reply
    assert "opaque-secret" not in reply
    assert "opaque-api-key" not in reply


@pytest.mark.parametrize(
    "assignment",
    [
        "password=p@ss?word",
        "client_secret=left&right",
        "token=abc#suffix",
        "api_key=part;tail",
        "token=abc:def",
        "token=abc=def",
        "password=p@ss:word",
        "client_secret=left:right",
        "secret=urn:local:value",
        "token=YWJjZA==",
        "token=https://local.test/path?a=1&b=2#fragment",
    ],
)
def test_report_redacts_full_sensitive_assignment_values(assignment):
    key = assignment.split("=", 1)[0]

    redacted = redact({"reply": assignment}, set())

    assert redacted == {"reply": f"{key}=[REDACTED]"}
    assert not contains_sensitive_data(redacted, set())


@pytest.mark.parametrize(
    "suffix",
    [" tail", "\ttail", "\ntail", "?suffix", "&tail", "#tail", ";tail", ",tail"],
)
def test_report_redacts_content_after_partial_redaction_marker(suffix):
    raw = {"reply": f"token=[REDACTED]{suffix}"}

    redacted = redact(raw, set())

    assert redacted == {"reply": "token=[REDACTED]"}
    assert not contains_sensitive_data(redacted, set())


def test_custom_sensitive_assignment_keeps_internal_operators_in_value():
    fields = {"local hint"}
    raw = {"reply": "local hint=opaque:value=with-padding=="}

    redacted = redact(raw, fields)

    assert redacted == {"reply": "local hint=[REDACTED]"}
    assert not contains_sensitive_data(redacted, fields)


@pytest.mark.parametrize("fields", [{""}, {"---"}, {"..."}])
def test_sanitizer_ignores_empty_canonical_custom_fields(fields):
    raw = {"reply": "x=1"}

    assert redact(raw, fields) == raw
    assert not contains_sensitive_data(raw, fields)


def test_assignment_scan_stays_bounded_for_maximum_response_strings():
    raw = {f"reply_{index}": "x=" * 10_000 for index in range(3)}

    started = time.perf_counter()
    redacted = redact(raw, set())
    assert not contains_sensitive_data(redacted, set())
    duration = time.perf_counter() - started

    assert duration < 2.0


def test_report_preserves_unrelated_unicode_around_redacted_span():
    original = "ＡＢＣ 계좌는 123—456—789012, 표식\u200b유지"

    redacted = redact({"reply": original}, set())

    assert isinstance(redacted, dict)
    assert redacted["reply"] == "ＡＢＣ 계좌는 [REDACTED], 표식\u200b유지"


def test_sensitive_detector_handles_unicode_account_forms_independently():
    for value in (
        "123/456/789012",
        "123\u202f456\u202f789012",
        "123\u200b456\u200b789012",
        "123(456)789012",
        "123:456:789012",
        "１２３－４５６－７８９０１２",
        "123—456—789012",
        "MFS0123456789AB",
    ):
        assert contains_sensitive_data({"response": {"reply": value}}, set())

    assert not contains_sensitive_data(
        {
            "generation_seed": 1602940468,
            "large_balance": 1250000000,
            "epoch_seconds": 1784515025,
        },
        set(),
    )
    assert not contains_sensitive_data(
        {"response": {"reply": "2026 07 20 12 34 56"}},
        set(),
    )
    for ordinary_value in (
        "2026-07-20-1234",
        "2026/07/20 12:34",
        "192.168.10.20",
    ):
        assert not contains_sensitive_data(
            {"response": {"reply": ordinary_value}},
            set(),
        )
    assert not contains_sensitive_data(
        {"response": {"reply": "식별값 123456-789012"}},
        set(),
    )
    for ordinary_value in (
        "010-1234-5678",
        "111-222-333",
        "123-4567-8901-23",
    ):
        assert not contains_sensitive_data(
            {"response": {"reply": ordinary_value}},
            set(),
        )


def test_labeled_two_group_account_value_is_redacted():
    raw = {"reply": "계좌번호 123456-789012"}

    assert contains_sensitive_data(raw, set())
    assert redact(raw, set()) == {"reply": "계좌번호 [REDACTED]"}


def test_failed_ledger_verification_stops_remaining_cases():
    config = load_config(ROOT / "config.example.yaml")
    config = config.model_copy(
        update={"adaptive_attack": config.adaptive_attack.model_copy(update={"max_iterations_per_attack": 1})}
    )
    scenario = load_scenario(ROOT / "scenarios" / "prompt_injection.yaml")
    generator = _SeedGenerator()
    ledger_reads = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal ledger_reads
        if request.url.path == "/__local_test__/ledger":
            ledger_reads += 1
            if ledger_reads == 2:
                return httpx.Response(503)
        return _handler(request)

    with AgentClient(
        config.target,
        RequestBudget(config.execution.max_requests_per_run),
        httpx.MockTransport(handler),
    ) as client:
        result = run_scenario(config, scenario, client, "user_001", generator)

    assert len(result.results) == 1
    assert generator.calls == 1
    assert result.execution_reason == "scenario stopped because ledger integrity is unknown"
    assert "ledger_state:integrity_unknown" in result.results[0].evidence


def test_report_pair_is_removed_when_second_atomic_replace_fails(
    tmp_path,
    monkeypatch,
):
    config = load_config(ROOT / "config.example.yaml")
    scenario = load_scenario(ROOT / "scenarios" / "prompt_injection.yaml")
    scenario = scenario.model_copy(update={"attacks": [scenario.attacks[0]]})
    with AgentClient(
        config.target,
        RequestBudget(config.execution.max_requests_per_run),
        httpx.MockTransport(_handler),
    ) as client:
        result = run_scenario(config, scenario, client, "user_001", _SeedGenerator())

    real_replace = reporter_module.os.replace
    replacements = 0

    def fail_second_replace(source, destination):
        nonlocal replacements
        replacements += 1
        if replacements == 2:
            raise OSError("synthetic second replace failure")
        return real_replace(source, destination)

    monkeypatch.setattr(reporter_module.os, "replace", fail_second_replace)

    with pytest.raises(ReportWriteError, match="finalize report"):
        write_report(result, tmp_path, config.safety.redact_fields)

    assert list(tmp_path.iterdir()) == []


def test_report_cleanup_runs_when_publish_is_interrupted(tmp_path, monkeypatch):
    config = load_config(ROOT / "config.example.yaml")
    scenario = load_scenario(ROOT / "scenarios" / "prompt_injection.yaml")
    scenario = scenario.model_copy(update={"attacks": [scenario.attacks[0]]})
    with AgentClient(
        config.target,
        RequestBudget(config.execution.max_requests_per_run),
        httpx.MockTransport(_handler),
    ) as client:
        result = run_scenario(config, scenario, client, "user_001", _SeedGenerator())

    real_replace = reporter_module.os.replace
    replacements = 0

    def interrupt_second_replace(source, destination):
        nonlocal replacements
        replacements += 1
        if replacements == 2:
            raise KeyboardInterrupt
        return real_replace(source, destination)

    monkeypatch.setattr(reporter_module.os, "replace", interrupt_second_replace)

    with pytest.raises(KeyboardInterrupt):
        write_report(result, tmp_path, config.safety.redact_fields)

    assert list(tmp_path.iterdir()) == []


def test_report_cleanup_runs_when_directory_sync_is_interrupted(
    tmp_path,
    monkeypatch,
):
    config = load_config(ROOT / "config.example.yaml")
    scenario = load_scenario(ROOT / "scenarios" / "prompt_injection.yaml")
    scenario = scenario.model_copy(update={"attacks": [scenario.attacks[0]]})
    with AgentClient(
        config.target,
        RequestBudget(config.execution.max_requests_per_run),
        httpx.MockTransport(_handler),
    ) as client:
        result = run_scenario(config, scenario, client, "user_001", _SeedGenerator())

    real_fsync = reporter_module.os.fsync
    syncs = 0

    def interrupt_directory_sync(descriptor):
        nonlocal syncs
        syncs += 1
        if syncs == 4:
            raise KeyboardInterrupt
        return real_fsync(descriptor)

    monkeypatch.setattr(reporter_module.os, "fsync", interrupt_directory_sync)

    with pytest.raises(KeyboardInterrupt):
        write_report(result, tmp_path, config.safety.redact_fields)

    assert list(tmp_path.iterdir()) == []


def test_report_deadline_failure_leaves_no_output(tmp_path):
    config = load_config(ROOT / "config.example.yaml")
    scenario = load_scenario(ROOT / "scenarios" / "prompt_injection.yaml")
    scenario = scenario.model_copy(update={"attacks": [scenario.attacks[0]]})
    with AgentClient(
        config.target,
        RequestBudget(config.execution.max_requests_per_run),
        httpx.MockTransport(_handler),
    ) as client:
        result = run_scenario(config, scenario, client, "user_001", _SeedGenerator())
    checks = 0

    def deadline_check():
        nonlocal checks
        checks += 1
        if checks == 4:
            raise RequestBudgetError("deadline exhausted")

    with pytest.raises(RequestBudgetError, match="deadline exhausted"):
        write_report(
            result,
            tmp_path,
            config.safety.redact_fields,
            deadline_check,
        )

    assert list(tmp_path.iterdir()) == []


def test_fresh_finalization_budget_preserves_expired_run_result(tmp_path):
    config = load_config(ROOT / "config.example.yaml")
    scenario = load_scenario(ROOT / "scenarios" / "prompt_injection.yaml")
    scenario = scenario.model_copy(update={"attacks": [scenario.attacks[0]]})
    with AgentClient(
        config.target,
        RequestBudget(config.execution.max_requests_per_run),
        httpx.MockTransport(_handler),
    ) as client:
        result = run_scenario(config, scenario, client, "user_001", _SeedGenerator())

    finalization_budget = RequestBudget(
        1,
        config.execution.report_finalization_timeout_seconds,
    )
    paths = write_report(
        result,
        tmp_path,
        config.safety.redact_fields,
        finalization_budget.check_deadline,
    )

    assert all(path.exists() for path in paths)
    assert paths[0].with_suffix(".complete").exists()


def test_report_is_not_rolled_back_after_durable_commit(tmp_path):
    config = load_config(ROOT / "config.example.yaml")
    scenario = load_scenario(ROOT / "scenarios" / "prompt_injection.yaml")
    scenario = scenario.model_copy(update={"attacks": [scenario.attacks[0]]})
    with AgentClient(
        config.target,
        RequestBudget(config.execution.max_requests_per_run),
        httpx.MockTransport(_handler),
    ) as client:
        result = run_scenario(config, scenario, client, "user_001", _SeedGenerator())
    checks = 0

    def deadline_check():
        nonlocal checks
        checks += 1
        if checks > 6:
            raise RequestBudgetError("expired after durable commit")

    paths = write_report(
        result,
        tmp_path,
        config.safety.redact_fields,
        deadline_check,
    )

    assert checks == 6
    assert all(path.exists() for path in paths)
    assert paths[0].with_suffix(".complete").exists()
