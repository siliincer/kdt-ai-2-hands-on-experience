"""Guardrail Engine.

guardrail_rules.yaml의 규칙을 읽어 입력/맥락이 정책 조건에 걸리는지 검사한다.
규칙은 applies_to_scope(global / workflow / tool)와 applies_to_ids로 구분되며,
호출자가 scope + context(+ target_id)만 넘기면 같은 검사 로직을 재사용한다.

조건 타입:
  - contains_any: context["user_input"]에 키워드 중 하나라도 포함되면 매칭
  - expression: 안전한 미니 평가기로 context 변수를 대조 (eval 미사용)
      문법: `피연산자 연산자 피연산자`를 AND/OR로 연결 (AND가 OR보다 우선)
      연산자: ==, !=, >=, <=, >, <
      피연산자: 정수/실수, '문자열', true/false, 점 표기 식별자(tool_result.status)
      누락 변수 안전 규칙: context에 없는 식별자를 참조하는 절은 False
      (가드레일 오발동으로 정상 요청을 차단하지 않기 위한 보수적 기본값)

check()는 발동한 규칙 전부를 반환하고, 단일 라우트 결정이 필요한 호출자는
pick_decision()으로 가장 심각한 액션의 규칙을 고른다.
"""

from __future__ import annotations

import re

from agent.workflow_loader import get_guardrail_rules

# 절: `피연산자 연산자 피연산자` (피연산자는 공백 없는 토큰 또는 따옴표 문자열)
_CLAUSE = re.compile(r"^\s*(\S+)\s*(==|!=|>=|<=|>|<)\s*(.+?)\s*$")
# AND/OR 구분 (절 내부 문자열에 공백+AND가 들어가는 경우는 시트 문법상 없음)
_CONNECTOR = re.compile(r"\s+(AND|OR)\s+")

# context에 없는 식별자 표시용 센티널
_MISSING = object()

# 액션 심각도 (앞일수록 우선)
_ACTION_PRIORITY = [
    "block",
    "require_additional_auth",
    "require_approval",
    "warn",
    "ask_clarification",
]


class GuardrailEngine:
    # ── expression 평가 ──────────────────────────────────────────────────────

    @staticmethod
    def _resolve_operand(token: str, context: dict):
        """토큰을 리터럴 또는 context 식별자 값으로 해석한다."""
        token = token.strip()
        if len(token) >= 2 and token[0] == token[-1] and token[0] in ("'", '"'):
            return token[1:-1]
        lowered = token.lower()
        if lowered == "true":
            return True
        if lowered == "false":
            return False
        try:
            return int(token)
        except ValueError:
            pass
        try:
            return float(token)
        except ValueError:
            pass
        value = context
        for part in token.split("."):
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                return _MISSING
        return value

    @classmethod
    def _evaluate_clause(cls, clause: str, context: dict) -> bool:
        """단일 절(`a == b` 등)을 평가한다. 파싱 실패/변수 누락은 False."""
        match = _CLAUSE.match(clause)
        if not match:
            return False
        left = cls._resolve_operand(match.group(1), context)
        right = cls._resolve_operand(match.group(3), context)
        if left is _MISSING or right is _MISSING:
            return False
        op = match.group(2)
        try:
            if op == "==":
                return left == right
            if op == "!=":
                return left != right
            if op == ">=":
                return left >= right
            if op == "<=":
                return left <= right
            if op == ">":
                return left > right
            if op == "<":
                return left < right
        except TypeError:
            return False
        return False

    @classmethod
    def _evaluate_expression(cls, expression: str, context: dict) -> bool:
        """AND/OR로 연결된 절들을 평가한다 (AND가 OR보다 우선)."""
        expression = (expression or "").strip()
        if not expression:
            return False
        parts = _CONNECTOR.split(expression)
        # parts = [절, 연산자, 절, 연산자, ...] — OR 그룹(각각 AND 절 묶음)으로 재구성
        or_groups: list[list[bool]] = []
        current = [cls._evaluate_clause(parts[0], context)]
        for i in range(1, len(parts) - 1, 2):
            value = cls._evaluate_clause(parts[i + 1], context)
            if parts[i] == "AND":
                current.append(value)
            else:
                or_groups.append(current)
                current = [value]
        or_groups.append(current)
        return any(all(group) for group in or_groups)

    # ── 조건/규칙 평가 ───────────────────────────────────────────────────────

    @classmethod
    def _evaluate_condition(cls, condition: dict, context: dict) -> bool:
        """규칙의 condition이 context에 매칭되는지 검사한다."""
        contains_any = condition.get("contains_any")
        if contains_any:
            text = str(context.get("user_input") or "")
            return any(keyword in text for keyword in contains_any)
        expression = condition.get("expression")
        if expression:
            return cls._evaluate_expression(expression, context)
        return False

    @staticmethod
    def _applies(rule: dict, target_id: str | None) -> bool:
        ids = rule.get("applies_to_ids") or []
        if "*" in ids:
            return True
        return target_id is not None and target_id in ids

    @classmethod
    def check(cls, scope: str, context: dict, target_id: str | None = None) -> list:
        """주어진 scope/target의 활성 규칙을 모두 검사해 발동 목록을 반환한다."""
        rules = get_guardrail_rules()
        triggered = []
        for rule_id, rule in rules.items():
            if rule.get("applies_to_scope") != scope:
                continue
            if not rule.get("enabled"):
                continue
            if not cls._applies(rule, target_id):
                continue
            if cls._evaluate_condition(rule.get("condition") or {}, context):
                triggered.append(
                    {
                        "rule_id": rule_id,
                        "rule_name": rule.get("rule_name"),
                        "action": rule.get("action"),
                        "risk_level_override": rule.get("risk_level_override"),
                        "user_message": rule.get("user_message"),
                    }
                )
        return triggered

    @classmethod
    def check_global(cls, context: dict) -> list:
        """전역(global) 규칙 검사 편의 메서드."""
        return cls.check("global", context)

    @staticmethod
    def pick_decision(triggered: list) -> dict | None:
        """발동 규칙 중 가장 심각한 액션의 규칙을 고른다. 없으면 None."""
        for action in _ACTION_PRIORITY:
            for rule in triggered:
                if rule.get("action") == action:
                    return rule
        return triggered[0] if triggered else None
