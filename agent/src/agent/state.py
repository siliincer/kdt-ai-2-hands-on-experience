"""LangGraph Agent State 정의.

구조 (시트 v2 개편):
  - 시스템 필드: 엔진이 소유하는 고정 필드 (route_key, status, final_response 등)
  - data: 모든 업무 데이터가 들어가는 단일 버킷. 키는 워크플로우 네임스페이스가
    붙은 dotted 문자열이다 (예: "balance.account_hint", "transfer.recipient").

왜 이렇게 하나:
  LangGraph는 스키마에 선언되지 않은 top-level 키 업데이트를 조용히 버린다.
  워크플로우마다 필드를 여기에 추가하는 방식은 지속 불가능하고,
  "transfer.recipient" 같은 dotted 키는 TypedDict 필드가 될 수도 없다.
  data 채널 하나에 reducer(merge_data)를 달아 임의의 업무 키를 안전하게
  병합한다. 새 워크플로우를 추가해도 이 파일은 수정할 필요가 없다.

규칙:
  - 노드/tool은 변경분(delta)만 반환한다. state["data"]를 in-place로
    수정하지 않는다 (reducer가 반환된 delta를 기존 data와 병합한다).
  - 시스템 키/업무 키 분리는 엔진(subgraph_builder._split_updates)이 담당한다.
"""

from __future__ import annotations

from typing import Annotated, TypedDict


def merge_data(left: dict | None, right: dict | None) -> dict:
    """data 채널 reducer: 얕은 병합, 오른쪽(새 업데이트) 우선, None 안전.

    입력 dict는 변형하지 않고 항상 새 dict를 반환한다.
    """
    if not left:
        return dict(right or {})
    if not right:
        return dict(left)
    return {**left, **right}


class AgentState(TypedDict, total=False):
    # ── 시스템 필드 (엔진 소속, 고정) ──
    user_id: str
    user_input: str
    workflow_id: str | None
    current_step_id: str | None
    route_key: str | None
    status: str
    final_response: str | None
    prompt_for: str | None
    prompt_message: str | None
    prompt_ui: dict | None
    guardrail_result: dict | None
    log_id: str | None
    logs: list
    execution_trace: list | None
    # ── 업무 데이터 (워크플로우별 네임스페이스 키, 무제한) ──
    data: Annotated[dict, merge_data]
