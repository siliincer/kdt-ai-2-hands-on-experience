"""LangGraph 노드 함수.

최상위 그래프가 사용하는 공통 노드 모음:
  global_guardrail_node → workflow_matching_node → (워크플로우 서브그래프)

각 노드는 state를 받아 '갱신할 필드만' dict로 반환한다(LangGraph가 병합).

참고: fin-ai 원본의 workflow_execution_node(순차 실행기 경로)는 서브그래프
기반 실행으로 대체되어 포팅에서 제외했다. 자세한 배경은
agent/docs/README.md 참조.
"""

from __future__ import annotations

from agent.policy.context_extractor import build_global_context
from agent.policy.guardrail_engine import GuardrailEngine
from agent.workflow_matcher import match_workflow


def global_guardrail_node(state: dict) -> dict:
    """전역 가드레일 규칙(guardrail_rules.yaml, scope=global)으로 입력을 검사한다."""
    context = build_global_context(state)
    triggered = GuardrailEngine.check_global(context)
    decision = GuardrailEngine.pick_decision(triggered)
    result = {"triggered": bool(triggered), "scope": "global", "rules": triggered}
    if decision and decision.get("action") == "block":
        return {
            "status": "blocked",
            "final_response": decision.get("user_message"),
            "guardrail_result": result,
        }
    return {"status": "guardrail_passed", "guardrail_result": result}


def workflow_matching_node(state: dict) -> dict:
    """입력에 맞는 Workflow를 매칭한다."""
    workflow_id = match_workflow(state.get("user_input", ""))
    if workflow_id is None:
        return {
            "status": "no_match",
            "final_response": (
                "요청을 이해하지 못했어요. 잔액 조회처럼 다시 말씀해 주세요."
            ),
        }
    return {"workflow_id": workflow_id, "status": "matched"}


def show_global_blocked_node(state: dict) -> dict:
    """전역 가드레일 차단 시 안내 응답을 설정한다."""
    return {
        "status": "blocked",
        "final_response": state.get("final_response")
        or "이 요청은 안전 정책상 실행할 수 없습니다.",
    }


def show_no_matching_workflow_node(__state: dict) -> dict:
    """매칭되는 워크플로우가 없을 때 안내 응답을 설정한다."""
    return {
        "status": "no_match",
        "final_response": "요청을 이해하지 못했어요. 잔액 조회처럼 다시 말씀해 주세요.",
    }


def show_workflow_failed_node(__state: dict) -> dict:
    """워크플로우 실행 실패 시 안내 응답을 설정한다."""
    return {
        "status": "workflow_failed",
        "final_response": (
            "요청 처리 중 문제가 발생했습니다. 잠시 후 다시 시도해 주세요."
        ),
    }


def return_response_node(__state: dict) -> dict:
    """서브 워크플로우 완료 후 최종 응답을 반환하는 글로벌 출구 노드.

    sub-graph가 이미 final_response를 설정해두므로 이 노드는 통과 역할만 한다.
    향후 채널별 포맷 변환, 공통 후처리가 필요하면 여기에 추가한다.
    """
    return {"status": "completed"}
