"""워크플로우 라우팅(분류기·검증기 분리) 검증.

conftest가 OPENAI_API_KEY를 제거하므로 별도 stub이 없으면 분류기/검증기 LLM은
실패하고 deterministic_fallback(강가드 + 키워드 규칙)이 동작한다. match_workflow는
route_workflow를 감싸 workflow_id만 반환하는 하위호환 래퍼다.
"""

from __future__ import annotations

import agent.workflow_routing as wr
from agent.workflow_matcher import match_workflow
from agent.workflow_routing import (
    WorkflowClassification,
    WorkflowVerification,
    _build_catalog,
    _load_choices,
    extract_routing_signals,
    resolve_workflow,
)

# ── 카탈로그 재료 ────────────────────────────────────────────────────────────


def test_choices_include_manifest_example_utterances():
    choices = {wid: example for wid, _, _, example in _load_choices()}
    assert "보내줘" in choices["wf_external_transfer"]
    assert "잔액" in choices["wf_balance_inquiry"]
    assert "계좌끼리" in choices["wf_internal_transfer"]


def test_build_catalog_format_and_size():
    choices = _load_choices()
    catalog = _build_catalog(choices)
    assert '(예: "' in catalog
    assert "step_id" not in catalog and "routes" not in catalog
    assert len(catalog.splitlines()) == len(choices)
    assert len(catalog) < 2000
    assert _build_catalog((("wf_x", "이름", "설명", ""),)) == "- wf_x: 이름 — 설명"


# ── 결정론 폴백 (LLM 실패 경로, conftest가 키 제거) ──────────────────────────


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
    assert match_workflow("생활비통장으로 10만원 이체해줘") == "wf_internal_transfer"


def test_own_account_transfer_with_send_verbs_matches_internal():
    assert match_workflow("제 계좌끼리의 송금 해줘") == "wf_internal_transfer"
    assert match_workflow("내 계좌끼리 5만원 송금해줘") == "wf_internal_transfer"
    assert match_workflow("내 통장끼리 돈 좀 옮겨줘") == "wf_internal_transfer"
    assert match_workflow("내 계좌로 10만원 송금해줘") == "wf_internal_transfer"


def test_bare_send_verbs_still_default_to_external():
    assert match_workflow("5만원 송금해줘") == "wf_external_transfer"


def test_compact_account_list_phrase_matches_account_list():
    assert match_workflow("계좌목록 보여줘") == "wf_account_list"


def test_income_phrase_matches_amount_summary():
    assert match_workflow("이번달 얼마 들어왔어?") == "wf_period_amount_summary"


def test_unrelated_input_matches_nothing():
    assert match_workflow("오늘 날씨 어때") is None


# ── 강가드가 조회·설정 신호에 양보(과잉 포섭 완화) ──────────────────────────


def test_fallback_guard_yields_to_setting_signal():
    """폴백에서도 '부계좌 + 이체동사'가 설정 신호와 겹치면 본인이체로 확정하지 않는다."""
    # "나가게 해"는 이체 동사가 아니라 기본계좌 설정 키워드로 폴백해야 한다.
    assert match_workflow("이제부터 신한 부계좌에서 나가게 해줘") == "wf_set_default_account"


def test_fallback_guard_yields_to_alias_signal():
    assert match_workflow("하나 부계좌를 비상금이라고 불러줘") == "wf_set_account_alias"


# ── extract_routing_signals ─────────────────────────────────────────────────


def test_signals_detect_setting_over_transfer():
    s = extract_routing_signals("이제부터 신한 부계좌에서 나가게 해줘")
    assert s.has_own_account_marker is True
    assert s.has_persistent_setting_expression is True
    assert s.has_person_marker is False


def test_signals_detect_amount_and_destination():
    s = extract_routing_signals("생활비통장으로 5만원 옮겨줘")
    assert s.has_amount_expression is True
    assert s.has_destination_expression is True


def test_signals_detect_person_marker():
    s = extract_routing_signals("민수에게 3만원 보내줘")
    assert s.has_person_marker is True


# ── resolve_workflow (순수 함수) ────────────────────────────────────────────


def test_resolve_accept_keeps_primary():
    c = WorkflowClassification(primary_workflow_id="wf_external_transfer", status="resolved")
    v = WorkflowVerification(verdict="accept", reason_code="VALID")
    r = resolve_workflow(c, v)
    assert r.status == "resolved"
    assert r.workflow_id == "wf_external_transfer"
    assert r.source == "classifier_verified"


def test_resolve_reject_setting_correction_is_adopted():
    """조회·설정형으로의 수정은 검증기 제안을 채택한다."""
    c = WorkflowClassification(primary_workflow_id="wf_internal_transfer", status="resolved")
    v = WorkflowVerification(
        verdict="reject",
        corrected_workflow_id="wf_set_default_account",
        reason_code="ACTION_MISMATCH",
    )
    r = resolve_workflow(c, v)
    assert r.status == "resolved"
    assert r.workflow_id == "wf_set_default_account"
    assert r.source == "verifier_corrected"


def test_resolve_execution_conflict_requires_confirmation():
    """실행형(transfer) 간 충돌은 자동 채택하지 않고 ambiguous로 보류한다."""
    c = WorkflowClassification(primary_workflow_id="wf_internal_transfer", status="resolved")
    v = WorkflowVerification(
        verdict="reject",
        corrected_workflow_id="wf_external_transfer",
        reason_code="INTERNAL_EXTERNAL_CONFLICT",
    )
    r = resolve_workflow(c, v)
    assert r.status == "ambiguous"
    assert set(r.candidates) == {"wf_internal_transfer", "wf_external_transfer"}
    assert r.source == "classifier_verifier_conflict"


def test_resolve_ambiguous_verdict():
    c = WorkflowClassification(
        primary_workflow_id="wf_set_default_account",
        alternative_workflow_ids=["wf_internal_transfer"],
        status="resolved",
    )
    v = WorkflowVerification(verdict="ambiguous", reason_code="INSUFFICIENT_EVIDENCE")
    r = resolve_workflow(c, v)
    assert r.status == "ambiguous"


# ── route_workflow 통합 (분류기·검증기 stub 주입) ───────────────────────────


class _StubLlm:
    """schema 타입에 따라 분류/검증 결과를 반환하는 stub."""

    def __init__(self, classification=None, verification=None):
        self._classification = classification
        self._verification = verification
        self._schema = None

    def with_structured_output(self, schema):
        self._schema = schema
        return self

    def invoke(self, prompt):
        if self._schema is WorkflowClassification:
            return self._classification
        return self._verification


def test_route_verifier_corrects_setting_over_transfer(monkeypatch):
    """분류기가 본인이체로 오분류해도 검증기가 기본계좌 설정으로 교정한다."""
    classification = WorkflowClassification(
        primary_workflow_id="wf_internal_transfer",
        alternative_workflow_ids=["wf_set_default_account"],
        evidence_phrases=["부계좌"],
        status="resolved",
    )
    verification = WorkflowVerification(
        verdict="reject",
        corrected_workflow_id="wf_set_default_account",
        reason_code="ACTION_MISMATCH",
    )
    monkeypatch.setattr(
        wr,
        "get_llm",
        lambda *a, **k: _StubLlm(classification=classification, verification=verification),
    )
    assert match_workflow("이제부터 신한 부계좌에서 나가게 해줘") == "wf_set_default_account"


def test_route_execution_conflict_falls_to_none(monkeypatch):
    """실행형 충돌은 ambiguous → match_workflow는 None(안전 폴백)."""
    classification = WorkflowClassification(
        primary_workflow_id="wf_internal_transfer",
        status="resolved",
    )
    verification = WorkflowVerification(
        verdict="reject",
        corrected_workflow_id="wf_external_transfer",
        reason_code="INTERNAL_EXTERNAL_CONFLICT",
    )
    monkeypatch.setattr(
        wr,
        "get_llm",
        lambda *a, **k: _StubLlm(classification=classification, verification=verification),
    )
    assert match_workflow("내 신한계좌에서 민수한테 3만원 보내줘") is None


def test_route_accept_returns_primary(monkeypatch):
    classification = WorkflowClassification(
        primary_workflow_id="wf_external_transfer",
        evidence_phrases=["민수에게", "보내줘"],
        status="resolved",
    )
    verification = WorkflowVerification(verdict="accept", reason_code="VALID")
    monkeypatch.setattr(
        wr,
        "get_llm",
        lambda *a, **k: _StubLlm(classification=classification, verification=verification),
    )
    assert match_workflow("민수에게 3만원 보내줘") == "wf_external_transfer"
