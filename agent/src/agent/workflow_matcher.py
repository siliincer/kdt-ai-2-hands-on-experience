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
# LLM 미사용(키 없음) 시 폴백. 위에서부터 먼저 매칭되는 규칙이 이긴다.
# LLM 경로는 시트 example_utterance로 분류하므로, 이 키워드는 그 보조판이다.
_KEYWORD_RULES = [
    (("보내", "송금", "이체", "에게", "한테"), "wf_external_transfer"),
    (("잔액", "통장", "얼마 있어", "얼마야"), "wf_balance_inquiry"),
    (("옮겨", "본인 계좌", "내 계좌로"), "wf_internal_transfer"),
    (("기본 계좌", "기본 출금", "나가게 해", "출금 계좌로"), "wf_set_default_account"),
    (
        ("별칭", "이라고 해", "이라 해", "이라 불러", "라고 불러", "이름 붙"),
        "wf_set_account_alias",
    ),
    (
        ("계좌 목록", "계좌 뭐", "무슨 계좌", "어떤 계좌", "계좌 다 보"),
        "wf_account_list",
    ),
    (
        ("거래내역", "거래 내역", "결제 내역", "이용 내역", "사용 내역", "입출금 내역"),
        "wf_transaction_history",
    ),
    (("얼마 썼", "얼마 쓴", "지출", "소비"), "wf_period_amount_summary"),
]


@lru_cache(maxsize=1)
def _load_workflow_choices() -> tuple[tuple[str, str, str, str], ...]:
    """(workflow_id, name, description, example_utterance) 목록.

    global 타입은 제외. 매칭 프롬프트에는 이 요약 정보만 들어간다 —
    steps/routes 등 YAML 본문은 LLM에 전달되지 않는다 (토큰 비용 없음).
    """
    with open(WORKFLOWS_PATH, encoding="utf-8") as f:
        wfs = yaml.safe_load(f) or {}
    choices = []
    for wid, wf in wfs.items():
        if wf.get("workflow_type") == "global":
            continue
        choices.append(
            (
                wid,
                wf.get("workflow_name", ""),
                wf.get("description", ""),
                wf.get("example_utterance", ""),
            )
        )
    return tuple(choices)


def _build_catalog(choices: tuple[tuple[str, str, str, str], ...]) -> str:
    """매칭 프롬프트용 워크플로우 카탈로그 (한 줄씩).

    시트의 example_utterance를 few-shot 예시로 함께 넣어 분류 정확도를
    높인다. 예시가 없으면 괄호를 생략한다.
    """
    lines = []
    for wid, name, desc, example in choices:
        line = f"- {wid}: {name} — {desc}"
        if example:
            line += f' (예: "{example}")'
        lines.append(line)
    return "\n".join(lines)


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
        catalog = _build_catalog(choices)
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
