"""LangGraph StateGraph 조립.

흐름:
  global_guardrail
    ├─ blocked       → show_global_blocked       → END
    └─ continue      → workflow_matching
                           ├─ no_match → show_no_matching_workflow → END
                           └─ wf_<id> (서브그래프)
                                   ├─ completed  → return_response      → END
                                   └─ failed     → show_workflow_failed  → END

각 워크플로우(wf_balance_inquiry, wf_external_transfer 등)는
workflows.yaml에서 읽은 steps/routes를 기반으로 LangGraph 서브그래프로
자동 빌드된다. subgraph_builder.py가 이 변환을 담당한다.
"""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from agent.nodes import (
    global_guardrail_node,
    return_response_node,
    show_global_blocked_node,
    show_no_matching_workflow_node,
    show_workflow_failed_node,
    workflow_matching_node,
)
from agent.state import AgentState
from agent.subgraph_builder import build_all_workflow_graphs


def _after_guardrail(state: dict) -> str:
    return "blocked" if state.get("status") == "blocked" else "continue"


# graph.py가 직접 구현하는 진입 로직과 중복되므로 dispatch 대상에서 제외
_ENTRY_ONLY = {"wf_global_agent_entry"}


def build_graph(checkpointer=None):
    """컴파일된 LangGraph 실행 그래프를 반환한다.

    checkpointer: 멀티턴(interrupt/재개)이 필요하면 MemorySaver 등을 전달한다.
                  None이면 단일 턴 전용(input 스텝을 거치지 않는 흐름).
    """
    # workflows.yaml → 워크플로우별 서브그래프 (진입 전용 워크플로우 제외)
    all_graphs = build_all_workflow_graphs()
    workflow_graphs = {k: v for k, v in all_graphs.items() if k not in _ENTRY_ONLY}

    graph = StateGraph(AgentState)
    graph.add_node("global_guardrail", global_guardrail_node)
    graph.add_node("workflow_matching", workflow_matching_node)

    # 사용자 워크플로우 서브그래프만 노드로 추가
    for wf_id, sub_graph in workflow_graphs.items():
        graph.add_node(wf_id, sub_graph)

    graph.add_node("show_global_blocked", show_global_blocked_node)
    graph.add_node("show_no_matching_workflow", show_no_matching_workflow_node)
    graph.add_node("show_workflow_failed", show_workflow_failed_node)
    graph.add_node("return_response", return_response_node)

    graph.set_entry_point("global_guardrail")

    # 가드레일 차단 → show_global_blocked, 통과 → workflow_matching
    graph.add_conditional_edges(
        "global_guardrail",
        _after_guardrail,
        {"blocked": "show_global_blocked", "continue": "workflow_matching"},
    )
    graph.add_edge("show_global_blocked", END)

    # workflow_matching 후 workflow_id에 따라 해당 서브그래프로 디스패치
    def _dispatch(state: dict) -> str:
        wf_id = state.get("workflow_id")
        return wf_id if wf_id in workflow_graphs else "no_match"

    dispatch_map = {wf_id: wf_id for wf_id in workflow_graphs}
    dispatch_map["no_match"] = "show_no_matching_workflow"

    graph.add_conditional_edges("workflow_matching", _dispatch, dispatch_map)
    graph.add_edge("show_no_matching_workflow", END)

    # 서브 워크플로우 완료 후 status에 따라 return_response 또는 show_workflow_failed
    def _after_workflow(state: dict) -> str:
        return "failed" if state.get("status") == "workflow_failed" else "completed"

    for wf_id in workflow_graphs:
        graph.add_conditional_edges(
            wf_id,
            _after_workflow,
            {"completed": "return_response", "failed": "show_workflow_failed"},
        )
    graph.add_edge("show_workflow_failed", END)
    graph.add_edge("return_response", END)

    return graph.compile(checkpointer=checkpointer)
