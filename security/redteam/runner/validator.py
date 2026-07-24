"""Validate generated local QA candidates before target execution."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher

from security.redteam.models import (
    AttackCase,
    AttackResult,
    CandidateBusinessFact,
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
_KOREAN_NUMBER = (
    r"(?:[공영일이삼사오육칠팔구십백천만억]+|"
    r"한|두|세|네|다섯|여섯|일곱|여덟|아홉|열)"
)
_AMOUNT_CHANGE_CONTEXT = re.compile(r"금액|송금|이체|보내|바꾸|변경|올리|내리|늘리|줄이|증가|감소")
_NUMERIC_AMOUNT = re.compile(r"(?:₩\s*\d[\d,.]*|(?<![가-힣A-Za-z0-9])\d[\d,.]*\s*(?:만\s*)?원)")
_KOREAN_AMOUNT = re.compile(rf"(?<![가-힣A-Za-z0-9])(?!일원(?:으로|인|이|의|을|과|에)){_KOREAN_NUMBER}\s*원")
_ABBREVIATED_AMOUNT_CHANGE = re.compile(
    r"(?<![가-힣A-Za-z0-9])\d[\d,.]*\s*만"
    r"(?=\s*(?:으로|을|를|에|만|바꾸|변경|올리|내리|늘리|줄이))"
)
_PERCENT_CHANGE = re.compile(
    r"(?<![가-힣A-Za-z0-9])"
    r"(?:\d+(?:\.\d+)?|한|두|세|네|다섯|여섯|일곱|여덟|아홉|열)\s*"
    r"(?:%|퍼센트|프로)(?:\s*(?:만큼|정도|가량|씩|만))?\s*"
    r"(?:올(?:리|린|려)|내(?:리|린|려)|늘(?:리|린|려)|줄(?:이|인|여)|"
    r"높(?:이|인|여)|낮(?:추|춘|춰)|증가|감소)"
)
_BUSINESS_FACT_PATTERNS = {
    CandidateBusinessFact.RELATIVE_CHANGE: re.compile(
        r"(?<![가-힣A-Za-z0-9])"
        r"(?:\d+(?:\.\d+)?|한|두|세|네|다섯|여섯|일곱|여덟|아홉|열|몇)\s*"
        r"배(?=\s|로|를|만|씩|[.,!?]|$)|"
        r"절반|반으로|증액|감액|추가\s*금액"
    ),
    CandidateBusinessFact.SOURCE_ACCOUNT: re.compile(r"[가-힣]{1,20}\s*통장"),
    CandidateBusinessFact.RECIPIENT: re.compile(r"[가-힣]{2,12}(?:에게|한테)"),
}
_NON_RECIPIENT_ROLES = {"관리자", "담당자", "상담원", "사용자", "본인"}
_NON_RECIPIENT_SUFFIXES = ("팀", "부", "실", "기관", "회사", "센터", "부서")
_TRANSFER_ACTION = re.compile(r"송금|이체|보내")
_TRANSFER_PROCEDURE = re.compile(r"(?:송금|이체)\s*요청\s*(?:절차|방법|지침|기록|정책|과정)")


def detect_business_facts(value: str) -> set[CandidateBusinessFact]:
    detected = {
        category
        for category, pattern in _BUSINESS_FACT_PATTERNS.items()
        if category != CandidateBusinessFact.RECIPIENT
        if pattern.search(value)
    }
    if _NUMERIC_AMOUNT.search(value) or (_KOREAN_AMOUNT.search(value) and _AMOUNT_CHANGE_CONTEXT.search(value)):
        detected.add(CandidateBusinessFact.AMOUNT)
    if _ABBREVIATED_AMOUNT_CHANGE.search(value):
        detected.add(CandidateBusinessFact.AMOUNT)
    if _PERCENT_CHANGE.search(value):
        detected.add(CandidateBusinessFact.RELATIVE_CHANGE)
    if _TRANSFER_ACTION.search(value) and not _TRANSFER_PROCEDURE.search(value):
        detected.add(CandidateBusinessFact.TRANSFER_ACTION)
    recipient_pattern = _BUSINESS_FACT_PATTERNS[CandidateBusinessFact.RECIPIENT]
    if any(
        (recipient := match.group()[: -len(suffix)]) not in _NON_RECIPIENT_ROLES
        and not recipient.endswith(_NON_RECIPIENT_SUFFIXES)
        for match in recipient_pattern.finditer(value)
        for suffix in ("에게", "한테")
        if match.group().endswith(suffix)
    ):
        detected.add(CandidateBusinessFact.RECIPIENT)
    return detected


def _detected_business_facts(value: str) -> set[CandidateBusinessFact]:
    """Backward-compatible alias for existing imports."""
    return detect_business_facts(value)


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

        if any(re.search(pattern, variation, flags=re.IGNORECASE) for pattern in attack.variation_forbidden_patterns):
            return CandidateValidation(
                valid=False,
                reason="forbidden_variation_pattern",
            )
        unexpected_facts = detect_business_facts(variation) - attack.allowed_variation_business_facts
        if unexpected_facts:
            return CandidateValidation(
                valid=False,
                reason="conflicting_immutable_fact",
                intent_mismatches=tuple(
                    f"business_fact:{fact.value}" for fact in sorted(unexpected_facts, key=lambda item: item.value)
                ),
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
        unexpected_facts = candidate.business_fact_mentions - attack.allowed_variation_business_facts
        if unexpected_facts:
            return CandidateValidation(
                valid=False,
                reason="conflicting_immutable_fact",
                similarity=similarity,
                intent_mismatches=tuple(
                    f"business_fact:{fact.value}" for fact in sorted(unexpected_facts, key=lambda item: item.value)
                ),
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
