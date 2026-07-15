"""Validate generated local QA candidates before target execution."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from security.redteam.models import AttackCase, AttackResult, GeneratedCandidate


@dataclass(frozen=True)
class CandidateValidation:
    valid: bool
    reason: str
    missing_patterns: tuple[str, ...] = ()


class CandidateValidator:
    def validate(
        self,
        attack: AttackCase,
        candidate: GeneratedCandidate,
        history: Sequence[AttackResult],
    ) -> CandidateValidation:
        missing = tuple(
            pattern
            for pattern in attack.candidate_required_patterns
            if not re.search(pattern, candidate.message, flags=re.IGNORECASE)
        )
        if missing:
            return CandidateValidation(
                valid=False,
                reason="missing_required_patterns",
                missing_patterns=missing,
            )

        normalized = self.normalize(candidate.message)
        if any(
            result.turns and self.normalize(result.turns[0].message) == normalized
            for result in history
        ):
            return CandidateValidation(valid=False, reason="duplicate_candidate")
        return CandidateValidation(valid=True, reason="accepted")

    @staticmethod
    def normalize(candidate: str) -> str:
        return re.sub(r"[^\w가-힣]+", "", candidate.casefold())
