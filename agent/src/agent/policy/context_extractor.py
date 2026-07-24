"""전역 가드레일 컨텍스트 추출.

global scope 규칙의 expression 변수(action_count, target_owner, action_type)를
state에서 만들어 GuardrailEngine에 넘길 context dict를 구성한다.

target_owner / action_type은 키워드 휴리스틱 MVP다. 가드레일 오탐은 정상 요청
차단으로 이어지므로 '3인칭 소유 표현 + 계좌 단어 인접'처럼 보수적인 패턴만
쓴다.

또한 Intent Gate(intent_gate.py) 분류 결과를 context에 함께 노출한다:
  - intent_gate_status: ok | failed | skipped
  - intent_attack: 분류가 공격으로 본 경우 True (실제 차단은 global_guardrail_node)
  - intent_category / requested_action / target: 관측성·DevSecOps 인계용 라벨
분류 라벨을 context에 넣어 두면 DevSecOps가 이후 guardrail_rules.yaml에
`intent_attack == true` 같은 규칙을 추가할 여지가 생긴다.
"""

from __future__ import annotations

import re

from agent.policy.intent_gate import classify_intent

# "남편 계좌", "엄마의 통장", "친구 잔액"처럼 3인칭 소유 표현이 계좌 단어와
# 인접한 경우만 타인 계좌 접근으로 본다 ("친구한테 보내줘"는 매칭되지 않음).
_THIRD_PARTY_ACCOUNT = re.compile(
    r"(남편|아내|엄마|아빠|어머니|아버지|부모님|친구|동생|형|누나|언니|오빠"
    r"|타인|다른\s*사람|남)\s*(?:의)?\s*(계좌|통장|잔액|잔고)"
)

_INQUIRY_WORDS = ["잔액", "잔고", "조회", "얼마", "알려줘", "확인해", "보여줘"]


def build_global_context(state: dict) -> dict:
    """global 규칙 평가용 context를 만든다.

    누락 변수는 규칙 미발동으로 처리되므로(엔진의 보수적 기본값),
    확신할 수 있는 신호만 context에 넣는다.
    """
    user_input = str(state.get("user_input") or "")
    context: dict = {
        "user_input": user_input,
        # 같은 thread에서 누적된 스텝 실행 수 (tool_abuse_block용)
        "action_count": len(state.get("execution_trace") or []),
    }
    if _THIRD_PARTY_ACCOUNT.search(user_input):
        context["target_owner"] = "other"
    if any(word in user_input for word in _INQUIRY_WORDS):
        context["action_type"] = "inquiry"

    # Intent Gate: 공격 의도 분류 결과를 context에 노출한다.
    # status "ok"(LLM) / "degraded"(정규식 폴백) 모두 판정이 확정된 상태다.
    gate = classify_intent(user_input)
    context["intent_gate_status"] = gate.status
    if gate.status in ("ok", "degraded"):
        context["intent_attack"] = gate.is_attack
        context["intent_category"] = gate.category or "none"
        if gate.reason:
            context["intent_reason"] = gate.reason
        # 라벨(requested_action, target 등)을 개별 변수로도 노출
        for label_key, label_value in gate.labels.items():
            context[label_key] = label_value

    return context
