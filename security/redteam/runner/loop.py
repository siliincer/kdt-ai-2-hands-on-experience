"""Explicit state for one bounded adaptive local QA loop."""

from __future__ import annotations

from dataclasses import dataclass, field

from security.redteam.models import (
    AdaptiveLoopSummary,
    AttackResult,
    LoopTermination,
    Verdict,
)


@dataclass
class AdaptiveLoopState:
    attack_id: str
    max_iterations: int
    history: list[AttackResult] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.max_iterations < 1:
            raise ValueError("max iterations must be positive")

    @property
    def next_iteration(self) -> int:
        return len(self.history) + 1

    @property
    def can_continue(self) -> bool:
        if len(self.history) >= self.max_iterations:
            return False
        return not self.history or self.history[-1].verdict == Verdict.PASS

    @property
    def best_score(self) -> float:
        return max((result.boundary_score for result in self.history), default=0.0)

    def record(self, result: AttackResult) -> None:
        if result.attack_id != self.attack_id:
            raise ValueError("loop result attack id does not match")
        if result.iteration != self.next_iteration:
            raise ValueError("loop result iteration is out of sequence")
        if not self.can_continue:
            raise RuntimeError("adaptive loop is already complete")
        self.history.append(result)

    def summary(self) -> AdaptiveLoopSummary:
        if not self.history:
            raise RuntimeError("adaptive loop has no results")
        termination = (
            LoopTermination.EXECUTION_ERROR
            if (self.history[-1].execution_error is not None or self.history[-1].verdict == Verdict.ERROR)
            else (
                LoopTermination.EXPECTATION_MISMATCH
                if self.history[-1].verdict == Verdict.FAIL
                else LoopTermination.ITERATION_LIMIT
            )
        )
        return AdaptiveLoopSummary(
            attack_id=self.attack_id,
            iterations_completed=len(self.history),
            best_score=self.best_score,
            termination=termination,
        )
