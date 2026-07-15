"""Validate generated local QA candidates before target execution."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher

from security.redteam.models import AttackCase, AttackResult, GeneratedCandidate


@dataclass(frozen=True)
class CandidateValidation:
    valid: bool
    reason: str
    missing_patterns: tuple[str, ...] = ()
    similarity: float = 0.0


class CandidateValidator:
    def __init__(self, duplicate_similarity_threshold: float = 0.88) -> None:
        if not 0.5 <= duplicate_similarity_threshold <= 1.0:
            raise ValueError("duplicate similarity threshold must be between 0.5 and 1")
        self._duplicate_similarity_threshold = duplicate_similarity_threshold

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
        similarities = [
            self.similarity(normalized, self.normalize(result.turns[0].message))
            for result in history
            if result.turns
        ]
        max_similarity = max(similarities, default=0.0)
        if max_similarity >= self._duplicate_similarity_threshold:
            return CandidateValidation(
                valid=False,
                reason="duplicate_candidate",
                similarity=max_similarity,
            )
        return CandidateValidation(
            valid=True,
            reason="accepted",
            similarity=max_similarity,
        )

    @staticmethod
    def normalize(candidate: str) -> str:
        return re.sub(r"[^\w가-힣]+", "", candidate.casefold())

    @staticmethod
    def similarity(left: str, right: str) -> float:
        if not left or not right:
            return 0.0
        return SequenceMatcher(None, left, right, autojunk=False).ratio()
