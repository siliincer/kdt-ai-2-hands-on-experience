"""계약 기반 상위 Graph가 공유하는 전역 Guardrail 노드."""

from __future__ import annotations

from agent.policy.context_extractor import build_global_context
from agent.policy.guardrail_engine import GuardrailEngine
from agent.policy.intent_gate import GATE_BLOCK_MESSAGE, GATE_FAILURE_MESSAGE

# 규칙 엔진이 낸 decision 중 요청 전체를 차단하는 액션.
# (require_approval/warn 등은 워크플로우 내부에서 처리하므로 전역 차단이 아니다.)
_BLOCKING_ACTIONS = frozenset({"block"})


def global_guardrail_node(state: dict) -> dict:
    """전역 가드레일로 입력을 검사한다.

    두 경로를 함께 적용한다:
      1. 규칙 기반(guardrail_rules.yaml, scope=global) — DevSecOps 소유
      2. Intent Gate(intent_gate.py) — 복합 공격 의도 분류, fail-closed

    둘 중 하나라도 차단 신호를 내면 요청 전체를 blocked 처리한다.
    """
    context = build_global_context(state)

    # 1) 규칙 기반 검사
    triggered = GuardrailEngine.check_global(context)
    decision = GuardrailEngine.pick_decision(triggered)
    rule_block = bool(decision and decision.get("action") in _BLOCKING_ACTIONS)

    # 2) Intent Gate 판정 (context_extractor가 분류 결과를 context에 넣어 둠)
    #    status: ok(LLM) | degraded(정규식 폴백) | failed(closed 모드) | skipped
    gate_status = context.get("intent_gate_status")
    gate_attack = context.get("intent_attack") is True
    # closed 모드에서 LLM 분류에 실패한 경우에만 status="failed" → fail-closed
    gate_failed = gate_status == "failed"

    intent_record = {
        "status": gate_status,
        "is_attack": gate_attack,
        "category": context.get("intent_category"),
        "reason": context.get("intent_reason"),
    }
    result = {
        "triggered": bool(triggered),
        "scope": "global",
        "rules": triggered,
        "intent_gate": intent_record,
    }

    if rule_block or gate_attack or gate_failed:
        # Security Decision 기록: 어떤 경로가 왜 차단했는지 남긴다.
        if rule_block:
            block_reason = "rule"
            final_response = decision.get("user_message")
        elif gate_attack:
            # LLM 판정(ok)과 정규식 폴백(degraded)을 구분해 기록한다.
            block_reason = "intent_gate_fallback" if gate_status == "degraded" else "intent_gate"
            final_response = GATE_BLOCK_MESSAGE
        else:
            block_reason = "intent_gate_failed"
            final_response = GATE_FAILURE_MESSAGE
        result["block_reason"] = block_reason
        return {
            "status": "blocked",
            "final_response": final_response,
            "guardrail_result": result,
        }

    return {"status": "guardrail_passed", "guardrail_result": result}
