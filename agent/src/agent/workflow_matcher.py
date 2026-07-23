"""Workflow Matching.

사용자 입력을 분석해 실행할 workflow_id를 결정한다.
LLM 의도 분류를 사용하고, 후보 목록은 관리시트 V3 계약 Manifest에서 읽는다.
LLM 호출 실패 시 키워드 규칙으로 폴백한다.
"""

from __future__ import annotations

from functools import lru_cache
from typing import cast

from pydantic import BaseModel, Field

from agent.llm import get_llm
from agent.workflow_contracts import WorkflowContractStore

# 폴백용 키워드 규칙(LLM 실패 시에만 사용)
# LLM 미사용(키 없음) 시 폴백. 위에서부터 먼저 매칭되는 규칙이 이긴다.
# LLM 경로는 계약 Manifest의 example_utterances로 분류하므로, 이 키워드는 그 보조판이다.
#
# 순서 규칙: 구체적인(다른 워크플로우와 안 겹치는) 키워드를 위에,
# "통장"/"잔액"처럼 범용적인 키워드는 맨 아래에 둔다. "통장"은 거의 모든
# 계좌 관련 발화에 등장하므로 balance_inquiry를 맨 뒤(다른 게 하나도
# 안 걸렸을 때만 잡히는 catch-all)로 둬야 한다.
_KEYWORD_RULES = [
    (("에게", "한테", "송금", "보내"), "wf_external_transfer"),
    (
        ("옮겨", "본인 계좌", "내 계좌로", "통장으로", "계좌 간", "이체"),
        "wf_internal_transfer",
    ),
    (
        ("기본", "출금 계좌로", "나가게 해"),
        "wf_set_default_account",
    ),
    (
        ("별칭", "라고 해", "라 해", "라고 불러", "라 불러", "이름 붙"),
        "wf_set_account_alias",
    ),
    (
        (
            "계좌 목록",
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
    (
        ("거래내역", "거래 내역", "결제 내역", "이용 내역", "사용 내역", "입출금 내역"),
        "wf_transaction_history",
    ),
    (
        (
            "얼마 썼",
            "얼마 쓴",
            "지출",
            "소비",
            "얼마 들어",
            "얼마 받",
            "수입",
            "입금 얼마",
        ),
        "wf_period_amount_summary",
    ),
    # 가장 범용적인 규칙 — 위 어느 것도 안 걸렸을 때만 잔액조회로 (catch-all)
    (("잔액", "통장", "얼마 있어", "얼마야"), "wf_balance_inquiry"),
]


@lru_cache(maxsize=1)
def _load_workflow_choices() -> tuple[tuple[str, str, str, str], ...]:
    """(workflow_id, name, description, example_utterance) 목록.

    global 타입은 제외한다. 실행 Workflow와 같은 V3 Manifest의 catalog만 사용하며
    Steps와 Routes는 LLM에 전달하지 않는다.
    """
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


def _build_catalog(choices: tuple[tuple[str, str, str, str], ...]) -> str:
    """매칭 프롬프트용 워크플로우 카탈로그 (한 줄씩).

    계약의 example_utterances를 few-shot 예시로 함께 넣어 분류 정확도를
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
        result = cast(
            _IntentResult,
            llm.invoke(
                "너는 은행 상담 라우터다. 사용자 발화를 아래 워크플로우 중 "
                "하나로 분류해라. 해당하는 것이 없으면 workflow_id를 null로 둬라.\n\n"
                f"[워크플로우 목록]\n{catalog}\n\n"
                f"[발화]\n{text}"
            ),
        )
        workflow_id = result.workflow_id
        return workflow_id if workflow_id in valid_ids else None
    except Exception:
        return _match_by_keyword(text)
