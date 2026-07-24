import json
from pathlib import Path

import httpx
import pytest

from security.redteam.config import load_config, load_scenario
from security.redteam.models import (
    AgentResponse,
    ExpectedResponse,
    JudgmentOutcome,
    Verdict,
)
from security.redteam.runner.client import RequestBudget, RequestBudgetError
from security.redteam.runner.judge import OllamaResponseJudge

ROOT = Path(__file__).resolve().parents[1]


def _model_response(payload: dict) -> httpx.Response:
    return httpx.Response(200, json={"response": json.dumps(payload)})


def test_independent_judge_records_disagreement_without_rule_verdict_in_prompt():
    config = load_config(ROOT / "config.example.yaml")
    scenario = load_scenario(ROOT / "scenarios" / "prompt_injection.yaml")
    expected = scenario.expected_response
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        captured.update(json.loads(body["prompt"]))
        return _model_response(
            {
                "outcome": "violation",
                "categories": ["internal_policy"],
                "confidence": 0.91,
                "evidence_fields": ["reply"],
            }
        )

    response = AgentResponse(
        reply="요청을 처리할 수 없습니다.",
        status="blocked",
        thread_id="thread-1",
    )
    with OllamaResponseJudge(
        config.judgment,
        RequestBudget(10),
        httpx.MockTransport(handler),
    ) as judge:
        judgment = judge.evaluate(
            scenario,
            expected,
            "요청",
            response,
            Verdict.PASS,
        )
        telemetry = judge.telemetry()

    assert judgment.model == config.judgment.model
    assert judgment.outcome == JudgmentOutcome.VIOLATION
    assert "rule_verdict" not in captured
    assert "scenario_goal" not in captured
    assert captured["context_only_user_message"] == "요청"
    assert "Judge only observed_response" in captured["instruction"]
    assert "response itself" in captured["category_definitions"]["sensitive_data"]
    assert any(
        "확인 없이" in example.get("context_only_user_message", "") and example["outcome"] == "consistent"
        for example in captured["examples"]
    )
    assert telemetry.agreements == 0
    assert telemetry.disagreements == 1
    assert telemetry.uncertain == 0


def test_independent_judge_tracks_uncertain_separately():
    config = load_config(ROOT / "config.example.yaml")
    scenario = load_scenario(ROOT / "scenarios" / "prompt_injection.yaml")

    def handler(_request: httpx.Request) -> httpx.Response:
        return _model_response(
            {
                "outcome": "uncertain",
                "categories": [],
                "confidence": 0.4,
                "evidence_fields": [],
            }
        )

    with OllamaResponseJudge(
        config.judgment,
        RequestBudget(10),
        httpx.MockTransport(handler),
    ) as judge:
        judge.evaluate(
            scenario,
            scenario.expected_response,
            "요청",
            AgentResponse(reply="확인", status="blocked", thread_id="thread-1"),
            Verdict.PASS,
        )
        telemetry = judge.telemetry()

    assert telemetry.successes == 1
    assert telemetry.uncertain == 1
    assert telemetry.disagreements == 0


def test_independent_judge_counts_malformed_output_as_failure():
    config = load_config(ROOT / "config.example.yaml")
    scenario = load_scenario(ROOT / "scenarios" / "prompt_injection.yaml")
    transport = httpx.MockTransport(lambda _request: httpx.Response(200, json={"response": "not-json"}))

    with OllamaResponseJudge(
        config.judgment,
        RequestBudget(10),
        transport,
    ) as judge:
        with pytest.raises(ValueError):
            judge.evaluate(
                scenario,
                scenario.expected_response,
                "요청",
                AgentResponse(reply="확인", status="blocked", thread_id="thread-1"),
                Verdict.PASS,
            )
        telemetry = judge.telemetry()

    assert telemetry.attempts == 2
    assert telemetry.failures == 2
    assert telemetry.successes == 0


def test_independent_judge_recovers_from_one_malformed_output():
    config = load_config(ROOT / "config.example.yaml")
    scenario = load_scenario(ROOT / "scenarios" / "prompt_injection.yaml")
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        requests.append(body)
        if len(requests) == 1:
            return httpx.Response(200, json={"response": "not-json"})
        return _model_response(
            {
                "outcome": "consistent",
                "categories": [],
                "confidence": 0.9,
                "evidence_fields": ["status"],
            }
        )

    with OllamaResponseJudge(
        config.judgment,
        RequestBudget(10),
        httpx.MockTransport(handler),
    ) as judge:
        judgment = judge.evaluate(
            scenario,
            scenario.expected_response,
            "요청",
            AgentResponse(reply="확인", status="blocked", thread_id="thread-1"),
            Verdict.PASS,
        )
        telemetry = judge.telemetry()

    first_prompt = json.loads(requests[0]["prompt"])
    second_prompt = json.loads(requests[1]["prompt"])
    assert judgment.outcome == JudgmentOutcome.CONSISTENT
    assert "retry_correction" not in first_prompt
    assert "retry_correction" in second_prompt
    assert requests[1]["options"]["seed"] == requests[0]["options"]["seed"] + 1
    assert telemetry.attempts == 2
    assert telemetry.failures == 1
    assert telemetry.successes == 1
    assert telemetry.agreements == 1


def test_independent_judge_retries_unsupported_violation_without_evidence():
    config = load_config(ROOT / "config.example.yaml")
    scenario = load_scenario(ROOT / "scenarios" / "prompt_injection.yaml")
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return _model_response(
                {
                    "outcome": "violation",
                    "categories": ["unauthorized_completion"],
                    "confidence": 1,
                    "evidence_fields": [],
                }
            )
        return _model_response(
            {
                "outcome": "consistent",
                "categories": [],
                "confidence": 0.9,
                "evidence_fields": ["status"],
            }
        )

    with OllamaResponseJudge(
        config.judgment,
        RequestBudget(10),
        httpx.MockTransport(handler),
    ) as judge:
        judgment = judge.evaluate(
            scenario,
            scenario.expected_response,
            "요청",
            AgentResponse(reply="확인", status="blocked", thread_id="thread-1"),
            Verdict.PASS,
        )
        telemetry = judge.telemetry()

    assert judgment.outcome == JudgmentOutcome.CONSISTENT
    assert telemetry.attempts == 2
    assert telemetry.failures == 1


def test_independent_judge_keeps_telemetry_valid_when_budget_is_already_empty():
    config = load_config(ROOT / "config.example.yaml")
    scenario = load_scenario(ROOT / "scenarios" / "prompt_injection.yaml")

    with OllamaResponseJudge(config.judgment, RequestBudget(0)) as judge:
        with pytest.raises(RequestBudgetError):
            judge.evaluate(
                scenario,
                scenario.expected_response,
                "요청",
                AgentResponse(reply="확인", status="blocked", thread_id="thread-1"),
                Verdict.PASS,
            )
        telemetry = judge.telemetry()

    assert telemetry.attempts == 0
    assert telemetry.successes == 0
    assert telemetry.failures == 0


@pytest.mark.parametrize(
    ("response", "expected_ui_types", "expected_prompt_for", "is_terminal"),
    [
        (
            AgentResponse(
                reply="요청한 작업을 완료했습니다.",
                status="completed",
                thread_id="thread-1",
            ),
            ["none"],
            ["none"],
            True,
        ),
        (
            AgentResponse(
                reply="계좌를 선택하세요.",
                status="waiting_input",
                thread_id="thread-1",
                prompt_for="transfer.from_account",
            ),
            ["account_card_list"],
            ["transfer.from_account"],
            False,
        ),
    ],
)
def test_independent_judge_uses_status_specific_contract(
    response: AgentResponse,
    expected_ui_types: list[str],
    expected_prompt_for: list[str],
    is_terminal: bool,
):
    config = load_config(ROOT / "config.example.yaml")
    scenario = load_scenario(ROOT / "scenarios" / "prompt_injection.yaml")
    expected = ExpectedResponse(
        allowed_statuses={"waiting_input", "completed"},
        terminal_statuses={"completed"},
        allowed_ui_types={"account_card_list"},
        allowed_prompt_for={"transfer.from_account"},
        terminal_allowed_ui_types={None},
        terminal_allowed_prompt_for={None},
        required_reply_patterns=["완료|취소"],
        forbidden_reply_patterns=["비밀번호"],
    )
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        captured.update(json.loads(body["prompt"]))
        return _model_response(
            {
                "outcome": "consistent",
                "categories": [],
                "confidence": 0.95,
                "evidence_fields": ["status"],
            }
        )

    with OllamaResponseJudge(
        config.judgment,
        RequestBudget(10),
        httpx.MockTransport(handler),
    ) as judge:
        judge.evaluate(scenario, expected, "요청", response, Verdict.PASS)

    contract = captured["expected_contract"]
    assert contract["observed_status_is_terminal"] is is_terminal
    assert contract["allowed_ui_types"] == expected_ui_types
    assert contract["allowed_prompt_for"] == expected_prompt_for
    assert contract["required_reply_patterns"] == ["완료|취소"]
    assert contract["forbidden_reply_patterns"] == ["비밀번호"]
    assert any(
        example["observed_response"]["status"] == "completed" and example["outcome"] == "consistent"
        for example in captured["examples"]
    )
