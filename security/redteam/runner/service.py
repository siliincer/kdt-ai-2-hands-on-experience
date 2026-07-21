"""Orchestrate one bounded red-team scenario run."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from security.redteam.config import RedTeamConfig
from security.redteam.models import (
    AttackResult,
    ExecutionMode,
    Scenario,
    ScenarioResult,
    Verdict,
)
from security.redteam.runner.client import AgentClient
from security.redteam.runner.evaluator import evaluate_ledger, evaluate_response


class SafetyPolicyError(RuntimeError):
    """Raised before network access when execution violates the safety policy."""


def validate_runtime(config: RedTeamConfig, user_id: str) -> None:
    if user_id not in config.safety.allowed_user_ids:
        raise SafetyPolicyError(f"user_id is not allowed: {user_id}")


def run_scenario(
    config: RedTeamConfig,
    scenario: Scenario,
    client: AgentClient,
    user_id: str,
) -> ScenarioResult:
    validate_runtime(config, user_id)
    turn_count = sum(len(attack.expanded_turns()) for attack in scenario.attacks)
    if turn_count > config.execution.max_turns_per_scenario:
        raise SafetyPolicyError(
            f"scenario has {turn_count} turns but turn limit is {config.execution.max_turns_per_scenario}"
        )
    ledger_checks = sum(2 for attack in scenario.attacks if attack.expected_ledger)
    required_requests = 2 + turn_count + ledger_checks
    if client.remaining_requests < required_requests:
        raise SafetyPolicyError(
            f"scenario needs {required_requests} HTTP requests including health, "
            f"but only {client.remaining_requests} remain"
        )

    client.check_health()
    results = []
    for attack in scenario.attacks:
        before_ledger = client.ledger_snapshot() if attack.expected_ledger is not None else None
        thread_id = None
        turn_results = []
        for index, turn in enumerate(attack.expanded_turns(), start=1):
            response = client.chat(turn.message, user_id, thread_id)
            thread_id = response.thread_id
            expected = turn.expected_response or scenario.expected_response
            turn_results.append(evaluate_response(index, turn.message, response, expected))
        attack_verdict = (
            Verdict.FAIL if any(result.verdict == Verdict.FAIL for result in turn_results) else Verdict.PASS
        )
        evidence = [item for result in turn_results for item in result.evidence]
        ledger_reason = None
        if attack.expected_ledger is not None and before_ledger is not None:
            ledger_verdict, ledger_reason, ledger_evidence = evaluate_ledger(
                before_ledger,
                client.ledger_snapshot(),
                attack.expected_ledger,
            )
            evidence.extend(ledger_evidence)
            if ledger_verdict == Verdict.FAIL:
                attack_verdict = Verdict.FAIL
        reason = (
            "response and ledger evidence matched the expected outcome"
            if attack_verdict == Verdict.PASS
            else "response or ledger evidence violated the expected outcome"
        )
        if ledger_reason:
            reason = f"{reason}; {ledger_reason}"
        results.append(
            AttackResult(
                attack_id=attack.id,
                verdict=attack_verdict,
                reason=reason,
                evidence=evidence,
                turns=turn_results,
            )
        )
    verdict = Verdict.PASS
    if any(result.verdict == Verdict.FAIL for result in results):
        verdict = Verdict.FAIL

    llm_telemetry = client.llm_telemetry()
    if config.execution.mode == ExecutionMode.LLM_REDTEAM:
        if llm_telemetry.attempts == 0:
            if verdict != Verdict.FAIL:
                verdict = Verdict.ERROR
            execution_reason = "scenario did not execute an LLM inference"
        elif llm_telemetry.failures > 0:
            if verdict != Verdict.FAIL:
                verdict = Verdict.ERROR
            execution_reason = "one or more LLM calls failed and may have used fallback"
        else:
            execution_reason = "all observed LLM calls completed successfully"
    else:
        execution_reason = "guardrail fallback mode does not require successful LLM calls"

    return ScenarioResult(
        run_id=f"rt_{uuid.uuid4().hex[:12]}",
        started_at=datetime.now(UTC),
        target_origin=config.target.base_url.rstrip("/"),
        scenario_id=scenario.id,
        scenario_name=scenario.name,
        severity=scenario.severity,
        execution_mode=config.execution.mode,
        execution_reason=execution_reason,
        llm_telemetry=llm_telemetry,
        verdict=verdict,
        results=results,
    )
