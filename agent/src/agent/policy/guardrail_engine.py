"""Guardrail Engine.

guardrail_rules.yaml의 규칙을 읽어 입력/맥락이 차단 조건에 걸리는지 검사한다.
규칙은 applies_to_scope(global / step / task / tool)로 구분되며, 같은 검사 로직을
scope만 바꿔 재사용할 수 있도록 구조화했다(현재는 global 규칙만 존재).

조건 평가는 _evaluate_condition으로 분리해, 지금은 contains_any만 지원하고
이후 regex/length 등 조건 타입을 확장할 수 있게 했다.
"""

from __future__ import annotations

from agent.workflow_loader import get_guardrail_rules


class GuardrailEngine:
    @staticmethod
    def _evaluate_condition(condition: dict, text: str) -> bool:
        """규칙의 condition이 text에 매칭되는지 검사한다.

        지원 조건:
          - contains_any: 목록 중 하나라도 포함되면 매칭
        (확장 예: contains_all, regex, max_length ...)
        """
        contains_any = condition.get("contains_any")
        if contains_any and any(keyword in text for keyword in contains_any):
            return True
        return False

    @classmethod
    def check(cls, scope: str, text: str) -> dict:
        """주어진 scope의 규칙들을 검사한다.

        매칭되고 action이 block인 규칙이 있으면 차단 결과를,
        없으면 통과 결과를 반환한다.
        """
        rules = get_guardrail_rules()
        for rule_id, rule in rules.items():
            if rule.get("applies_to_scope") != scope:
                continue
            if cls._evaluate_condition(rule.get("condition", {}), text):
                if rule.get("action") == "block":
                    return {
                        "triggered": True,
                        "rule_id": rule_id,
                        "rule_name": rule.get("rule_name"),
                        "action": "block",
                        "risk_level_override": rule.get("risk_level_override"),
                        "user_message": rule.get("user_message"),
                    }
        return {"triggered": False, "scope": scope}

    @classmethod
    def check_global(cls, text: str) -> dict:
        """전역(global) 규칙 검사 편의 메서드."""
        return cls.check("global", text)
