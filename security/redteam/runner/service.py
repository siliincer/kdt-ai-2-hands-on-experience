"""Orchestrate one bounded red-team scenario run."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from security.redteam.config import RedTeamConfig
from security.redteam.models import (
    AdaptiveLoopSummary,
    AttackCase,
    AttackResult,
    LoopTermination,
    Scenario,
    ScenarioResult,
    Verdict,
)
from security.redteam.runner.attacker import AttackGenerator
from security.redteam.runner.client import AgentClient
from security.redteam.runner.evaluator import evaluate_ledger, evaluate_response


class SafetyPolicyError(RuntimeError):
    """Raised before network access when execution violates the safety policy."""


def validate_runtime(config: RedTeamConfig, user_id: str) -> None:
    if user_id not in config.safety.allowed_user_ids:
        raise SafetyPolicyError(f"user_id is not allowed: {user_id}")


def _adaptive_attempts(
    config: RedTeamConfig,
    attack: AttackCase,
    attacker: AttackGenerator | None,
) -> int:
    if attack.adaptive:
        if attacker is None:
            raise SafetyPolicyError("adaptive LLM mode requires an attack generator")
        return config.adaptive_attack.max_iterations_per_attack
    return 1


def _execute_attack(
    client: AgentClient,
    scenario: Scenario,
    attack: AttackCase,
    user_id: str,
    *,
    first_message: str | None,
    generation_strategy: str | None,
    generation_style: str | None,
    generation_seed: int | None,
    iteration: int,
) -> AttackResult:
    turns = attack.expanded_turns()
    if first_message is not None:
        turns = [
            turns[0].model_copy(update={"message": first_message}),
            *turns[1:],
        ]

    before_ledger = (
        client.ledger_snapshot() if attack.expected_ledger is not None else None
    )
    thread_id = None
    turn_results = []
    for index, turn in enumerate(turns, start=1):
        response = client.chat(turn.message, user_id, thread_id)
        thread_id = response.thread_id
        expected = turn.expected_response or scenario.expected_response
        turn_result = evaluate_response(index, turn.message, response, expected)
        turn_results.append(turn_result)
        if (
            turn_result.verdict == Verdict.PASS
            and response.status in expected.terminal_statuses
        ):
            break

    attack_verdict = (
        Verdict.FAIL
        if any(result.verdict == Verdict.FAIL for result in turn_results)
        else Verdict.PASS
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
    return AttackResult(
        attack_id=attack.id,
        iteration=iteration,
        generated_by_llm=first_message is not None,
        generation_strategy=generation_strategy,
        generation_style=generation_style,
        generation_seed=generation_seed,
        verdict=attack_verdict,
        reason=reason,
        evidence=evidence,
        turns=turn_results,
    )


def run_scenario(
    config: RedTeamConfig,
    scenario: Scenario,
    client: AgentClient,
    user_id: str,
    attacker: AttackGenerator | None = None,
) -> ScenarioResult:
    validate_runtime(config, user_id)
    if any(attack.adaptive for attack in scenario.attacks) and attacker is None:
        raise SafetyPolicyError("adaptive LLM execution requires an input generator")
    attempt_counts = [
        _adaptive_attempts(config, attack, attacker) for attack in scenario.attacks
    ]
    turn_count = sum(
        len(attack.expanded_turns()) * attempts
        for attack, attempts in zip(scenario.attacks, attempt_counts, strict=True)
    )
    if turn_count > config.execution.max_turns_per_scenario:
        raise SafetyPolicyError(
            f"scenario can use {turn_count} turns but turn limit is "
            f"{config.execution.max_turns_per_scenario}"
        )
    ledger_checks = sum(
        2 * attempts
        for attack, attempts in zip(scenario.attacks, attempt_counts, strict=True)
        if attack.expected_ledger
    )
    required_requests = 2 + turn_count + ledger_checks
    if client.remaining_requests < required_requests:
        raise SafetyPolicyError(
            f"scenario needs up to {required_requests} HTTP requests including health, "
            f"but only {client.remaining_requests} remain"
        )

    client.check_health()
    results: list[AttackResult] = []
    loop_summaries: list[AdaptiveLoopSummary] = []
    for attack, attempts in zip(scenario.attacks, attempt_counts, strict=True):
        history: list[AttackResult] = []
        for iteration in range(1, attempts + 1):
            generated = (
                attacker.generate(scenario, attack, history)
                if attempts > 1 and attacker is not None
                else None
            )
            result = _execute_attack(
                client,
                scenario,
                attack,
                user_id,
                first_message=generated.message if generated is not None else None,
                generation_strategy=(
                    generated.strategy if generated is not None else None
                ),
                generation_style=generated.style if generated is not None else None,
                generation_seed=generated.seed if generated is not None else None,
                iteration=iteration,
            )
            results.append(result)
            history.append(result)
            if attempts > 1 and result.verdict == Verdict.FAIL:
                break
        if attempts > 1:
            loop_summaries.append(
                AdaptiveLoopSummary(
                    attack_id=attack.id,
                    iterations_completed=len(history),
                    termination=(
                        LoopTermination.EXPECTATION_MISMATCH
                        if history[-1].verdict == Verdict.FAIL
                        else LoopTermination.ITERATION_LIMIT
                    ),
                )
            )

    verdict = (
        Verdict.FAIL
        if any(result.verdict == Verdict.FAIL for result in results)
        else Verdict.PASS
    )
    llm_telemetry = client.llm_telemetry()
    attacker_telemetry = attacker.telemetry() if attacker is not None else None
    adaptive_enabled = any(attempts > 1 for attempts in attempt_counts)
    if adaptive_enabled:
        if attacker_telemetry is None or attacker_telemetry.attempts == 0:
            if verdict != Verdict.FAIL:
                verdict = Verdict.ERROR
            execution_reason = "adaptive run did not generate an LLM attack"
        elif attacker_telemetry.failures > 0:
            if verdict != Verdict.FAIL:
                verdict = Verdict.ERROR
            execution_reason = "one or more attacker LLM generations failed"
        elif llm_telemetry.failures > 0:
            if verdict != Verdict.FAIL:
                verdict = Verdict.ERROR
            execution_reason = "one or more target LLM calls failed"
        else:
            execution_reason = (
                "attacker LLM generated all adaptive candidates successfully"
            )
    else:
        if llm_telemetry.attempts == 0:
            if verdict != Verdict.FAIL:
                verdict = Verdict.ERROR
            execution_reason = "scenario did not execute an LLM inference"
        elif llm_telemetry.failures > 0:
            if verdict != Verdict.FAIL:
                verdict = Verdict.ERROR
            execution_reason = "one or more target LLM calls failed"
        else:
            execution_reason = "all observed LLM calls completed successfully"

    return ScenarioResult(
        run_id=f"rt_{uuid.uuid4().hex[:12]}",
        started_at=datetime.now(UTC),
        target_origin=config.target.base_url.rstrip("/"),
        scenario_id=scenario.id,
        scenario_name=scenario.name,
        severity=scenario.severity,
        execution_mode="adaptive_llm",
        execution_reason=execution_reason,
        llm_telemetry=llm_telemetry,
        attacker_telemetry=attacker_telemetry,
        loop_summaries=loop_summaries,
        verdict=verdict,
        results=results,
    )
