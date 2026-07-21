"""Validate generated local QA candidates before target execution."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher

from security.redteam.models import (
    AttackCase,
    AttackResult,
    CandidatePolarity,
    GeneratedCandidate,
)


@dataclass(frozen=True)
class CandidateValidation:
    valid: bool
    reason: str
    missing_patterns: tuple[str, ...] = ()
    intent_mismatches: tuple[str, ...] = ()
    similarity: float = 0.0


_META_BRACES = re.compile(r"\{[^{}]*\}")
_META_ALTERNATION = re.compile(r"\|")
_META_FIELD = re.compile(
    r"seed_candidate|candidate_template|variation|schema|candidates",
    flags=re.IGNORECASE,
)
_ALLOWED_PUNCTUATION = frozenset(".,!?':;\"-_/()[]+=%…·₩")
_EXPLICIT_BUSINESS_FACT = re.compile(
    r"(?:\d[\d,.]*\s*(?:만\s*)?원|"
    r"(?:\d+(?:\.\d+)?|한|두|세|네|다섯|여섯|일곱|여덟|아홉|열|몇)\s*배|"
    r"절반|반으로|증액|감액|"
    r"추가\s*금액|송금|이체|[가-힣]{1,10}\s*통장)"
)
_WORD_TOKEN = re.compile(r"\w+", flags=re.UNICODE)


def _procedural_words(value: str) -> tuple[str, ...]:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return tuple(_WORD_TOKEN.findall(normalized))


def _matches_procedural_grammar(
    variation: str,
    slots: list[set[str]],
) -> bool:
    remaining = _procedural_words(variation)
    if not remaining:
        return False
    for slot in slots:
        choices = sorted(
            (_procedural_words(choice) for choice in slot),
            key=len,
            reverse=True,
        )
        matched = next(
            (choice for choice in choices if remaining[: len(choice)] == choice),
            None,
        )
        if not matched:
            return False
        remaining = remaining[len(matched) :]
    return not remaining


def _is_allowed_candidate_character(character: str) -> bool:
    codepoint = ord(character)
    return (
        character.isspace()
        or character in _ALLOWED_PUNCTUATION
        or (character.isascii() and character.isalnum())
        or 0x1100 <= codepoint <= 0x11FF
        or 0x3130 <= codepoint <= 0x318F
        or 0xA960 <= codepoint <= 0xA97F
        or 0xAC00 <= codepoint <= 0xD7A3
        or 0xD7B0 <= codepoint <= 0xD7FF
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
        deterministic = self.validate_deterministic(
            attack,
            candidate.message,
            candidate.variation,
            history,
        )
        if not deterministic.valid:
            return deterministic
        return self.validate_intent(attack, candidate, deterministic.similarity)

    def validate_deterministic(
        self,
        attack: AttackCase,
        message: str,
        variation: str,
        history: Sequence[AttackResult],
    ) -> CandidateValidation:
        missing = tuple(
            pattern
            for pattern in attack.candidate_required_patterns
            if not re.search(pattern, message, flags=re.IGNORECASE)
        )
        if missing:
            return CandidateValidation(
                valid=False,
                reason="missing_required_patterns",
                missing_patterns=missing,
            )

        if _META_BRACES.search(variation):
            return CandidateValidation(valid=False, reason="unresolved_meta_braces")
        if _META_ALTERNATION.search(variation):
            return CandidateValidation(
                valid=False,
                reason="unresolved_meta_alternation",
            )
        if _META_FIELD.search(variation):
            return CandidateValidation(valid=False, reason="unresolved_meta_field")
        if any(not _is_allowed_candidate_character(char) for char in variation):
            return CandidateValidation(valid=False, reason="non_korean_cjk_text")

        template = attack.candidate_template or ""
        fixed_fragments = template.split("{variation}")
        normalized_variation = self.normalize(variation)
        if any(
            len(normalized_fixed) >= 8 and normalized_fixed in normalized_variation
            for fragment in fixed_fragments
            if (normalized_fixed := self.normalize(fragment))
        ):
            return CandidateValidation(valid=False, reason="repeated_template_text")

        missing_variation = tuple(
            pattern
            for pattern in attack.variation_required_patterns
            if not re.search(pattern, variation, flags=re.IGNORECASE)
        )
        if missing_variation:
            return CandidateValidation(
                valid=False,
                reason="missing_variation_patterns",
                missing_patterns=missing_variation,
            )

        if any(
            re.search(pattern, variation, flags=re.IGNORECASE)
            for pattern in attack.variation_forbidden_patterns
        ):
            return CandidateValidation(
                valid=False,
                reason="forbidden_variation_pattern",
            )
        if attack.forbid_variation_business_facts and _EXPLICIT_BUSINESS_FACT.search(
            variation
        ):
            return CandidateValidation(
                valid=False,
                reason="conflicting_immutable_fact",
            )
        if (
            attack.forbid_variation_business_facts
            or attack.enforce_procedural_variation
        ) and not _matches_procedural_grammar(
            variation, attack.procedural_variation_slots
        ):
            return CandidateValidation(
                valid=False,
                reason="non_procedural_variation",
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
            reason="deterministic_checks_passed",
            similarity=max_similarity,
        )

    @staticmethod
    def validate_intent(
        attack: AttackCase,
        candidate: GeneratedCandidate,
        similarity: float = 0.0,
    ) -> CandidateValidation:
        if attack.forbid_variation_business_facts and candidate.business_fact_mentions:
            return CandidateValidation(
                valid=False,
                reason="conflicting_immutable_fact",
                similarity=similarity,
            )
        intent_mismatches = tuple(
            field
            for field, mismatched in (
                (
                    "requested_action",
                    candidate.requested_action != attack.expected_intent_action,
                ),
                ("target", candidate.target != attack.expected_intent_target),
                ("polarity", candidate.polarity != CandidatePolarity.REQUEST),
                ("reported_speech", candidate.reported_speech),
            )
            if mismatched
        )
        if intent_mismatches:
            return CandidateValidation(
                valid=False,
                reason="non_attack_intent",
                intent_mismatches=intent_mismatches,
                similarity=similarity,
            )
        return CandidateValidation(
            valid=True,
            reason="accepted",
            similarity=similarity,
        )

    @staticmethod
    def normalize(candidate: str) -> str:
        return re.sub(r"[^\w가-힣]+", "", candidate.casefold())

    @staticmethod
    def similarity(left: str, right: str) -> float:
        if not left or not right:
            return 0.0
        return SequenceMatcher(None, left, right, autojunk=False).ratio()
