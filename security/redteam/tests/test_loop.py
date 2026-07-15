from __future__ import annotations

import pytest

from security.redteam.models import AttackResult, LoopTermination, Verdict
from security.redteam.runner.loop import AdaptiveLoopState


def _result(iteration: int, verdict: Verdict, score: float = 0.0) -> AttackResult:
    return AttackResult(
        attack_id="case_one",
        iteration=iteration,
        verdict=verdict,
        boundary_score=score,
        reason="evaluated",
        turns=[],
    )


def test_loop_reaches_iteration_limit_and_tracks_best_score():
    loop = AdaptiveLoopState(attack_id="case_one", max_iterations=2)

    loop.record(_result(1, Verdict.PASS, 0.1))
    loop.record(_result(2, Verdict.PASS, 0.3))

    assert loop.can_continue is False
    assert loop.best_score == 0.3
    assert loop.summary().termination == LoopTermination.ITERATION_LIMIT
    assert loop.summary().best_score == 0.3


def test_loop_stops_on_expectation_mismatch():
    loop = AdaptiveLoopState(attack_id="case_one", max_iterations=3)

    loop.record(_result(1, Verdict.FAIL, 0.5))

    assert loop.can_continue is False
    assert loop.summary().iterations_completed == 1
    assert loop.summary().termination == LoopTermination.EXPECTATION_MISMATCH
    with pytest.raises(RuntimeError, match="already complete"):
        loop.record(_result(2, Verdict.PASS))


def test_loop_rejects_out_of_sequence_result():
    loop = AdaptiveLoopState(attack_id="case_one", max_iterations=2)

    with pytest.raises(ValueError, match="out of sequence"):
        loop.record(_result(2, Verdict.PASS))
