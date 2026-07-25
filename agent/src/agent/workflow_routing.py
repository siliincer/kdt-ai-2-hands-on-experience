"""Workflow Routing — 분류기·검증기 분리 라우팅 파이프라인.

기존 단일 LLM 분류(match_workflow)의 두 문제를 함께 보완한다.
  1. 결정론적 선가드(_is_own_account_transfer)가 LLM보다 먼저 워크플로우를
     확정해, "부계좌"·"내 계좌" 같은 엔티티 표현이 설정·조회 발화까지
     본인이체로 가로채는 과잉 포섭.
  2. 단일 LLM 분류 결과를 검증 없이 그대로 실행하는 위험.

구조:
    Global Guardrail(별도 노드)
      → LLM Workflow Classifier   (primary/alternatives/evidence/status)
      → Deterministic Signal Extractor (의미 신호만 추출, 확정하지 않음)
      → LLM Workflow Verifier     (accept/reject/ambiguous)
      → Workflow Resolution       (합의 확정 / 조회·설정 오류 수정 / 실행형 충돌은 보류)
      → (실패 시) Deterministic Fallback

주의: 라우팅 단계의 사용자 재확인(HITL)은 아직 배선돼 있지 않다. 이 버전은
ambiguous·실행형 충돌을 안전 폴백(no_match)으로 종료하고, 실제 되묻기는 후속
작업으로 분리한다. resolve_workflow는 그 지점을 status=ambiguous로 표시한다.
"""

from __future__ import annotations

import logging
import re
from functools import lru_cache
from hashlib import sha256
from typing import Literal, cast

from pydantic import BaseModel, Field

from agent.llm import get_llm
from agent.workflow_contracts import WorkflowContractStore

logger = logging.getLogger("agent.workflow_routing")

# ─────────────────────────────────────────────────────────────────────────────
# 스키마
# ─────────────────────────────────────────────────────────────────────────────


class WorkflowClassification(BaseModel):
    """1차 분류기 출력."""

    primary_workflow_id: str | None = Field(
        default=None,
        description="발화에 가장 적합한 워크플로우 id. 해당하는 것이 없으면 null.",
    )
    alternative_workflow_ids: list[str] = Field(
        default_factory=list,
        description="주 후보 외에 가능성이 있는 대안 워크플로우 id 목록. 없으면 빈 배열.",
    )
    evidence_phrases: list[str] = Field(
        default_factory=list,
        description="분류 근거가 된, 사용자 발화에 실제로 존재하는 구절.",
    )
    status: Literal["resolved", "ambiguous", "no_match"] = Field(
        default="no_match",
        description="resolved=하나로 확정, ambiguous=둘 이상 가능, no_match=해당 없음.",
    )


class RoutingSignals(BaseModel):
    """결정론적으로 추출한 의미 신호(확정하지 않고 검증·폴백에만 사용)."""

    has_person_marker: bool = False
    has_own_account_marker: bool = False
    has_transfer_action: bool = False
    has_setting_action: bool = False
    has_query_action: bool = False
    has_amount_expression: bool = False
    has_destination_expression: bool = False
    has_persistent_setting_expression: bool = False
    has_alias_expression: bool = False


class WorkflowVerification(BaseModel):
    """2차 검증기 출력."""

    verdict: Literal["accept", "reject", "ambiguous"] = Field(
        description="accept=분류 유지, reject=수정 제안, ambiguous=확정 불가.",
    )
    corrected_workflow_id: str | None = Field(
        default=None,
        description="reject일 때 제안하는 대체 워크플로우 id. 없으면 null.",
    )
    reason_code: Literal[
        "VALID",
        "ACTION_MISMATCH",
        "INTERNAL_EXTERNAL_CONFLICT",
        "QUERY_SETTING_CONFLICT",
        "INSUFFICIENT_EVIDENCE",
        "MULTIPLE_ACTIONS",
    ] = Field(default="VALID")
    evidence_phrases: list[str] = Field(default_factory=list)


class WorkflowResolution(BaseModel):
    """최종 라우팅 결정."""

    status: Literal["resolved", "ambiguous", "no_match", "failed"] = "no_match"
    workflow_id: str | None = None
    candidates: list[str] = Field(default_factory=list)
    source: Literal[
        "classifier_verified",
        "verifier_corrected",
        "classifier_verifier_conflict",
        "deterministic_fallback",
        "user_selected",
        "no_match",
    ] = "no_match"


# ─────────────────────────────────────────────────────────────────────────────
# 계약 카탈로그 (분류기 프롬프트용) + 워크플로우 타입 맵 (resolution용)
# ─────────────────────────────────────────────────────────────────────────────


@lru_cache(maxsize=1)
def _load_choices() -> tuple[tuple[str, str, str, str], ...]:
    """(workflow_id, name, description, example_utterances). global 타입 제외."""
    store = WorkflowContractStore()
    choices: list[tuple[str, str, str, str]] = []
    for workflow_id in store.workflow_ids():
        catalog = store.get_workflow(workflow_id)["catalog"]
        if catalog.get("workflow_type") == "global":
            continue
        choices.append(
            (
                workflow_id,
                str(catalog.get("workflow_name") or ""),
                str(catalog.get("description") or ""),
                str(catalog.get("example_utterances") or ""),
            )
        )
    return tuple(choices)


@lru_cache(maxsize=1)
def _workflow_types() -> dict[str, str]:
    """workflow_id → workflow_type(inquiry/setting_change/transfer/…)."""
    store = WorkflowContractStore()
    types: dict[str, str] = {}
    for workflow_id in store.workflow_ids():
        catalog = store.get_workflow(workflow_id)["catalog"]
        types[workflow_id] = str(catalog.get("workflow_type") or "")
    return types


def _valid_ids() -> set[str]:
    return {c[0] for c in _load_choices()}


def _build_catalog(choices: tuple[tuple[str, str, str, str], ...]) -> str:
    lines = []
    for wid, name, desc, example in choices:
        line = f"- {wid}: {name} — {desc}"
        if example:
            line += f' (예: "{example}")'
        lines.append(line)
    return "\n".join(lines)


def _is_execution_workflow(workflow_id: str | None) -> bool:
    """실행형(자금 이동) 워크플로우인지. 실행형 간 충돌은 자동 수정하지 않는다."""
    return bool(workflow_id) and _workflow_types().get(workflow_id or "") == "transfer"


# ─────────────────────────────────────────────────────────────────────────────
# 결정론적 Signal Extractor (확정하지 않음)
# ─────────────────────────────────────────────────────────────────────────────

_PERSON_MARKERS = ("에게", "한테")
_OWN_ACCOUNT_MARKERS = (
    "계좌끼리",
    "통장끼리",
    "본인 계좌",
    "본인계좌",
    "내 계좌",
    "내 통장",
    "제 계좌",
    "제 통장",
    "부계좌",
    "계좌 간",
)
_TRANSFER_VERBS = ("이체", "송금", "보내", "옮겨", "쏴", "부쳐", "이체해")
_SETTING_VERBS = ("바꿔", "바꾸", "변경", "설정", "지정", "등록")
_QUERY_MARKERS = ("얼마", "잔액", "내역", "보여", "알려", "확인", "있어", "썼", "쓴")
_PERSISTENT_MARKERS = ("이제부터", "앞으로", "기본", "나가게", "주로", "항상")
_ALIAS_MARKERS = ("별칭", "별명", "라고 불러", "라고 해", "이라고 부", "라고 부", "이름 붙", "이름을 붙")

_AMOUNT_RE = re.compile(r"\d[\d,]*\s*(?:원|만|천|억)|[영일이삼사오육칠팔구십백천만억]+\s*원")
_DESTINATION_RE = re.compile(r"(?:부?계좌|통장|은행)\s*(?:으로|로)\b")


def extract_routing_signals(text: str) -> RoutingSignals:
    """발화의 의미 신호를 결정론적으로 추출한다. 워크플로우를 확정하지 않는다."""
    t = text or ""
    return RoutingSignals(
        has_person_marker=any(m in t for m in _PERSON_MARKERS),
        has_own_account_marker=any(m in t for m in _OWN_ACCOUNT_MARKERS),
        has_transfer_action=any(m in t for m in _TRANSFER_VERBS),
        has_setting_action=any(m in t for m in _SETTING_VERBS),
        has_query_action=any(m in t for m in _QUERY_MARKERS),
        has_amount_expression=bool(_AMOUNT_RE.search(t)),
        has_destination_expression=bool(_DESTINATION_RE.search(t)),
        has_persistent_setting_expression=any(m in t for m in _PERSISTENT_MARKERS),
        has_alias_expression=any(m in t for m in _ALIAS_MARKERS),
    )


# ─────────────────────────────────────────────────────────────────────────────
# 1차 분류기 (LLM)
# ─────────────────────────────────────────────────────────────────────────────

_CLASSIFIER_PROMPT = (
    "너는 금융 업무 라우터다. 사용자 발화에서 사용자가 실제로 수행하려는 금융 "
    "행위를 기준으로 가장 적절한 워크플로우를 분류하라.\n\n"
    "중요 원칙:\n"
    "1. 계좌명, 은행명, 계좌, 통장, 부계좌는 대상 엔티티이며 이 표현만으로 "
    "워크플로우를 결정하지 않는다.\n"
    "2. 실제 자금 이동 요청이 있어야 transfer 워크플로우로 분류한다.\n"
    "3. '기본', '이제부터', '앞으로', '나가게 해줘'는 기본 출금 계좌 설정 신호다.\n"
    "4. '별칭', '라고 불러', '이름을 붙여'는 계좌 별칭 설정 신호다.\n"
    "5. '얼마 있어', '잔액', '내역'은 조회 행위다.\n"
    "6. 발화의 특정 단어 하나가 아니라 문장 전체의 핵심 행위를 기준으로 판단한다.\n"
    "7. 두 워크플로우가 모두 가능하고 하나로 확정할 근거가 부족하면 status를 "
    "ambiguous로 둔다.\n\n"
    "본인 소유 계좌 사이의 자금 이동(부계좌·다른 내 계좌 포함)은 '송금'이나 "
    "'보내' 표현이 있어도 wf_internal_transfer다. 다른 사람(수취인)에게 보내는 "
    "경우에만 wf_external_transfer다.\n\n"
    "예시:\n"
    '입력: "신한 부계좌에서 이제부터 나가게 해줘."\n'
    "출력: primary=wf_set_default_account, alternatives=[], "
    'evidence=["이제부터","나가게 해줘"], status=resolved\n'
    '입력: "신한 부계좌에서 카카오 계좌로 3만원 옮겨줘."\n'
    "출력: primary=wf_internal_transfer, alternatives=[], "
    'evidence=["카카오 계좌로","3만원","옮겨줘"], status=resolved\n'
    '입력: "하나 부계좌를 비상금이라고 부를게."\n'
    "출력: primary=wf_set_account_alias, alternatives=[], "
    'evidence=["비상금이라고 부를게"], status=resolved\n'
    '입력: "신한 계좌 어떻게 할 수 있어?"\n'
    "출력: primary=null, alternatives=[], evidence=[], status=ambiguous\n\n"
    "[워크플로우 목록]\n{catalog}\n\n"
    "[사용자 발화]\n{text}"
)


def classify_workflow(text: str) -> WorkflowClassification:
    """LLM으로 워크플로우 후보를 분류한다. 실패 시 예외를 그대로 올린다."""
    catalog = _build_catalog(_load_choices())
    llm = get_llm().with_structured_output(WorkflowClassification)
    result = cast(
        WorkflowClassification,
        llm.invoke(_CLASSIFIER_PROMPT.format(catalog=catalog, text=text)),
    )
    valid = _valid_ids()
    # 무효 id 정리: primary가 카탈로그 밖이면 no_match로 낮추고, 대안도 필터한다.
    if result.primary_workflow_id not in valid:
        result.primary_workflow_id = None
        if result.status == "resolved":
            result.status = "no_match"
    result.alternative_workflow_ids = [w for w in result.alternative_workflow_ids if w in valid]
    return result


# ─────────────────────────────────────────────────────────────────────────────
# 2차 검증기 (LLM)
# ─────────────────────────────────────────────────────────────────────────────

_VERIFIER_PROMPT = (
    "너는 금융 Workflow 분류 검증기다. 사용자 발화와 분류기가 선택한 Workflow를 "
    "비교하여, 분류 결과가 실제 사용자 행위와 일치하는지 검증하라.\n\n"
    "새로운 분류를 처음부터 수행하는 것이 아니라, 제시된 분류 결과와 사용자 발화 "
    "사이의 모순을 찾아라.\n\n"
    "다음 기준을 확인하라.\n"
    "1. 실제 자금 이동 요청이 없는 발화를 transfer로 분류하지 않았는가.\n"
    "2. 별칭 또는 기본계좌 설정 발화를 transfer로 분류하지 않았는가.\n"
    "3. 조회 발화를 설정이나 실행형 Workflow로 분류하지 않았는가.\n"
    "4. 본인계좌 간 이동과 타인송금을 혼동하지 않았는가.\n"
    "5. 계좌명, 은행명, 부계좌와 같은 엔티티 표현 하나만을 근거로 Workflow를 "
    "선택하지 않았는가.\n"
    "6. 분류기의 evidence_phrases가 실제 사용자 발화에 존재하고, 선택한 "
    "Workflow를 뒷받침하는가.\n"
    "7. 결정론적 signal과 분류 결과가 명백히 충돌하지 않는가.\n"
    "8. 근거가 부족하거나 두 개 이상의 Workflow가 가능하면 ambiguous로 판단하라.\n\n"
    "분류기의 결과는 참고 정보일 뿐 정답이 아니다. 분류기의 결론을 반복하지 말고, "
    "사용자 발화와 선택된 Workflow 사이의 모순을 우선적으로 찾아라. 수정이 "
    "필요하면 corrected_workflow_id에 올바른 id를 넣어라.\n\n"
    "reason_code는 다음 중 하나다: VALID, ACTION_MISMATCH, "
    "INTERNAL_EXTERNAL_CONFLICT, QUERY_SETTING_CONFLICT, INSUFFICIENT_EVIDENCE, "
    "MULTIPLE_ACTIONS.\n\n"
    "예시:\n"
    '발화: "이제부터 신한 부계좌에서 나가게 해줘." / 분류기: wf_internal_transfer\n'
    "→ verdict=reject, corrected=wf_set_default_account, reason=ACTION_MISMATCH\n"
    '발화: "내 신한계좌에서 민수한테 3만원 보내줘." / 분류기: wf_internal_transfer\n'
    "→ verdict=reject, corrected=wf_external_transfer, reason=INTERNAL_EXTERNAL_CONFLICT\n"
    '발화: "민수에게 3만원 보내줘." / 분류기: wf_external_transfer\n'
    "→ verdict=accept, corrected=null, reason=VALID\n"
    '발화: "신한 계좌로 해줘." / 분류기: wf_set_default_account\n'
    "→ verdict=ambiguous, corrected=null, reason=INSUFFICIENT_EVIDENCE\n\n"
    "[워크플로우 목록]\n{catalog}\n\n"
    "[사용자 발화]\n{text}\n\n"
    "[분류기 결과]\nprimary={primary}\nalternatives={alternatives}\n"
    "evidence={evidence}\nstatus={status}\n\n"
    "[결정론 신호]\n{signals}"
)


def verify_workflow(
    text: str,
    classification: WorkflowClassification,
    signals: RoutingSignals,
) -> WorkflowVerification:
    """분류 결과와 발화의 모순을 검증한다. 실패 시 예외를 그대로 올린다."""
    catalog = _build_catalog(_load_choices())
    llm = get_llm().with_structured_output(WorkflowVerification)
    result = cast(
        WorkflowVerification,
        llm.invoke(
            _VERIFIER_PROMPT.format(
                catalog=catalog,
                text=text,
                primary=classification.primary_workflow_id,
                alternatives=classification.alternative_workflow_ids,
                evidence=classification.evidence_phrases,
                status=classification.status,
                signals=signals.model_dump(),
            )
        ),
    )
    if result.corrected_workflow_id not in _valid_ids():
        result.corrected_workflow_id = None
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Resolution 정책
# ─────────────────────────────────────────────────────────────────────────────


def _merge_candidates(
    classification: WorkflowClassification,
    verification: WorkflowVerification,
) -> list[str]:
    seen: list[str] = []
    for wid in (
        classification.primary_workflow_id,
        verification.corrected_workflow_id,
        *classification.alternative_workflow_ids,
    ):
        if wid and wid not in seen:
            seen.append(wid)
    return seen


def _requires_user_confirmation(original: str | None, corrected: str | None) -> bool:
    """실행형(transfer) 간 수정은 자동 채택하지 않고 사용자 확인이 필요하다."""
    return _is_execution_workflow(original) and _is_execution_workflow(corrected)


def resolve_workflow(
    classification: WorkflowClassification,
    verification: WorkflowVerification,
) -> WorkflowResolution:
    """분류기·검증기 결과를 합쳐 최종 라우팅을 결정한다."""
    if verification.verdict == "accept":
        if classification.primary_workflow_id:
            return WorkflowResolution(
                status="resolved",
                workflow_id=classification.primary_workflow_id,
                source="classifier_verified",
            )
        # 분류기가 no_match인데 검증기가 accept한 모순 → 확정 불가.
        return WorkflowResolution(status="no_match", source="no_match")

    if verification.verdict == "ambiguous":
        return WorkflowResolution(
            status="ambiguous",
            candidates=_merge_candidates(classification, verification),
            source="classifier_verifier_conflict",
        )

    # verdict == "reject"
    corrected = verification.corrected_workflow_id
    if corrected is None:
        return WorkflowResolution(
            status="ambiguous",
            candidates=_merge_candidates(classification, verification),
            source="classifier_verifier_conflict",
        )

    if _requires_user_confirmation(classification.primary_workflow_id, corrected):
        # 실행형 간 충돌 — 자동 수정하지 않고 확인 필요(현재는 안전 폴백에서 no_match).
        return WorkflowResolution(
            status="ambiguous",
            candidates=[c for c in (classification.primary_workflow_id, corrected) if c],
            source="classifier_verifier_conflict",
        )

    # 조회·설정형 수정은 검증기 제안을 채택한다.
    return WorkflowResolution(
        status="resolved",
        workflow_id=corrected,
        source="verifier_corrected",
    )


# ─────────────────────────────────────────────────────────────────────────────
# 결정론적 폴백 (LLM 실패 시에만)
#
# 설계 원칙(P0/P10): 기존의 결정론적 선가드(_is_own_account_transfer)와 키워드
# 규칙을 "LLM보다 먼저 확정하는 선가드"에서 "LLM 실패 시에만 도는 폴백"으로
# 옮긴다. 검증된 기존 규칙을 계승해 호환성을 유지하되, 본인이체 강가드에
# 조회·설정 신호 제외를 추가해 과잉 포섭을 완화한다.
# ─────────────────────────────────────────────────────────────────────────────

# 기존 키워드 규칙(위에서부터 first-match). 구체 키워드가 위, 범용어는 맨 아래.
_KEYWORD_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("에게", "한테"), "wf_external_transfer"),
    # "부계좌"는 이체·설정·별칭·조회에 모두 등장하는 순수 엔티티라 internal 신호로
    # 쓰지 않는다(진짜 본인이체는 위 강가드가 own_account+transfer로 이미 잡는다).
    (
        ("계좌끼리", "통장끼리", "옮겨", "본인 계좌", "내 계좌로", "통장으로", "계좌 간", "이체"),
        "wf_internal_transfer",
    ),
    (("송금", "보내"), "wf_external_transfer"),
    (("기본", "출금 계좌로", "나가게 해"), "wf_set_default_account"),
    (("별칭", "라고 해", "라 해", "라고 불러", "라 불러", "이름 붙"), "wf_set_account_alias"),
    (
        (
            "계좌 목록",
            "계좌목록",
            "계좌 뭐",
            "무슨 계좌",
            "어떤 계좌",
            "계좌 다 보",
            "계좌 확인",
            "계좌를 보여",
            "계좌 보여",
            "내 계좌",
        ),
        "wf_account_list",
    ),
    (("거래내역", "거래 내역", "결제 내역", "이용 내역", "사용 내역", "입출금 내역"), "wf_transaction_history"),
    (("얼마 썼", "얼마 쓴", "지출", "소비", "얼마 들어", "얼마 받", "수입", "입금 얼마"), "wf_period_amount_summary"),
    (("잔액", "통장", "얼마 있어", "얼마야"), "wf_balance_inquiry"),
)


def _strong_internal_transfer_signal(signals: RoutingSignals) -> bool:
    """사람 표지 없이 본인 계좌 신호와 이체 동사가 함께 있으면 본인이체.

    기존 _is_own_account_transfer를 신호 기반으로 옮기되, 조회("얼마/내역")·
    설정("바꿔/변경") 신호가 있으면 양보해 과잉 포섭을 줄인다.
    """
    if signals.has_person_marker:
        return False
    if signals.has_query_action or signals.has_setting_action:
        return False
    return signals.has_own_account_marker and signals.has_transfer_action


def deterministic_fallback(text: str, signals: RoutingSignals) -> WorkflowResolution:
    """LLM 실패 시 강가드 + 키워드 규칙으로 최소 라우팅을 수행한다."""
    if _strong_internal_transfer_signal(signals):
        return WorkflowResolution(
            status="resolved",
            workflow_id="wf_internal_transfer",
            source="deterministic_fallback",
        )
    for keywords, workflow_id in _KEYWORD_RULES:
        if any(k in text for k in keywords):
            return WorkflowResolution(
                status="resolved",
                workflow_id=workflow_id,
                source="deterministic_fallback",
            )
    return WorkflowResolution(status="no_match", source="no_match")


# ─────────────────────────────────────────────────────────────────────────────
# 오케스트레이터
# ─────────────────────────────────────────────────────────────────────────────


def route_workflow(user_input: str) -> WorkflowResolution:
    """분류 → 신호 추출 → 검증 → resolution. LLM 실패 시 결정론 폴백."""
    text = user_input or ""
    signals = extract_routing_signals(text)

    try:
        classification = classify_workflow(text)
    except Exception:
        resolution = deterministic_fallback(text, signals)
        _log_routing(text, None, signals, None, resolution)
        return resolution

    try:
        verification = verify_workflow(text, classification, signals)
    except Exception:
        # 검증기만 실패: 분류기가 확정한 경우에만 신뢰하고, 아니면 폴백.
        if classification.status == "resolved" and classification.primary_workflow_id:
            resolution = WorkflowResolution(
                status="resolved",
                workflow_id=classification.primary_workflow_id,
                source="classifier_verified",
            )
        else:
            resolution = deterministic_fallback(text, signals)
        _log_routing(text, classification, signals, None, resolution)
        return resolution

    resolution = resolve_workflow(classification, verification)
    _log_routing(text, classification, signals, verification, resolution)
    return resolution


def _log_routing(
    text: str,
    classification: WorkflowClassification | None,
    signals: RoutingSignals,
    verification: WorkflowVerification | None,
    resolution: WorkflowResolution,
) -> None:
    """관측성: 분류·신호·검증·최종 결정을 구조화 로그로 남긴다(원문은 해시)."""
    logger.info(
        "workflow_routing",
        extra={
            "routing": {
                "user_input_hash": sha256(text.encode("utf-8")).hexdigest()[:16],
                "classifier": classification.model_dump() if classification else None,
                "signals": signals.model_dump(),
                "verifier": verification.model_dump() if verification else None,
                "resolution": resolution.model_dump(),
            }
        },
    )
