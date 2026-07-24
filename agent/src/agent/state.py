"""계약 기반 LangGraph Runtime의 공통 State 정의.

업무별 State 이름과 Step 입출력은 관리시트 V3 Manifest를 따르고, ``data``
reducer는 중첩 Graph가 반환한 변경분을 기존 값과 안전하게 병합한다.
"""

from __future__ import annotations

from typing import Annotated, TypedDict


def merge_data(left: dict | None, right: dict | None) -> dict:
    """data 채널을 얕게 병합하고 새로운 변경분을 우선한다."""

    if not left:
        return dict(right or {})
    if not right:
        return dict(left)
    return {**left, **right}


class AgentState(TypedDict, total=False):
    """상위 Graph와 업무별 하위 Graph가 공유하는 State."""

    # 사용자 입력과 라우팅
    user_input: str
    workflow_id: str | None
    current_step_id: str | None
    route_key: str | None
    status: str

    # 전역 Guardrail 결과
    final_response: str | None
    guardrail_result: dict | None
    execution_trace: list | None

    # V3 계약 업무 State
    data: Annotated[dict, merge_data]
