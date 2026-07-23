"""전역 Guardrail 규칙 파일을 읽는 전용 Loader."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_RULES_PATH = Path(__file__).resolve().parents[1] / "config" / "guardrail_rules.yaml"


@lru_cache(maxsize=1)
def get_guardrail_rules() -> dict[str, dict[str, Any]]:
    """현재 Agent 전역 진입점이 사용하는 Guardrail 규칙을 반환한다."""

    loaded = yaml.safe_load(_RULES_PATH.read_text(encoding="utf-8")) or {}
    if not isinstance(loaded, dict):
        raise ValueError("guardrail_rules.yaml 최상위 값은 mapping이어야 합니다.")
    return {str(rule_id): dict(rule) for rule_id, rule in loaded.items() if isinstance(rule, dict)}
