"""Workflow Matching.

사용자 입력을 분석해 실행할 workflow_id를 결정한다.
LLM 의도 분류를 사용하고, 후보 워크플로우 목록은 workflows.yaml에서 동적으로 읽는다.
LLM 호출 실패 시 키워드 규칙으로 폴백한다.
"""

from __future__ import annotations

from functools import lru_cache

import yaml
from pydantic import BaseModel, Field

from agent.llm import get_llm
from agent.paths import WORKFLOWS_PATH

# 폴백용 키워드 규칙(LLM 실패 시에만 사용)
_KEYWORD_RULES = [
    (("보내", "송금", "이체", "에게", "한테"), "wf_external_transfer"),
    (("잔액", "통장", "얼마 있어", "얼마야"), "wf_balance_inquiry"),
]


@lru_cache(maxsize=1)
def _load_workflow_choices() -> tuple[tuple[str, str, str], ...]:
    """(workflow_id, workflow_name, description) 목록. global 타입은 제외."""
    with open(WORKFLOWS_PATH, encoding="utf-8") as f:
        wfs = yaml.safe_load(f) or {}
    choices = []
    for wid, wf in wfs.items():
        if wf.get("workflow_type") == "global":
            continue
        choices.append((wid, wf.get("workflow_name", ""), wf.get("description", "")))
    return tuple(choices)


class _IntentResult(BaseModel):
    """의도 분류 결과."""

    workflow_id: str | None = Field(
        None,
        description="발화에 가장 알맞은 워크플로우 id. 해당하는 것이 없으면 null.",
    )


def _match_by_keyword(text: str) -> str | None:
    """규칙 기반 폴백."""
    for keywords, workflow_id in _KEYWORD_RULES:
        if any(keyword in text for keyword in keywords):
            return workflow_id
    return None


def match_workflow(user_input: str) -> str | None:
    """입력에 매칭되는 workflow_id를 반환한다. 없으면 None.

    LLM으로 후보 워크플로우 중 하나로 분류하고, 실패 시 키워드 규칙으로 폴백한다.
    """
    text = user_input or ""
    choices = _load_workflow_choices()
    valid_ids = {c[0] for c in choices}

    try:
        catalog = "\n".join(f"- {wid}: {name} — {desc}" for wid, name, desc in choices)
        llm = get_llm().with_structured_output(_IntentResult)
        result = llm.invoke(
            "너는 은행 상담 라우터다. 사용자 발화를 아래 워크플로우 중 "
            "하나로 분류해라. 해당하는 것이 없으면 workflow_id를 null로 둬라.\n\n"
            f"[워크플로우 목록]\n{catalog}\n\n"
            f"[발화]\n{text}"
        )
        workflow_id = result.workflow_id
        return workflow_id if workflow_id in valid_ids else None
    except Exception:
        return _match_by_keyword(text)
