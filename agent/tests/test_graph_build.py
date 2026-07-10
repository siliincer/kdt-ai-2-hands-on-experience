"""그래프 빌드 검증.

config YAML이 깨지면 앱 import 자체가 실패하므로, 이 테스트가
service.py의 import 시점 그래프 빌드에 대한 가드 역할을 한다.
"""

from __future__ import annotations

from agent.graph import build_graph


def test_build_graph_compiles():
    graph = build_graph()
    nodes = set(graph.get_graph().nodes.keys())

    # 최상위 공통 노드
    assert "global_guardrail" in nodes
    assert "workflow_matching" in nodes
    assert "return_response" in nodes

    # workflows.yaml 기반 서브그래프 노드
    assert "wf_balance_inquiry" in nodes
    assert "wf_external_transfer" in nodes

    # 진입 전용 메타 워크플로우는 디스패치 대상에서 제외된다
    assert "wf_global_agent_entry" not in nodes
