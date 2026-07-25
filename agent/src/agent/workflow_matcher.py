"""Workflow Matching (하위호환 얇은 래퍼).

실제 라우팅 로직은 workflow_routing.route_workflow로 이동했다(분류기·검증기
분리 파이프라인). 이 모듈은 기존 호출부·테스트 호환을 위해 workflow_id만
반환하는 match_workflow를 유지한다. 신규 코드는 route_workflow를 직접 사용해
resolution(ambiguous/candidates/source)까지 소비하라.
"""

from __future__ import annotations

from agent.workflow_routing import route_workflow


def match_workflow(user_input: str) -> str | None:
    """입력에 매칭되는 workflow_id를 반환한다. 확정 못 하면 None.

    ambiguous·no_match·failed는 전부 None으로 낮춘다(하위호환). 라우팅의
    세부 상태가 필요하면 workflow_routing.route_workflow를 사용하라.
    """
    resolution = route_workflow(user_input)
    if resolution.status == "resolved":
        return resolution.workflow_id
    return None
