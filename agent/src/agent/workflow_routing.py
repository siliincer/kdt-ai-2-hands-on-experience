"""Workflow Routing — 분류기·검증기 분리 라우팅 파이프라인.

핵심 원칙: 자연어의 의미는 LLM 분류기와 검증기가 판단하고, 두 판단 결과를
어떻게 처리할지는 결정론적 Resolution 코드로 결정한다. 결정론은 세 번째
분류기가 아니라 Resolution 정책이다.

    Global Guardrail(별도 노드)
      → LLM Workflow Classifier   (primary / alternatives / evidence / status)
      → LLM Workflow Verifier      (accept / reject / ambiguous, 수정 후보)
      → Deterministic Resolution   (출력 검증 + 결과 결합 + 자동수정 정책)
           - resolved   → Workflow Subgraph
           - ambiguous  → 사용자 확인(라우팅 HITL)
           - no_match   → 매칭 워크플로우 없음 안내
           - failed     → 안전 실패 안내

결정론이 담당하는 것: 분류기·검증기 출력이 유효한가 / 두 결과가 합의했는가 /
충돌 시 자동 수정이 가능한가 / 사용자 확인이 필요한가 / 실패 시 안전하게
종료하는가. 자연어 의미를 다시 판단하지 않는다(키워드·정규식 라우팅 금지).

LLM 호출이 실패하면 키워드로 강제 확정하지 않고 status="failed"로 안전하게
종료한다(금융 도메인 기본값). 결정론 키워드·정규식 폴백은 존재하지 않는다.

환경변수:
  WORKFLOW_VERIFIER_ENABLED=true(기본) | false
    false면 검증 단계를 건너뛰고 분류기 결과를 유효성 검증 후 직접 사용한다.
  WORKFLOW_VERIFIER_FAIL_MODE=closed(기본) | fallback
    LLM 실패 시 동작. closed=안전 실패(failed). fallback=분류기가 resolved면
    그 결과를 신뢰(가용성 우선). 금융 Agent 기본값은 closed.
  WORKFLOW_QUERY_AUTO_CORRECTION_ENABLED=true(기본) | false
    조회형→조회형 검증기 수정을 자동 적용할지. false면 사용자 확인으로 보류.
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from hashlib import sha256
from typing import Literal, cast

from pydantic import BaseModel, Field

from agent.llm import get_llm
from agent.workflow_contracts import WorkflowContractStore

logger = logging.getLogger("agent.workflow_routing")

# ─────────────────────────────────────────────────────────────────────────────
# 환경변수 (intent_gate.py 패턴 답습)
# ─────────────────────────────────────────────────────────────────────────────


def verifier_enabled() -> bool:
    """검증기 사용 여부. 기본 활성(true). false면 분류기 결과를 직접 사용한다."""
    raw = os.getenv("WORKFLOW_VERIFIER_ENABLED", "true").strip().lower()
    return raw not in ("false", "0", "no", "off")


def _verifier_fail_mode() -> str:
    """검증기·분류기 LLM 실패 시 동작. closed(기본) | fallback."""
    raw = os.getenv("WORKFLOW_VERIFIER_FAIL_MODE", "closed").strip().lower()
    return "fallback" if raw == "fallback" else "closed"


def query_auto_correction_enabled() -> bool:
    """조회형→조회형 검증기 수정 자동 적용 여부. 기본 활성(true)."""
    raw = os.getenv("WORKFLOW_QUERY_AUTO_CORRECTION_ENABLED", "true").strip().lower()
    return raw not in ("false", "0", "no", "off")


# ─────────────────────────────────────────────────────────────────────────────
# 스키마
# ─────────────────────────────────────────────────────────────────────────────


class WorkflowClassification(BaseModel):
    """1차 분류기 출력."""

    primary_workflow_id: str | None = Field(
        default=None,
        description="사용자 발화에 가장 적합한 Workflow ID. 없으면 null.",
    )
    alternative_workflow_ids: list[str] = Field(
        default_factory=list,
        description="주 후보 외에 가능성이 있는 대안 Workflow ID. 없으면 빈 배열.",
    )
    evidence_phrases: list[str] = Field(
        default_factory=list,
        description="분류 근거가 된, 사용자 발화에 실제로 존재하는 구절.",
    )
    status: Literal["resolved", "ambiguous", "no_match"] = Field(
        default="no_match",
        description="resolved=하나로 확정, ambiguous=둘 이상 가능, no_match=해당 없음.",
    )


VerificationReasonCode = Literal[
    "VALID",
    "ACTION_MISMATCH",
    "INTERNAL_EXTERNAL_CONFLICT",
    "QUERY_SETTING_CONFLICT",
    "INSUFFICIENT_EVIDENCE",
    "MULTIPLE_ACTIONS",
    "INVALID_CLASSIFIER_OUTPUT",
]


class WorkflowVerification(BaseModel):
    """2차 검증기 출력."""

    verdict: Literal["accept", "reject", "ambiguous"] = Field(
        description="accept=분류 유지, reject=수정 제안, ambiguous=확정 불가.",
    )
    corrected_workflow_id: str | None = Field(
        default=None,
        description="분류 결과가 잘못된 경우 제안하는 수정 Workflow ID. 없으면 null.",
    )
    reason_code: VerificationReasonCode = Field(default="VALID")
    evidence_phrases: list[str] = Field(default_factory=list)


ResolutionSource = Literal[
    "classifier_verified",
    "verifier_corrected",
    "classifier_verifier_conflict",
    "classifier_no_match",
    "classifier_ambiguous",
    "invalid_classifier_output",
    "invalid_verifier_output",
    "classifier_failed",
    "verifier_failed",
    "user_selected",
]


class WorkflowResolution(BaseModel):
    """최종 라우팅 결정."""

    status: Literal["resolved", "ambiguous", "no_match", "failed"] = "no_match"
    workflow_id: str | None = None
    candidates: list[str] = Field(default_factory=list)
    source: ResolutionSource = "classifier_no_match"
    reason_code: str | None = None


# ─────────────────────────────────────────────────────────────────────────────
# 계약 카탈로그 (분류기·검증기 프롬프트용) + 워크플로우 타입 맵 (resolution용)
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


def workflow_name(workflow_id: str) -> str:
    """사용자 확인 UI 라벨용 워크플로우 표시명."""
    for wid, name, _desc, _ex in _load_choices():
        if wid == workflow_id:
            return name or workflow_id
    return workflow_id


def _build_catalog(choices: tuple[tuple[str, str, str, str], ...]) -> str:
    lines = []
    for wid, name, desc, example in choices:
        line = f"- {wid}: {name} — {desc}"
        if example:
            line += f' (예: "{example}")'
        lines.append(line)
    return "\n".join(lines)


# 의미상 워크플로우 유형(자동수정 정책용). Manifest workflow_type을 그대로 쓴다.
#   transfer      → execution (실행형, 실제 자금 이동)
#   setting_change→ setting
#   inquiry       → query
def _risk_class(workflow_id: str | None) -> str | None:
    """워크플로우의 의미 유형: execution | setting | query | None."""
    if not workflow_id:
        return None
    mapping = {
        "transfer": "execution",
        "setting_change": "setting",
        "inquiry": "query",
    }
    return mapping.get(_workflow_types().get(workflow_id, ""))


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


# 일부 모델(예 gemini)이 JSON null 대신 문자열 "null"/"none"을 채우는 것을 흡수한다.
_NULL_PLACEHOLDERS = {"null", "none", "n/a", "na", "nil", ""}


def _normalize_workflow_id(value: str | None) -> str | None:
    if value is None:
        return None
    return None if value.strip().lower() in _NULL_PLACEHOLDERS else value


def classify_workflow(text: str) -> WorkflowClassification:
    """LLM으로 워크플로우 후보를 분류한다. 실패 시 예외를 그대로 올린다."""
    catalog = _build_catalog(_load_choices())
    llm = get_llm().with_structured_output(WorkflowClassification)
    result = cast(
        WorkflowClassification,
        llm.invoke(_CLASSIFIER_PROMPT.format(catalog=catalog, text=text)),
    )
    # "null" 문자열을 실제 null로 정규화하고, 대안 ID만 유효성 필터한다(무효
    # primary는 resolve_workflow가 failed로 처리한다).
    valid = _valid_ids()
    result.primary_workflow_id = _normalize_workflow_id(result.primary_workflow_id)
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
    "7. 근거가 부족하거나 두 개 이상의 Workflow가 가능하면 ambiguous로 판단하라.\n\n"
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
    "evidence={evidence}\nstatus={status}"
)


def verify_workflow(
    text: str,
    classification: WorkflowClassification,
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
            )
        ),
    )
    result.corrected_workflow_id = _normalize_workflow_id(result.corrected_workflow_id)
    if result.corrected_workflow_id not in _valid_ids():
        result.corrected_workflow_id = None
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Resolution 정책 (결정론 — 자연어 재판단 없음, 결과 결합만)
# ─────────────────────────────────────────────────────────────────────────────


def _merge_valid_candidates(*values: str | list[str] | None) -> list[str]:
    """유효한 workflow_id를 순서 유지·중복 제거로 병합한다."""
    valid = _valid_ids()
    candidates: list[str] = []
    for value in values:
        items = [value] if isinstance(value, str) else (value or [])
        for workflow_id in items:
            if workflow_id in valid and workflow_id not in candidates:
                candidates.append(workflow_id)
    return candidates


def _ambiguous(
    classification: WorkflowClassification,
    verification: WorkflowVerification,
    *,
    source: ResolutionSource,
) -> WorkflowResolution:
    return WorkflowResolution(
        status="ambiguous",
        workflow_id=None,
        candidates=_merge_valid_candidates(
            classification.primary_workflow_id,
            classification.alternative_workflow_ids,
            verification.corrected_workflow_id,
        ),
        source=source,
        reason_code=verification.reason_code,
    )


def resolve_workflow(
    classification: WorkflowClassification,
    verification: WorkflowVerification,
) -> WorkflowResolution:
    """분류기·검증기 결과를 결정론적으로 결합해 최종 라우팅을 정한다.

    자연어를 다시 판단하지 않는다. 출력 유효성 검증, 결과 합의, 자동수정 정책,
    사용자 확인 여부, 안전 실패만 담당한다.
    """
    valid = _valid_ids()
    primary = classification.primary_workflow_id
    corrected = verification.corrected_workflow_id

    # (a) primary가 유효하지 않으면(무효 id) 안전 실패.
    if primary is not None and primary not in valid:
        return WorkflowResolution(
            status="failed",
            source="invalid_classifier_output",
            reason_code="INVALID_CLASSIFIER_OUTPUT",
        )
    # 검증기의 무효 수정 id는 이미 verify_workflow가 None으로 낮춘다(방어적 재확인).
    if corrected is not None and corrected not in valid:
        corrected = None

    # (b) 분류기 no_match: 검증기가 수정 후보를 제시하면 사용자 확인, 아니면 no_match.
    if classification.status == "no_match":
        if verification.verdict == "reject" and corrected is not None:
            return WorkflowResolution(
                status="ambiguous",
                candidates=[corrected],
                source="classifier_verifier_conflict",
                reason_code=verification.reason_code,
            )
        return WorkflowResolution(
            status="no_match",
            source="classifier_no_match",
            reason_code="NO_MATCH",
        )

    # (c) 분류기 ambiguous: 검증기가 accept여도 자동 확정하지 않는다.
    if classification.status == "ambiguous":
        return _ambiguous(classification, verification, source="classifier_ambiguous")

    # 여기부터 classification.status == "resolved" 이고 primary 유효.
    # (d) accept → 확정.
    if verification.verdict == "accept":
        return WorkflowResolution(
            status="resolved",
            workflow_id=primary,
            source="classifier_verified",
            reason_code="VALID",
        )

    # (e) 검증기 ambiguous → 사용자 확인.
    if verification.verdict == "ambiguous":
        return _ambiguous(classification, verification, source="classifier_verifier_conflict")

    # (f) 검증기 reject.
    if corrected is None:
        return _ambiguous(classification, verification, source="classifier_verifier_conflict")

    # reject인데 같은 워크플로우를 제시 → 검증기 출력 논리 오류(안전 실패).
    if corrected == primary:
        return WorkflowResolution(
            status="failed",
            source="invalid_verifier_output",
            reason_code="INVALID_VERIFIER_OUTPUT",
        )

    # 조회형→조회형만 자동수정(근거가 충분할 때). 그 외(실행형·설정형·교차)는
    # 결과가 크게 달라지므로 사용자 확인으로 통일한다.
    original_type = _risk_class(primary)
    corrected_type = _risk_class(corrected)
    if (
        query_auto_correction_enabled()
        and original_type == "query"
        and corrected_type == "query"
        and verification.reason_code not in {"INSUFFICIENT_EVIDENCE", "MULTIPLE_ACTIONS"}
    ):
        return WorkflowResolution(
            status="resolved",
            workflow_id=corrected,
            source="verifier_corrected",
            reason_code=verification.reason_code,
        )

    return _ambiguous(classification, verification, source="classifier_verifier_conflict")


# ─────────────────────────────────────────────────────────────────────────────
# 오케스트레이터
# ─────────────────────────────────────────────────────────────────────────────


def route_workflow(user_input: str) -> WorkflowResolution:
    """분류 → 검증 → resolution. LLM 실패 시 안전 실패(failed)."""
    text = user_input or ""

    try:
        classification = classify_workflow(text)
    except Exception:
        resolution = WorkflowResolution(
            status="failed",
            source="classifier_failed",
            reason_code="CLASSIFIER_UNAVAILABLE",
        )
        _log_routing(text, None, None, resolution)
        return resolution

    # 검증기 비활성: 분류기 결과를 (유효성 검증 후) 직접 사용한다.
    if not verifier_enabled():
        verification = WorkflowVerification(verdict="accept", reason_code="VALID")
        resolution = resolve_workflow(classification, verification)
        _log_routing(text, classification, verification, resolution)
        return resolution

    try:
        verification = verify_workflow(text, classification)
    except Exception:
        can_trust_classifier = (
            _verifier_fail_mode() == "fallback"
            and classification.status == "resolved"
            and classification.primary_workflow_id is not None
        )
        if can_trust_classifier:
            resolution = WorkflowResolution(
                status="resolved",
                workflow_id=classification.primary_workflow_id,
                source="classifier_verified",
                reason_code="VERIFIER_UNAVAILABLE",
            )
        else:
            resolution = WorkflowResolution(
                status="failed",
                candidates=([classification.primary_workflow_id] if classification.primary_workflow_id else []),
                source="verifier_failed",
                reason_code="VERIFIER_UNAVAILABLE",
            )
        _log_routing(text, classification, None, resolution)
        return resolution

    resolution = resolve_workflow(classification, verification)
    _log_routing(text, classification, verification, resolution)
    return resolution


def _log_routing(
    text: str,
    classification: WorkflowClassification | None,
    verification: WorkflowVerification | None,
    resolution: WorkflowResolution,
) -> None:
    """관측성: 분류·검증·최종 결정을 구조화 로그로 남긴다(원문은 해시)."""
    logger.info(
        "workflow_resolution",
        extra={
            "routing": {
                "user_input_hash": sha256(text.encode("utf-8")).hexdigest()[:16],
                "classifier": classification.model_dump() if classification else None,
                "verifier": verification.model_dump() if verification else None,
                "resolution": resolution.model_dump(),
            }
        },
    )
