"""설정(YAML) 로더.

config/ 폴더의 여러 YAML(워크플로/태스크/툴/위험등급/가드레일)을 읽어 dict로 제공한다.
실행 위치(cwd)와 무관하게 이 파일 기준 상대 경로로 찾고, 파일별로 한 번만 읽어 캐시한다.

설계 원칙: 정책/절차는 모두 YAML(데이터)에 있고, 코드는 그것을 '조회'만 한다.
정책을 바꾸려면 코드가 아니라 YAML을 고친다.
"""

from __future__ import annotations

import yaml

from agent.paths import CONFIG_DIR

# 파일명 -> 파싱된 dict 캐시
_cache: dict[str, dict] = {}


def _load(filename: str) -> dict:
    """config/<filename>을 읽어 dict로 반환한다(캐시)."""
    if filename not in _cache:
        path = CONFIG_DIR / filename
        with open(path, "r", encoding="utf-8") as f:
            _cache[filename] = yaml.safe_load(f) or {}
    return _cache[filename]


# ---- 워크플로 ----------------------------------------------------------------


def load_workflows() -> dict:
    return _load("workflows.yaml")


def get_workflow(workflow_id: str) -> dict:
    workflows = load_workflows()
    if workflow_id not in workflows:
        raise KeyError(f"정의되지 않은 workflow_id: {workflow_id}")
    return workflows[workflow_id]


# ---- 태스크 ------------------------------------------------------------------


def get_task(task_id: str) -> dict:
    tasks = _load("tasks.yaml")
    if task_id not in tasks:
        raise KeyError(f"정의되지 않은 task_id: {task_id}")
    return tasks[task_id]


# ---- 툴 명세 -----------------------------------------------------------------


def get_tool_spec(tool_id: str) -> dict:
    tools = _load("tools.yaml")
    if tool_id not in tools:
        raise KeyError(f"정의되지 않은 tool_id: {tool_id}")
    return tools[tool_id]


# ---- 위험 등급 정책 ----------------------------------------------------------


def get_risk_policy(risk_level: str) -> dict:
    levels = _load("risk_levels.yaml")
    if risk_level not in levels:
        raise KeyError(f"정의되지 않은 risk_level: {risk_level}")
    return levels[risk_level]


# ---- 가드레일 규칙 -----------------------------------------------------------


def get_guardrail_rules() -> dict:
    return _load("guardrail_rules.yaml")
