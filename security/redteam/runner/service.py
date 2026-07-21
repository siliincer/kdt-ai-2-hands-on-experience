"""Orchestrate one bounded red-team scenario run."""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime

import httpx

from security.redteam.config import RedTeamConfig
from security.redteam.models import (
    AttackCase,
    AttackResult,
    CandidateAction,
    CandidateBusinessFact,
    CandidatePolarity,
    CandidateTarget,
    JudgmentOutcome,
    Scenario,
    ScenarioResult,
    TurnResult,
    Verdict,
)
from security.redteam.runner.attacker import AttackGenerator
from security.redteam.runner.client import AgentClient, RequestBudgetError
from security.redteam.runner.evaluator import evaluate_ledger, evaluate_response
from security.redteam.runner.judge import ResponseJudge
from security.redteam.runner.loop import AdaptiveLoopState


class SafetyPolicyError(RuntimeError):
    """Raised before network access when execution violates the safety policy."""


_BOUNDED_EXECUTION_ERRORS = (
    httpx.HTTPError,
    RequestBudgetError,
    RuntimeError,
    ValueError,
)


def _error_result(
    attack: AttackCase,
    iteration: int,
    stage: str,
    error: Exception,
    *,
    turns=None,
    extra_evidence: list[str] | None = None,
) -> AttackResult:
    preserved_turns = list(turns or [])
    has_failure = any(turn.verdict == Verdict.FAIL for turn in preserved_turns)
    failure_reasons = list(
        dict.fromkeys(
            turn.reason for turn in preserved_turns if turn.verdict == Verdict.FAIL
        )
    )
    execution_reason = f"{stage} failed: {type(error).__name__}"
    reason = (
        f"security expectation mismatch: {'; '.join(failure_reasons)}; "
        f"{execution_reason}"
        if failure_reasons
        else execution_reason
    )
    return AttackResult(
        attack_id=attack.id,
        target_workflow_id=attack.target_workflow_id,
        iteration=iteration,
        verdict=Verdict.FAIL if has_failure else Verdict.ERROR,
        reason=reason,
        execution_error=f"{stage}:{type(error).__name__}",
        boundary_score=max(
            (turn.boundary_score for turn in preserved_turns), default=0.0
        ),
        evidence=[
            *(item for turn in preserved_turns for item in turn.evidence),
            *(extra_evidence or []),
        ],
        turns=preserved_turns,
    )


def _aggregate_verdict(results: list[AttackResult]) -> Verdict:
    if any(result.verdict == Verdict.FAIL for result in results):
        return Verdict.FAIL
    if any(result.verdict == Verdict.ERROR for result in results):
        return Verdict.ERROR
    return Verdict.PASS


def _aggregate_workflow_verdicts(
    results: list[AttackResult],
) -> dict:
    grouped = {}
    for result in results:
        grouped.setdefault(result.target_workflow_id, []).append(result)
    return {
        workflow_id: _aggregate_verdict(workflow_results)
        for workflow_id, workflow_results in grouped.items()
    }


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
    redact_fields: set[str],
    *,
    first_message: str | None,
    generation_variation: str | None,
    generation_strategy: str | None,
    generation_style: str | None,
    generation_seed: int | None,
    iteration: int,
    judge: ResponseJudge | None = None,
    generation_requested_action: CandidateAction | None = None,
    generation_target: CandidateTarget | None = None,
    generation_polarity: CandidatePolarity | None = None,
    generation_reported_speech: bool | None = None,
    generation_business_fact_mentions: set[CandidateBusinessFact] | None = None,
) -> AttackResult:
    turns = attack.expanded_turns()
    if first_message is not None:
        turns = [
            turns[0].model_copy(update={"message": first_message}),
            *turns[1:],
        ]

    try:
        before_ledger = (
            client.ledger_snapshot() if attack.expected_ledger is not None else None
        )
    except _BOUNDED_EXECUTION_ERRORS as exc:
        return _error_result(attack, iteration, "ledger snapshot", exc)
    thread_id = None
    turn_results = []
    for index, turn in enumerate(turns, start=1):
        requested_thread_id = thread_id
        try:
            client.check_deadline()
            response = client.chat(turn.message, user_id, thread_id)
        except _BOUNDED_EXECUTION_ERRORS as exc:
            turn_results.append(
                TurnResult(
                    turn=index,
                    message=turn.message,
                    verdict=Verdict.ERROR,
                    reason=f"target chat failed: {type(exc).__name__}",
                )
            )
            return _error_result(
                attack,
                iteration,
                "target chat",
                exc,
                turns=turn_results,
            )
        expected = turn.expected_response or scenario.expected_response
        turn_result = evaluate_response(
            index,
            turn.message,
            response,
            expected,
            redact_fields,
        )
        execution_evidence = response.execution_evidence
        if (
            execution_evidence is not None
            and execution_evidence.observed_workflow_id != attack.target_workflow_id
        ):
            routing_error = ValueError("reference workflow routing mismatch")
            turn_result = turn_result.model_copy(
                update={
                    "verdict": Verdict.ERROR,
                    "reason": "reference workflow routing mismatch",
                    "evidence": [
                        *turn_result.evidence,
                        "workflow:routing_mismatch",
                    ],
                }
            )
            return _error_result(
                attack,
                iteration,
                "workflow routing",
                routing_error,
                turns=[*turn_results, turn_result],
            )
        if judge is not None:
            try:
                judgment = judge.evaluate(
                    scenario,
                    expected,
                    turn.message,
                    response,
                    turn_result.verdict,
                )
            except _BOUNDED_EXECUTION_ERRORS as exc:
                return _error_result(
                    attack,
                    iteration,
                    "independent judgment",
                    exc,
                    turns=[*turn_results, turn_result],
                )
            agreement = (
                None
                if judgment.outcome == JudgmentOutcome.UNCERTAIN
                else (
                    (judgment.outcome == JudgmentOutcome.VIOLATION)
                    == (turn_result.verdict == Verdict.FAIL)
                )
            )
            turn_result = turn_result.model_copy(
                update={
                    "model_judgment": judgment,
                    "judgment_agrees_with_rules": agreement,
                }
            )
        if (
            requested_thread_id is not None
            and response.thread_id != requested_thread_id
        ):
            drift_reason = (
                f"thread continuity mismatch: expected {requested_thread_id}, "
                f"got {response.thread_id}"
            )
            turn_result = turn_result.model_copy(
                update={
                    "verdict": Verdict.FAIL,
                    "boundary_score": 1.0,
                    "reason": f"{turn_result.reason}; {drift_reason}",
                    "evidence": [
                        *turn_result.evidence,
                        "state:thread_continuity_mismatch",
                    ],
                }
            )
        turn_results.append(turn_result)
        try:
            client.check_deadline()
        except RequestBudgetError as exc:
            return _error_result(
                attack,
                iteration,
                "response evaluation",
                exc,
                turns=turn_results,
            )
        if (
            requested_thread_id is not None
            and response.thread_id != requested_thread_id
        ):
            break
        thread_id = response.thread_id
        if response.status in expected.terminal_statuses:
            break

    attack_verdict = (
        Verdict.FAIL
        if any(result.verdict == Verdict.FAIL for result in turn_results)
        else Verdict.PASS
    )
    boundary_score = max(
        (result.boundary_score for result in turn_results), default=0.0
    )
    evidence = [item for result in turn_results for item in result.evidence]
    ledger_reason = None
    if attack.expected_ledger is not None and before_ledger is not None:
        try:
            after_ledger = client.ledger_snapshot()
        except _BOUNDED_EXECUTION_ERRORS as exc:
            return _error_result(
                attack,
                iteration,
                "ledger verification",
                exc,
                turns=turn_results,
                extra_evidence=["ledger_state:integrity_unknown"],
            )
        ledger_verdict, ledger_reason, ledger_evidence = evaluate_ledger(
            before_ledger,
            after_ledger,
            attack.expected_ledger,
        )
        evidence.extend(ledger_evidence)
        try:
            client.check_deadline()
        except RequestBudgetError as exc:
            return _error_result(
                attack,
                iteration,
                "ledger evaluation",
                exc,
                turns=turn_results,
                extra_evidence=ledger_evidence,
            )
        if ledger_verdict == Verdict.FAIL:
            attack_verdict = Verdict.FAIL
            boundary_score = 1.0
    reason = (
        "response and ledger evidence matched the expected outcome"
        if attack_verdict == Verdict.PASS
        else "response or ledger evidence violated the expected outcome"
    )
    if ledger_reason:
        reason = f"{reason}; {ledger_reason}"
    return AttackResult(
        attack_id=attack.id,
        target_workflow_id=attack.target_workflow_id,
        iteration=iteration,
        generated_by_llm=first_message is not None,
        generation_variation=generation_variation,
        generation_strategy=generation_strategy,
        generation_style=generation_style,
        generation_seed=generation_seed,
        generation_requested_action=generation_requested_action,
        generation_target=generation_target,
        generation_polarity=generation_polarity,
        generation_reported_speech=generation_reported_speech,
        generation_business_fact_mentions=generation_business_fact_mentions or set(),
        verdict=attack_verdict,
        boundary_score=boundary_score,
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
    judge: ResponseJudge | None = None,
    *,
    run_started_at: datetime | None = None,
    run_started_monotonic: float | None = None,
) -> ScenarioResult:
    started_at = run_started_at or datetime.now(UTC)
    started_monotonic = (
        run_started_monotonic if run_started_monotonic is not None else time.monotonic()
    )
    validate_runtime(config, user_id)
    client.check_deadline()
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
    generation_requests = sum(
        attempts
        * (
            1
            + config.adaptive_attack.candidates_per_generation
            + 2 * (config.adaptive_attack.max_generation_attempts - 1)
        )
        for attack, attempts in zip(scenario.attacks, attempt_counts, strict=True)
        if attack.adaptive
    )
    judgment_requests = (
        turn_count * config.judgment.max_attempts_per_evaluation
        if judge is not None
        else 0
    )
    required_requests = (
        2 + turn_count + ledger_checks + generation_requests + judgment_requests
    )
    if client.remaining_requests < required_requests:
        raise SafetyPolicyError(
            f"scenario needs up to {required_requests} HTTP requests including health, "
            f"but only {client.remaining_requests} remain"
        )

    client.check_health()
    results: list[AttackResult] = []
    loop_summaries = []
    state_integrity_failure: str | None = None
    run_deadline_exhausted = False
    for attack, attempts in zip(scenario.attacks, attempt_counts, strict=True):
        loop = AdaptiveLoopState(attack_id=attack.id, max_iterations=attempts)
        while loop.can_continue:
            if attack.adaptive and attacker is not None:
                try:
                    client.check_deadline()
                    generated = attacker.generate(scenario, attack, loop.history)
                    client.check_deadline()
                except _BOUNDED_EXECUTION_ERRORS as exc:
                    result = _error_result(
                        attack,
                        loop.next_iteration,
                        "candidate generation",
                        exc,
                    )
                    results.append(result)
                    loop.record(result)
                    if isinstance(exc, RequestBudgetError):
                        run_deadline_exhausted = True
                        break
                    continue
            else:
                generated = None
            result = _execute_attack(
                client,
                scenario,
                attack,
                user_id,
                config.safety.redact_fields,
                first_message=generated.message if generated is not None else None,
                generation_variation=(
                    generated.variation if generated is not None else None
                ),
                generation_strategy=(
                    generated.strategy if generated is not None else None
                ),
                generation_style=generated.style if generated is not None else None,
                generation_seed=generated.seed if generated is not None else None,
                generation_requested_action=(
                    generated.requested_action if generated is not None else None
                ),
                generation_target=generated.target if generated is not None else None,
                generation_polarity=(
                    generated.polarity if generated is not None else None
                ),
                generation_reported_speech=(
                    generated.reported_speech if generated is not None else None
                ),
                generation_business_fact_mentions=(
                    generated.business_fact_mentions if generated is not None else None
                ),
                iteration=loop.next_iteration,
                judge=judge,
            )
            if result.execution_error is not None and generated is not None:
                result = result.model_copy(
                    update={
                        "generated_by_llm": True,
                        "generation_variation": generated.variation,
                        "generation_strategy": generated.strategy,
                        "generation_style": generated.style,
                        "generation_seed": generated.seed,
                        "generation_requested_action": generated.requested_action,
                        "generation_target": generated.target,
                        "generation_polarity": generated.polarity,
                        "generation_reported_speech": generated.reported_speech,
                        "generation_business_fact_mentions": (
                            generated.business_fact_mentions
                        ),
                    }
                )
            results.append(result)
            loop.record(result)
            if result.execution_error and result.execution_error.endswith(
                ":RequestBudgetError"
            ):
                run_deadline_exhausted = True
                break
            integrity_markers = {
                "ledger_state:unexpected_mutation",
                "ledger_state:integrity_unknown",
            }
            if marker := next(
                (item for item in result.evidence if item in integrity_markers),
                None,
            ):
                state_integrity_failure = marker
                break
        if attack.adaptive:
            loop_summaries.append(loop.summary())
        if state_integrity_failure is not None or run_deadline_exhausted:
            break

    verdict = _aggregate_verdict(results)
    telemetry_error = None
    try:
        llm_telemetry = client.llm_telemetry()
    except _BOUNDED_EXECUTION_ERRORS as exc:
        llm_telemetry = None
        telemetry_error = exc
        if verdict != Verdict.FAIL:
            verdict = Verdict.ERROR
    attacker_telemetry_error = None
    try:
        attacker_telemetry = attacker.telemetry() if attacker is not None else None
    except _BOUNDED_EXECUTION_ERRORS as exc:
        attacker_telemetry = None
        attacker_telemetry_error = exc
        if verdict != Verdict.FAIL:
            verdict = Verdict.ERROR
    judgment_telemetry_error = None
    try:
        judgment_telemetry = judge.telemetry() if judge is not None else None
    except _BOUNDED_EXECUTION_ERRORS as exc:
        judgment_telemetry = None
        judgment_telemetry_error = exc
        if verdict != Verdict.FAIL:
            verdict = Verdict.ERROR
    review_required = bool(
        judgment_telemetry
        and (judgment_telemetry.disagreements or judgment_telemetry.uncertain)
    )
    adaptive_enabled = any(attack.adaptive for attack in scenario.attacks)
    if adaptive_enabled:
        if state_integrity_failure == "ledger_state:unexpected_mutation":
            execution_reason = "scenario stopped after an unexpected ledger mutation"
        elif state_integrity_failure == "ledger_state:integrity_unknown":
            execution_reason = "scenario stopped because ledger integrity is unknown"
        elif any(result.execution_error for result in results):
            execution_reason = "adaptive execution ended with a bounded runtime error"
        elif attacker_telemetry_error is not None:
            execution_reason = "attacker telemetry collection failed"
        elif judgment_telemetry_error is not None:
            execution_reason = "independent judgment telemetry collection failed"
        elif telemetry_error is not None:
            execution_reason = "target LLM telemetry collection failed"
        elif (
            llm_telemetry is not None
            and llm_telemetry.policy_marker_injections != llm_telemetry.attempts
        ):
            if verdict != Verdict.FAIL:
                verdict = Verdict.ERROR
            execution_reason = "target LLM policy marker coverage is incomplete"
        elif attacker_telemetry is None or attacker_telemetry.attempts == 0:
            if verdict != Verdict.FAIL:
                verdict = Verdict.ERROR
            execution_reason = "adaptive run did not generate an LLM attack"
        elif llm_telemetry is not None and llm_telemetry.failures > 0:
            if verdict != Verdict.FAIL:
                verdict = Verdict.ERROR
            execution_reason = "one or more target LLM calls failed"
        else:
            execution_reason = (
                "attacker LLM generated all adaptive candidates after bounded retries"
                if attacker_telemetry.failures > 0
                else "attacker LLM generated all adaptive candidates successfully"
            )
    else:
        if telemetry_error is not None:
            execution_reason = "target LLM telemetry collection failed"
        elif (
            llm_telemetry is not None
            and llm_telemetry.policy_marker_injections != llm_telemetry.attempts
        ):
            if verdict != Verdict.FAIL:
                verdict = Verdict.ERROR
            execution_reason = "target LLM policy marker coverage is incomplete"
        elif llm_telemetry is not None and llm_telemetry.attempts == 0:
            if verdict != Verdict.FAIL:
                verdict = Verdict.ERROR
            execution_reason = "scenario did not execute an LLM inference"
        elif llm_telemetry is not None and llm_telemetry.failures > 0:
            if verdict != Verdict.FAIL:
                verdict = Verdict.ERROR
            execution_reason = "one or more target LLM calls failed"
        else:
            execution_reason = "all observed LLM calls completed successfully"

    completed_at = datetime.now(UTC)
    return ScenarioResult(
        run_id=f"rt_{uuid.uuid4().hex[:12]}",
        started_at=started_at,
        completed_at=completed_at,
        duration_seconds=max(0.0, time.monotonic() - started_monotonic),
        target_origin=config.target.base_url.rstrip("/"),
        config_version=config.version,
        scenario_version=scenario.version,
        scenario_type=scenario.type,
        scenario_category=scenario.category,
        scenario_coverage=scenario.coverage,
        scenario_id=scenario.id,
        scenario_name=scenario.name,
        severity=scenario.severity,
        execution_mode="adaptive_llm",
        execution_reason=execution_reason,
        review_required=review_required,
        llm_telemetry=llm_telemetry,
        attacker_telemetry=attacker_telemetry,
        judgment_telemetry=judgment_telemetry,
        loop_summaries=loop_summaries,
        workflow_verdicts=_aggregate_workflow_verdicts(results),
        verdict=verdict,
        results=results,
    )
