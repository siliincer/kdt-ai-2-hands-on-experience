"""실제 LLM Slot 추출로 그래프를 끝까지 자동으로 돌려 경로를 검증하는 스크립트.

"자연어 메시지 → 실제 LLM이 뽑은 Slot으로 그래프에 진입했을 때, 이후 단계는
시나리오 표에 미리 정해둔 각본대로 자동 응답시키면서 실제로 밟은 step_id
순서가 설계한 경로와 같은가"를 사람 개입 없이 여러 시나리오에 걸쳐 자동으로
검증한다. 팀원이 남긴 "정해둔 워크플로우를 제대로 따라가는지 코드로 확인해야
한다"는 요청에 대한 답.

승인/인증/정정 등 분기 로직 자체는 이미 pytest가 결정적 입력으로 전수
검증한다(AGENTS.md §9) — 이 스크립트가 새로 보는 건 "그 진입점의 Slot이
진짜 LLM에서 나왔을 때도 여전히 설계한 경로로 들어가는가" 하나뿐이다.

실제 흐름 순서대로 두 단계로 나뉜다:
  1단계 — 전역 진입점 라우팅 (`global_entry.py`, 10개 시나리오)
    `wf_global_agent_entry`(가드레일 → LLM 라우터 `match_workflow` → 8개
    워크플로우)를 실행해, 발화가 맞는 워크플로우로 분류되는지·프롬프트
    인젝션이 차단되는지만 본다. 매칭된 뒤에는 완주시키지 않는다 — 그
    이후 내부 분기는 2단계가 이미 본다.
  2단계 — 워크플로우 내부 경로 (8개 파일, 28개 시나리오)
    각 워크플로우 그래프를 직접 실행해 승인/인증/정정 등 내부 분기를 본다.

측정 범위(정직하게 명시):
  - 승인/인증/재시도 자체의 분기 로직은 이미 pytest가 결정적 입력으로 전수
    검증한다(AGENTS.md §9). 이 스크립트가 새로 보는 건 "그 진입점의 Slot이
    진짜 LLM에서 나왔을 때도 여전히 설계한 경로로 들어가는가" 하나뿐이다.
  - 시나리오 표에 없는 조합(예: 인증 실패 재시도 + 정정 요청 동시 발생)은
    다루지 않는다 — 전수 조합 폭발을 피하려고 대표 시나리오만 골랐다.
  - Backend Tool 응답(계좌 조회/Prepare/인증/Execute)은 전부 Mock이 미리
    정해둔 값을 낸다 — Backend 자체의 정확성은 이 스크립트의 범위가 아니다.
  - 실제 FE·BE·Agent를 연결한 통합테스트는 범위 밖이다 — 이 스크립트는
    끝까지 Mock Backend로 Agent 하나만 고립시켜서 본다.

이 파일은 얇은 진입점이다. 실제 시나리오·드라이버는 워크플로우당 파일 하나로
`workflow_path_check/`에 나눠뒀다(agent/src/agent/workflows/의 관례와 동일).
공통 Fixture·범용 드라이버는 `workflow_path_check/_shared.py`에 있다.

사용법:
  LLM_PROVIDER=ollama OLLAMA_MODEL=exaone3.5:7.8b \
    uv run python agent/scripts/auto_workflow_path_check.py
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

from workflow_path_check import (
    account_alias,
    account_list,
    balance_inquiry,
    default_account,
    external_transfer,
    global_entry,
    internal_transfer,
    period_amount_summary,
    transaction_history,
)
from workflow_path_check._shared import Scenario

_MODULES = [
    internal_transfer,
    external_transfer,
    default_account,
    account_alias,
    account_list,
    balance_inquiry,
    transaction_history,
    period_amount_summary,
]

SCENARIOS: list[Scenario] = [s for m in _MODULES for s in m.SCENARIOS]

_RUNNERS = {
    "internal_transfer": internal_transfer.run_scenario,
    "external_transfer": external_transfer.run_scenario,
    "default_account": default_account.run_scenario,
    "account_alias": account_alias.run_scenario,
    "account_list": account_list.run_scenario,
    "balance_inquiry": balance_inquiry.run_scenario,
    "transaction_history": transaction_history.run_scenario,
    "period_amount_summary": period_amount_summary.run_scenario,
}


async def _run_workflow_scenarios() -> tuple[int, list[dict[str, Any]]]:
    print(
        f"\n{'=' * 70}\n2단계 — 워크플로우 내부 경로 ({len(SCENARIOS)}개)\n{'=' * 70}"
    )
    passed = 0
    failed: list[dict[str, Any]] = []

    for scenario in SCENARIOS:
        runner = _RUNNERS[scenario.workflow]
        try:
            outcome = await runner(scenario)
        except Exception as exc:  # noqa: BLE001
            outcome = {"path": [], "final_status": "exception", "error": repr(exc)}

        ok = outcome["error"] is None and outcome["path"] == scenario.expected_path
        status = "PASS" if ok else "FAIL"
        print(f"\n[{status}] {scenario.name} ({scenario.workflow})")
        print(f"    메시지: {scenario.message}")
        if ok:
            passed += 1
            print(f"    경로: {' -> '.join(outcome['path'])}")
        else:
            failed.append({"scenario": scenario.name, **outcome})
            print(f"    기대 경로: {' -> '.join(scenario.expected_path)}")
            print(f"    실제 경로: {' -> '.join(outcome['path']) or '(없음)'}")
            if outcome["error"]:
                print(f"    오류: {outcome['error']}")

    return passed, failed


async def _run_routing_scenarios() -> tuple[int, list[dict[str, Any]]]:
    print(
        f"\n{'=' * 70}\n1단계 — 전역 진입점 라우팅 "
        f"({len(global_entry.SCENARIOS)}개)\n{'=' * 70}"
    )
    passed = 0
    failed: list[dict[str, Any]] = []

    for scenario in global_entry.SCENARIOS:
        try:
            outcome = await global_entry.run_routing_scenario(scenario)
        except Exception as exc:  # noqa: BLE001
            outcome = {
                "workflow_id": None,
                "status": None,
                "ok": False,
                "error": repr(exc),
            }

        ok = outcome.get("ok", False)
        status_label = "PASS" if ok else "FAIL"
        print(f"\n[{status_label}] {scenario.name}")
        print(f"    메시지: {scenario.message}")
        if ok:
            passed += 1
            print(
                f"    workflow_id: {outcome['workflow_id']}, "
                f"status: {outcome['status']}"
            )
        else:
            failed.append({"scenario": scenario.name, **outcome})
            print(
                f"    기대: workflow_id={scenario.expected_workflow_id}, "
                f"status={scenario.expected_status}"
            )
            print(
                f"    실제: workflow_id={outcome.get('workflow_id')}, "
                f"status={outcome.get('status')}"
            )
            if outcome.get("error"):
                print(f"    오류: {outcome['error']}")

    return passed, failed


async def main() -> None:
    provider = os.getenv("LLM_PROVIDER", "openai").strip().lower()
    model = os.getenv("OLLAMA_MODEL") or os.getenv("LLM_MODEL") or "(기본값)"
    print(f"Provider: {provider} / Model: {model}")

    route_passed, route_failed = await _run_routing_scenarios()
    wf_passed, wf_failed = await _run_workflow_scenarios()

    total = len(SCENARIOS) + len(global_entry.SCENARIOS)
    passed = wf_passed + route_passed
    failed = wf_failed + route_failed

    print(f"\n{'#' * 70}\n요약\n{'#' * 70}")
    print(f"1단계(전역 진입점 라우팅): {route_passed}/{len(global_entry.SCENARIOS)}")
    print(f"2단계(워크플로우 내부 경로): {wf_passed}/{len(SCENARIOS)}")
    print(f"전체: {passed}/{total}")
    if failed:
        print("\n실패한 시나리오:")
        for item in failed:
            print(f"  - {item['scenario']}")


if __name__ == "__main__":
    asyncio.run(main())
