"""subgraph_builder의 시스템 키 / data 버킷 분리 검증.

미니 워크플로우 정의를 인라인으로 만들어 컴파일하고,
tool이 반환한 혼합 키(시스템 + 업무)가 올바른 위치에 저장되는지 확인한다.
"""

from __future__ import annotations

import pytest

from agent.subgraph_builder import (
    SYSTEM_KEYS,
    _split_updates,
    build_workflow_graph,
)
from agent.tools.registry import TOOL_REGISTRY


def test_split_updates_routes_keys_correctly():
    result = {
        "route_key": "success",
        "final_response": "안내문",
        "balance.x": 1,
        "data": {"transfer.y": 2},
    }
    updates = _split_updates(result)
    assert updates["route_key"] == "success"
    assert updates["final_response"] == "안내문"
    assert updates["data"] == {"balance.x": 1, "transfer.y": 2}
    assert "balance.x" not in updates  # top-level 유출 금지


def test_system_keys_match_agent_state_fields():
    """SYSTEM_KEYS는 AgentState의 top-level 필드(data 제외)와 일치해야 한다."""
    from agent.state import AgentState

    state_fields = set(AgentState.__annotations__.keys()) - {"data"}
    assert SYSTEM_KEYS == state_fields


@pytest.fixture()
def mini_workflow():
    """tool 1개 → response 1개짜리 최소 워크플로우 정의."""
    return {
        "steps": [
            {
                "step_order": 1,
                "step_id": "do_work",
                "step_type": "tool",
                "tool_id": "mixed_tool",
            },
            {
                "step_order": 2,
                "step_id": "scalar_step",
                "step_type": "tool",
                "tool_id": "scalar_tool",
                "output_data_key": "balance.scalar_out",
            },
        ],
        "routes": [
            {
                "from_step_id": "do_work",
                "route_key": "success",
                "to_step_id": "scalar_step",
            },
            {
                "from_step_id": "scalar_step",
                "route_key": "success",
                "to_step_id": "END",
            },
        ],
    }


def test_tool_returns_go_to_data_bucket(mini_workflow, monkeypatch):
    monkeypatch.setitem(
        TOOL_REGISTRY,
        "mixed_tool",
        lambda state: {
            "balance.x": 1,
            "route_key": "success",
            "final_response": "혼합 반환",
        },
    )
    monkeypatch.setitem(TOOL_REGISTRY, "scalar_tool", lambda state: "스칼라값")

    graph = build_workflow_graph("wf_test", mini_workflow)
    result = graph.invoke({"data": {}})

    # 업무 키는 data 버킷으로
    assert result["data"]["balance.x"] == 1
    # 스칼라 반환은 output_data_key로 data 버킷에
    assert result["data"]["balance.scalar_out"] == "스칼라값"
    # 시스템 키는 top-level로
    assert result["final_response"] == "혼합 반환"
    assert "balance.x" not in result  # 미선언 top-level 키로 새지 않음


def test_tool_dict_without_route_key_becomes_error(mini_workflow, monkeypatch):
    """route_key 없는 dict 반환은 이전 route 재사용 대신 error로 실패한다."""
    monkeypatch.setitem(TOOL_REGISTRY, "mixed_tool", lambda state: {"balance.x": 1})
    monkeypatch.setitem(TOOL_REGISTRY, "scalar_tool", lambda state: "값")

    graph = build_workflow_graph("wf_test", mini_workflow)
    result = graph.invoke({"data": {}})

    # error는 route 맵에 없으므로 첫 스텝에서 END로 조기 종료된다
    assert result["execution_trace"][0]["route_key"] == "error"
    assert len(result["execution_trace"]) == 1


def test_response_node_unregistered_tool_falls_back_to_message():
    """response 스텝의 tool_id가 미등록이면 step_message로 폴백한다.

    (시트가 'final_response' 같은 실존하지 않는 tool_id를 적는 경우 흡수)
    """
    from agent.subgraph_builder import _make_response_node

    node = _make_response_node(
        {
            "step_id": "show_blocked",
            "step_type": "response",
            "tool_id": "final_response",  # 미등록
            "step_message": "정책상 진행할 수 없습니다.",
        }
    )
    result = node({"data": {}})
    assert result["route_key"] == "completed"
    assert result["final_response"] == "정책상 진행할 수 없습니다."

    # 앞 스텝이 만든 구체 사유가 있으면 그것을 우선한다
    result = node({"data": {}, "final_response": "한도 초과로 차단되었습니다."})
    assert result["final_response"] == "한도 초과로 차단되었습니다."


def test_is_cancel_reply_keywords():
    from agent.subgraph_builder import _is_cancel_reply

    assert _is_cancel_reply("취소")
    assert _is_cancel_reply("송금 취소할래")
    assert _is_cancel_reply("그만")
    # "아니"로 시작하는 정정 답변은 취소가 아니다
    assert not _is_cancel_reply("아니 3만원으로 해줘")
    assert not _is_cancel_reply("1번")


def test_existing_data_preserved_across_steps(mini_workflow, monkeypatch):
    """reducer 병합: 이전 스텝의 data가 다음 스텝 업데이트에 지워지지 않는다."""
    monkeypatch.setitem(
        TOOL_REGISTRY,
        "mixed_tool",
        lambda state: {"balance.first": "a", "route_key": "success"},
    )
    monkeypatch.setitem(
        TOOL_REGISTRY,
        "scalar_tool",
        lambda state: {"balance.second": "b", "route_key": "success"},
    )

    graph = build_workflow_graph("wf_test", mini_workflow)
    result = graph.invoke({"data": {"balance.seed": "s"}})

    assert result["data"]["balance.seed"] == "s"
    assert result["data"]["balance.first"] == "a"
    assert result["data"]["balance.second"] == "b"
