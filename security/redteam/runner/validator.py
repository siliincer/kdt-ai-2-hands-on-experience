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


_META_BRACES = re.compile(r"\{[^{}]*\}")
_META_ALTERNATION = re.compile(r"\|")
_META_FIELD = re.compile(
    r"seed_candidate|candidate_template|variation|schema|candidates",
    flags=re.IGNORECASE,
)


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

        if _META_BRACES.search(candidate.variation):
            return CandidateValidation(valid=False, reason="unresolved_meta_braces")
        if _META_ALTERNATION.search(candidate.variation):
            return CandidateValidation(
                valid=False,
                reason="unresolved_meta_alternation",
            )
        if _META_FIELD.search(candidate.variation):
            return CandidateValidation(valid=False, reason="unresolved_meta_field")

        template = attack.candidate_template or ""
        fixed_fragments = template.split("{variation}")
        normalized_variation = self.normalize(candidate.variation)
        if any(
            len(normalized_fixed) >= 8 and normalized_fixed in normalized_variation
            for fragment in fixed_fragments
            if (normalized_fixed := self.normalize(fragment))
        ):
            return CandidateValidation(valid=False, reason="repeated_template_text")

        missing_variation = tuple(
            pattern
            for pattern in attack.variation_required_patterns
            if not re.search(pattern, candidate.variation, flags=re.IGNORECASE)
        )
        if missing_variation:
            return CandidateValidation(
                valid=False,
                reason="missing_variation_patterns",
                missing_patterns=missing_variation,
            )

        if any(
            re.search(pattern, candidate.variation, flags=re.IGNORECASE)
            for pattern in attack.variation_forbidden_patterns
        ):
            return CandidateValidation(
                valid=False,
                reason="forbidden_variation_pattern",
            )

        normalized = normalized_variation
        similarities = [
            self.similarity(
                normalized,
                self.normalize(result.generation_variation or result.turns[0].message),
            )
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
