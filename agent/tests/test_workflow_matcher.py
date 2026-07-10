"""워크플로우 매칭 검증 (키워드 폴백 경로).

conftest가 OPENAI_API_KEY를 제거하므로 LLM 분류는 항상 실패하고
_KEYWORD_RULES 폴백이 동작한다.
"""

from __future__ import annotations

from agent.workflow_matcher import (
    _build_catalog,
    _load_workflow_choices,
    match_workflow,
)


def test_choices_include_example_utterance():
    """카탈로그 재료에 시트의 example_utterance가 포함된다."""
    choices = {wid: example for wid, _, _, example in _load_workflow_choices()}
    assert "보내줘" in choices["wf_external_transfer"]
    assert "잔액" in choices["wf_balance_inquiry"]


def test_build_catalog_format_and_size():
    """카탈로그는 워크플로우당 한 줄 + 예시 발화 — steps는 절대 안 들어간다."""
    choices = _load_workflow_choices()
    catalog = _build_catalog(choices)

    assert '(예: "' in catalog  # 예시 발화 포함
    assert "step_id" not in catalog and "routes" not in catalog
    assert len(catalog.splitlines()) == len(choices)  # 워크플로우 수만큼만
    assert len(catalog) < 2000  # 워크플로우당 한 줄 수준 유지 (토큰 낭비 방지 가드)

    # 예시가 없으면 괄호 생략
    assert _build_catalog((("wf_x", "이름", "설명", ""),)) == "- wf_x: 이름 — 설명"


def test_account_list_keywords_match():
    assert match_workflow("내 계좌 목록 보여줘") == "wf_account_list"


def test_transaction_history_keywords_match():
    assert match_workflow("지난주 거래 내역 보여줘") == "wf_transaction_history"


def test_period_summary_keywords_match():
    assert match_workflow("이번 달 얼마 썼어?") == "wf_period_amount_summary"


def test_balance_keywords_match_balance_inquiry():
    assert match_workflow("잔액 얼마야?") == "wf_balance_inquiry"


def test_transfer_keywords_match_external_transfer():
    assert match_workflow("김철수한테 5만원 보내줘") == "wf_external_transfer"


def test_unrelated_input_matches_nothing():
    assert match_workflow("오늘 날씨 어때") is None
