"""워크플로우 라우팅(분류기·검증기 분리 + 결정론 Resolution) 검증.

결정론 키워드 폴백은 제거됐다. conftest가 OPENAI_API_KEY를 제거하므로 stub 없이
LLM을 호출하면 실패하고, route_workflow는 status="failed"로 안전 종료한다.
자연어 의미 판단은 stub으로 분류기·검증기 결과를 주입해 검증하고, resolution
정책은 순수 함수로 검증한다.
"""

from __future__ import annotations

import agent.workflow_routing as wr
from agent.workflow_matcher import match_workflow
from agent.workflow_routing import (
    WorkflowClassification,
    WorkflowVerification,
    _build_catalog,
    _load_choices,
    resolve_workflow,
    route_workflow,
)

# ── 카탈로그 재료 ────────────────────────────────────────────────────────────


def test_choices_include_manifest_example_utterances():
    choices = {wid: example for wid, _, _, example in _load_choices()}
    assert "보내줘" in choices["wf_external_transfer"]
    assert "잔액" in choices["wf_balance_inquiry"]


def test_build_catalog_format_and_size():
    choices = _load_choices()
    catalog = _build_catalog(choices)
    assert '(예: "' in catalog
    assert "step_id" not in catalog and "routes" not in catalog
    assert len(catalog.splitlines()) == len(choices)
    assert len(catalog) < 2000
    assert _build_catalog((("wf_x", "이름", "설명", ""),)) == "- wf_x: 이름 — 설명"


# ── resolve_workflow 정책 (순수 함수, LLM 불필요) ──────────────────────────


def _c(primary, status="resolved", alts=None):
    return WorkflowClassification(
        primary_workflow_id=primary,
        alternative_workflow_ids=alts or [],
        status=status,
    )


def _v(verdict, corrected=None, reason="VALID"):
    return WorkflowVerification(verdict=verdict, corrected_workflow_id=corrected, reason_code=reason)


def test_accept_keeps_primary():
    r = resolve_workflow(_c("wf_balance_inquiry"), _v("accept"))
    assert (r.status, r.workflow_id, r.source) == ("resolved", "wf_balance_inquiry", "classifier_verified")


def test_query_to_query_correction_is_adopted():
    r = resolve_workflow(
        _c("wf_transaction_history"),
        _v("reject", "wf_period_amount_summary", "ACTION_MISMATCH"),
    )
    assert (r.status, r.workflow_id, r.source) == ("resolved", "wf_period_amount_summary", "verifier_corrected")


def test_query_correction_blocked_on_insufficient_evidence():
    r = resolve_workflow(
        _c("wf_transaction_history"),
        _v("reject", "wf_period_amount_summary", "INSUFFICIENT_EVIDENCE"),
    )
    assert r.status == "ambiguous"


def test_execution_conflict_is_ambiguous():
    r = resolve_workflow(
        _c("wf_internal_transfer"),
        _v("reject", "wf_external_transfer", "INTERNAL_EXTERNAL_CONFLICT"),
    )
    assert r.status == "ambiguous"
    assert set(r.candidates) == {"wf_internal_transfer", "wf_external_transfer"}


def test_transfer_to_setting_correction_is_ambiguous():
    """교차 타입 수정(실행형→설정형)은 자동 채택하지 않고 사용자 확인으로 보류."""
    r = resolve_workflow(
        _c("wf_internal_transfer"),
        _v("reject", "wf_set_default_account", "ACTION_MISMATCH"),
    )
    assert r.status == "ambiguous"
    assert set(r.candidates) == {"wf_internal_transfer", "wf_set_default_account"}


def test_setting_to_setting_correction_is_ambiguous():
    r = resolve_workflow(
        _c("wf_set_account_alias"),
        _v("reject", "wf_set_default_account", "ACTION_MISMATCH"),
    )
    assert r.status == "ambiguous"


def test_invalid_primary_fails():
    r = resolve_workflow(_c("wf_bogus"), _v("accept"))
    assert (r.status, r.source, r.reason_code) == ("failed", "invalid_classifier_output", "INVALID_CLASSIFIER_OUTPUT")


def test_reject_same_workflow_fails():
    r = resolve_workflow(
        _c("wf_internal_transfer"),
        _v("reject", "wf_internal_transfer", "ACTION_MISMATCH"),
    )
    assert (r.status, r.source, r.reason_code) == ("failed", "invalid_verifier_output", "INVALID_VERIFIER_OUTPUT")


def test_reject_without_correction_is_ambiguous():
    r = resolve_workflow(_c("wf_internal_transfer"), _v("reject", None, "ACTION_MISMATCH"))
    assert r.status == "ambiguous"


def test_verifier_ambiguous_is_ambiguous():
    r = resolve_workflow(_c("wf_set_default_account"), _v("ambiguous", None, "INSUFFICIENT_EVIDENCE"))
    assert r.status == "ambiguous"


def test_classifier_ambiguous_stays_ambiguous_even_on_accept():
    r = resolve_workflow(
        _c("wf_set_default_account", status="ambiguous", alts=["wf_internal_transfer"]),
        _v("accept"),
    )
    assert r.status == "ambiguous"
    assert r.source == "classifier_ambiguous"


def test_classifier_no_match_stays_no_match():
    r = resolve_workflow(_c(None, status="no_match"), _v("accept"))
    assert (r.status, r.source) == ("no_match", "classifier_no_match")


def test_no_match_with_correction_becomes_ambiguous():
    r = resolve_workflow(
        _c(None, status="no_match"),
        _v("reject", "wf_balance_inquiry", "ACTION_MISMATCH"),
    )
    assert r.status == "ambiguous"
    assert r.candidates == ["wf_balance_inquiry"]


# ── route_workflow / match_workflow (stub 주입) ─────────────────────────────


class _StubLlm:
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


def test_route_verifier_corrects_query(monkeypatch):
    monkeypatch.setattr(
        wr,
        "get_llm",
        lambda *a, **k: _StubLlm(
            classification=_c("wf_transaction_history"),
            verification=_v("reject", "wf_period_amount_summary", "ACTION_MISMATCH"),
        ),
    )
    assert match_workflow("이번 달 스타벅스에서 얼마 썼어?") == "wf_period_amount_summary"


def test_route_accept_returns_primary(monkeypatch):
    monkeypatch.setattr(
        wr,
        "get_llm",
        lambda *a, **k: _StubLlm(classification=_c("wf_external_transfer"), verification=_v("accept")),
    )
    assert match_workflow("민수에게 3만원 보내줘") == "wf_external_transfer"


def test_route_execution_conflict_is_none(monkeypatch):
    """실행형 충돌은 ambiguous → match_workflow는 None(HITL은 그래프에서 처리)."""
    monkeypatch.setattr(
        wr,
        "get_llm",
        lambda *a, **k: _StubLlm(
            classification=_c("wf_internal_transfer"),
            verification=_v("reject", "wf_external_transfer", "INTERNAL_EXTERNAL_CONFLICT"),
        ),
    )
    assert match_workflow("내 신한계좌에서 민수한테 3만원 보내줘") is None


def test_route_llm_failure_is_safe_failed():
    """conftest가 OPENAI_API_KEY를 제거 → 분류기 LLM 실패 → failed → match None."""
    r = route_workflow("민수에게 3만원 보내줘")
    assert r.status == "failed"
    assert r.source == "classifier_failed"
    assert match_workflow("민수에게 3만원 보내줘") is None


def test_null_string_primary_is_normalized_not_failed(monkeypatch):
    """일부 모델(gemini)이 JSON null 대신 문자열 'null'을 채워도 failed가 아니라
    ambiguous로 처리돼야 한다."""
    monkeypatch.setattr(
        wr,
        "get_llm",
        lambda *a, **k: _StubLlm(
            classification=WorkflowClassification(primary_workflow_id="null", status="ambiguous"),
            verification=_v("ambiguous", None, "INSUFFICIENT_EVIDENCE"),
        ),
    )
    r = route_workflow("신한 계좌로 해줘")
    assert r.status == "ambiguous"
    assert match_workflow("신한 계좌로 해줘") is None


def test_verifier_disabled_uses_classifier(monkeypatch):
    monkeypatch.setenv("WORKFLOW_VERIFIER_ENABLED", "false")
    monkeypatch.setattr(
        wr,
        "get_llm",
        lambda *a, **k: _StubLlm(classification=_c("wf_account_list")),
    )
    assert match_workflow("내 계좌 목록 보여줘") == "wf_account_list"
