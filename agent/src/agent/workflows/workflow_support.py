"""계약 기반 Workflow가 공유하는 State와 실행 Context 보조 함수."""

from __future__ import annotations

from typing import Any, Literal

from langchain_core.runnables import RunnableConfig

from agent.state import AgentState


def state_data(state: AgentState) -> dict[str, Any]:
    """누적 State의 data를 Node에서 안전하게 수정할 수 있는 복사본으로 반환한다."""

    return dict(state.get("data") or {})


def route_key(state: AgentState) -> str:
    """Route가 없으면 각 Workflow의 오류 경로로 보낼 기본값을 반환한다."""

    return str(state.get("route_key") or "error")


def config_context(config: RunnableConfig, key: str) -> str:
    """LangGraph configurable에서 비어 있지 않은 필수 문자열 Context를 읽는다."""

    configurable = config.get("configurable") or {}
    value = configurable.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"LangGraph 실행 Context가 없습니다: {key}")
    return value


def terminal_update(
    step_id: str,
    *,
    status: Literal["completed", "workflow_failed"] = "completed",
) -> dict[str, Any]:
    """종료 Node가 공통으로 반환하는 State 변경값을 만든다."""

    return {
        "current_step_id": step_id,
        "route_key": "completed",
        "status": status,
    }
