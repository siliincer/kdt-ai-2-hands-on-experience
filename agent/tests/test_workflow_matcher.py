"""워크플로우 매칭 검증 (키워드 폴백 경로).

conftest가 OPENAI_API_KEY를 제거하므로 LLM 분류는 항상 실패하고
_KEYWORD_RULES 폴백이 동작한다.
"""

from __future__ import annotations

from agent.workflow_matcher import match_workflow


def test_balance_keywords_match_balance_inquiry():
    assert match_workflow("잔액 얼마야?") == "wf_balance_inquiry"


def test_transfer_keywords_match_external_transfer():
    assert match_workflow("김철수한테 5만원 보내줘") == "wf_external_transfer"


def test_unrelated_input_matches_nothing():
    assert match_workflow("오늘 날씨 어때") is None
