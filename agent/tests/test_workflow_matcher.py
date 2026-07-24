"""V3 계약 Manifest 기반 워크플로우 매칭 검증.

conftest가 OPENAI_API_KEY를 제거하므로 LLM 분류는 항상 실패하고
_KEYWORD_RULES 폴백이 동작한다.
"""

from __future__ import annotations

import agent.workflow_matcher as workflow_matcher
from agent.workflow_matcher import (
    _build_catalog,
    _IntentResult,
    _load_workflow_choices,
    match_workflow,
)


class _StubRouterLlm:
    """예외 없이 지정된 workflow_id를 반환하는 라우터 LLM 스텁."""

    def __init__(self, workflow_id: str | None) -> None:
        self._workflow_id = workflow_id

    def with_structured_output(self, schema: type) -> _StubRouterLlm:
        return self

    def invoke(self, prompt: str) -> _IntentResult:
        return _IntentResult(workflow_id=self._workflow_id)


def test_choices_include_manifest_example_utterances():
    """카탈로그 재료에 V3 계약의 example_utterances가 포함된다."""
    choices = {wid: example for wid, _, _, example in _load_workflow_choices()}
    assert "보내줘" in choices["wf_external_transfer"]
    assert "잔액" in choices["wf_balance_inquiry"]
    # 본인이체 예시에 '송금' 표현의 본인 계좌 발화가 포함돼야 한다
    assert "계좌끼리" in choices["wf_internal_transfer"]


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


def test_own_account_transfer_matches_internal_transfer():
    # 사람 대상(에게/한테) 없이 통장 간 이체는 본인이체로 매칭돼야 한다
    assert match_workflow("생활비통장으로 10만원 이체해줘") == "wf_internal_transfer"


def test_own_account_transfer_with_send_verbs_matches_internal():
    # '송금/보내' 표현이어도 본인 계좌 신호가 있으면 본인이체다
    assert match_workflow("제 계좌끼리의 송금 해줘") == "wf_internal_transfer"
    assert match_workflow("내 계좌끼리 5만원 송금해줘") == "wf_internal_transfer"
    assert match_workflow("내 통장끼리 돈 좀 옮겨줘") == "wf_internal_transfer"
    assert match_workflow("내 계좌로 10만원 송금해줘") == "wf_internal_transfer"


def test_bare_send_verbs_still_default_to_external():
    assert match_workflow("5만원 송금해줘") == "wf_external_transfer"


def test_compact_account_list_phrase_matches_account_list():
    assert match_workflow("계좌목록 보여줘") == "wf_account_list"


def test_llm_null_result_falls_back_to_keyword_rules(monkeypatch):
    """LLM이 예외 없이 null을 반환해도 키워드 폴백이 동작해야 한다."""
    monkeypatch.setattr(workflow_matcher, "get_llm", lambda **_: _StubRouterLlm(None))
    assert match_workflow("생활비통장으로 10만원 이체해줘") == "wf_internal_transfer"


def test_llm_invalid_result_falls_back_to_keyword_rules(monkeypatch):
    monkeypatch.setattr(
        workflow_matcher,
        "get_llm",
        lambda **_: _StubRouterLlm("wf_unknown"),
    )
    assert match_workflow("생활비통장으로 10만원 이체해줘") == "wf_internal_transfer"


def test_own_account_guard_overrides_llm_misclassification(monkeypatch):
    """강한 본인이체 신호는 LLM의 타인송금 오분류보다 우선한다."""
    monkeypatch.setattr(
        workflow_matcher,
        "get_llm",
        lambda **_: _StubRouterLlm("wf_external_transfer"),
    )
    assert match_workflow("신한 부계좌로 이체해줘") == "wf_internal_transfer"


def test_own_account_guard_skips_external_and_history_phrases(monkeypatch):
    """타인 계좌 목적지나 조회 발화는 결정적 가드에 걸리지 않는다."""
    monkeypatch.setattr(
        workflow_matcher,
        "get_llm",
        lambda **_: _StubRouterLlm("wf_external_transfer"),
    )
    assert match_workflow("내 계좌에서 홍길동 계좌로 5만원 송금해줘") == "wf_external_transfer"

    monkeypatch.setattr(
        workflow_matcher,
        "get_llm",
        lambda **_: _StubRouterLlm("wf_transaction_history"),
    )
    assert match_workflow("계좌 간 이체 내역 보여줘") == "wf_transaction_history"


def test_income_phrase_matches_amount_summary():
    # 지출뿐 아니라 입금 방향("들어왔어")도 기간 합계로 매칭돼야 한다
    assert match_workflow("이번달 얼마 들어왔어?") == "wf_period_amount_summary"


def test_unrelated_input_matches_nothing():
    assert match_workflow("오늘 날씨 어때") is None
