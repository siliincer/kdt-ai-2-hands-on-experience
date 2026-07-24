"""계약 기반 상위 Graph가 공유하는 전역 Guardrail 노드."""

from __future__ import annotations

from agent.policy.context_extractor import build_global_context
from agent.policy.guardrail_engine import GuardrailEngine


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
