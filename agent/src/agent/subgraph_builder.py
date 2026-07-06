"""YAML 워크플로우 정의 → LangGraph StateGraph 동적 빌드.

workflows.yaml을 읽어 각 워크플로우를 독립적인 LangGraph 서브그래프로 컴파일한다.

흐름:
  1. steps  → 각 step_id가 LangGraph 노드(node)가 된다
  2. routes → route_key 값에 따라 다음 노드로 이동하는 조건부 엣지(edge)가 된다
  3. 각 노드는 실행 후 state["route_key"]를 설정하고 execution_trace에 자신을 기록한다
"""

from __future__ import annotations

from typing import Callable

import yaml
from langgraph.graph import END, StateGraph
from langgraph.types import interrupt

from agent.paths import WORKFLOWS_PATH
from agent.state import AgentState
from agent.tools.registry import TOOL_REGISTRY


def _load_workflows() -> dict:
    with open(WORKFLOWS_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


# ── 시스템 키 / 업무 데이터 분리 ──────────────────────────────────────────────

# AgentState의 top-level 시스템 필드. tool이 반환한 dict에서 이 키들만
# top-level로 가고, 나머지 업무 키는 전부 data 버킷으로 들어간다.
# (LangGraph는 스키마에 없는 top-level 키를 조용히 버리므로 이 분리가 필수다.)
SYSTEM_KEYS = {
    "user_id",
    "user_input",
    "workflow_id",
    "current_step_id",
    "route_key",
    "status",
    "final_response",
    "prompt_for",
    "prompt_message",
    "guardrail_result",
    "log_id",
    "logs",
    "execution_trace",
}


def _split_updates(result: dict) -> dict:
    """tool 반환 dict를 시스템 키(top-level)와 업무 키(data 버킷)로 분리한다.

    tool이 명시적으로 {"data": {...}}를 반환한 경우도 병합해 지원한다.
    """
    updates: dict = {}
    data: dict = {}
    for key, value in result.items():
        if key in SYSTEM_KEYS:
            updates[key] = value
        elif key == "data" and isinstance(value, dict):
            data.update(value)
        else:
            data[key] = value
    if data:
        updates["data"] = data
    return updates


def _store_output(updates: dict, out_key: str, value) -> None:
    """output_data_key 저장: 시스템 키는 top-level, 그 외는 data 버킷으로."""
    if out_key in SYSTEM_KEYS:
        updates[out_key] = value
    else:
        updates.setdefault("data", {})[out_key] = value


# ── execution_trace 기록 ──────────────────────────────────────────────────────


def _append_trace(state: dict, step_id: str, route_key: str | None) -> dict:
    """execution_trace에 스텝 실행 기록을 추가한 업데이트 dict를 반환한다."""
    trace = list(state.get("execution_trace") or [])
    trace.append({"step": step_id, "route_key": route_key})
    return {"execution_trace": trace}


# ── 노드 팩토리 ───────────────────────────────────────────────────────────────


def _make_tool_node(step: dict) -> Callable:
    """tool_id를 호출하고 결과를 state에 병합하는 노드."""
    step_id = step["step_id"]
    tool_id = step.get("tool_id", "")
    out_key = step.get("output_data_key")

    def node_fn(state: dict) -> dict:
        updates: dict = {"current_step_id": step_id}
        tool_fn = TOOL_REGISTRY.get(tool_id)

        if not tool_fn:
            updates["route_key"] = "error"
        else:
            result = tool_fn(state)
            if isinstance(result, dict):
                updates.update(_split_updates(result))
            elif result is not None:
                if out_key:
                    _store_output(updates, out_key, result)
                updates.setdefault("route_key", "success")
            else:
                updates.setdefault("route_key", "error")

        updates.update(
            _append_trace({**state, **updates}, step_id, updates.get("route_key"))
        )
        return updates

    return node_fn


def _make_response_node(step: dict) -> Callable:
    """tool이 있으면 호출, 없으면 step_message를 final_response로 설정하는 노드."""
    step_id = step["step_id"]
    message = step.get("step_message") or ""
    tool_id = step.get("tool_id", "")
    out_key = step.get("output_data_key")

    def node_fn(state: dict) -> dict:
        updates: dict = {"current_step_id": step_id}

        if tool_id:
            tool_fn = TOOL_REGISTRY.get(tool_id)
            if tool_fn:
                result = tool_fn(state)
                if isinstance(result, dict):
                    updates.update(_split_updates(result))
                elif result is not None:
                    if out_key:
                        _store_output(updates, out_key, result)
                    updates.setdefault("route_key", "success")
                else:
                    updates.setdefault("route_key", "failed")
            else:
                updates["route_key"] = "error"
        else:
            # tool 없음 → step_message를 그대로 사용자에게 노출
            if message:
                updates["final_response"] = message
                if out_key and out_key != "final_response":
                    _store_output(updates, out_key, message)
            updates.setdefault("route_key", "completed")

        updates.update(
            _append_trace({**state, **updates}, step_id, updates.get("route_key"))
        )
        return updates

    return node_fn


def _make_input_node(step: dict) -> Callable:
    """사용자 입력 대기 스텝: interrupt로 그래프를 멈추고 사용자 답을 기다린다.

    처음 실행: interrupt(payload)가 그래프를 정지시킨다(GraphInterrupt).
    재개(Command(resume=답)): interrupt()가 그 답을 반환하며 아래 코드가 이어진다.
    → 사용자 답을 output_data_key에 저장하고 route_key='submitted'로 다음 스텝으로.
    """
    step_id = step["step_id"]
    message = step.get("step_message") or "선택해 주세요."
    out_key = step.get("output_data_key")

    def node_fn(state: dict) -> dict:
        # tool이 준비한 동적 메시지(prompt_message)가 있으면 우선 사용한다.
        # (예: verify_account가 만든 계좌 선택지 목록) 없으면 스텝의 정적 메시지.
        prompt = state.get("prompt_message") or message
        # 여기서 멈춘다. 재개되면 user_reply에 사용자 답이 담긴다.
        user_reply = interrupt({"prompt": prompt, "prompt_for": out_key})

        updates: dict = {"current_step_id": step_id, "route_key": "submitted"}
        if out_key:
            _store_output(updates, out_key, user_reply)
        updates.update(_append_trace({**state, **updates}, step_id, "submitted"))
        return updates

    return node_fn


def _make_log_node(step: dict) -> Callable:
    """감사 로그 스텝: tool을 호출해 로그를 기록한다."""
    step_id = step["step_id"]
    tool_id = step.get("tool_id", "")
    out_key = step.get("output_data_key")

    def node_fn(state: dict) -> dict:
        updates: dict = {"current_step_id": step_id}
        tool_fn = TOOL_REGISTRY.get(tool_id)

        if tool_fn:
            result = tool_fn(state)
            if isinstance(result, dict):
                updates.update(_split_updates(result))
            elif result is not None:
                if out_key:
                    _store_output(updates, out_key, result)
                updates.setdefault("route_key", "logged")
        else:
            updates["route_key"] = "log_failed"

        updates.update(
            _append_trace({**state, **updates}, step_id, updates.get("route_key"))
        )
        return updates

    return node_fn


# ── 엣지 빌더 ─────────────────────────────────────────────────────────────────


def _add_edges(graph: StateGraph, step_id: str, route_map: dict[str, str]) -> None:
    """step_id에서 나가는 엣지를 그래프에 추가한다.

    route_map: {route_key → to_step_id or "END"}
    모든 목적지가 END이면 단순 엣지로 처리한다.
    """
    if not route_map or set(route_map.values()) == {"END"}:
        graph.add_edge(step_id, END)
        return

    # path_map: route_key → 목적지 노드명
    # 라우터는 route_key를 그대로 반환 → LangGraph가 path_map에서 목적지를 찾는다
    mapping = {rkey: (END if to == "END" else to) for rkey, to in route_map.items()}
    # 라우터의 폴백 반환값(END)도 path_map에 있어야 한다.
    # 없으면 미정의 route_key(예: 미구현 tool의 "error")에서 KeyError가 난다.
    mapping.setdefault(END, END)

    def make_router(m: dict) -> Callable:
        def router(state: dict) -> str:
            rkey = state.get("route_key", "")
            return rkey if rkey in m else END

        return router

    graph.add_conditional_edges(step_id, make_router(mapping), mapping)


# ── 서브그래프 빌드 ───────────────────────────────────────────────────────────


def build_workflow_graph(wf_id: str, workflow: dict):
    """단일 워크플로우 YAML → 컴파일된 LangGraph 서브그래프."""
    steps = sorted(workflow.get("steps", []), key=lambda s: s.get("step_order", 0))
    routes = workflow.get("routes", [])

    if not steps:
        raise ValueError(f"워크플로우 '{wf_id}'에 steps가 없습니다.")

    # routes → from_step_id 기준으로 그룹화
    route_map: dict[str, dict[str, str]] = {}
    for r in routes:
        route_map.setdefault(r["from_step_id"], {})[r["route_key"]] = r["to_step_id"]

    graph: StateGraph = StateGraph(AgentState)

    # 노드 추가
    for step in steps:
        step_id = step["step_id"]
        step_type = step.get("step_type", "tool")

        if step_type == "input":
            node_fn = _make_input_node(step)
        elif step_type in ("response", "block"):
            node_fn = _make_response_node(step)
        elif step_type == "log":
            node_fn = _make_log_node(step)
        else:
            node_fn = _make_tool_node(step)

        graph.add_node(step_id, node_fn)

    # 진입점: step_order가 가장 작은 스텝
    graph.set_entry_point(steps[0]["step_id"])

    # 엣지 추가
    for step in steps:
        _add_edges(graph, step["step_id"], route_map.get(step["step_id"], {}))

    return graph.compile()


def build_all_workflow_graphs() -> dict:
    """workflows.yaml의 모든 워크플로우를 서브그래프로 빌드해 반환한다."""
    workflows = _load_workflows()
    graphs = {}
    for wf_id, workflow in workflows.items():
        try:
            graphs[wf_id] = build_workflow_graph(wf_id, workflow)
        except Exception as e:
            print(f"[subgraph_builder] {wf_id}: 빌드 실패 — {e}")
    return graphs
