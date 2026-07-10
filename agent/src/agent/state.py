"""LangGraph Agent State 정의.

구조 (시트 v2 개편):
  - 시스템 필드: 엔진이 소유하는 고정 필드 (route_key, status, final_response 등)
  - data: 모든 업무 데이터가 들어가는 단일 버킷. 키는 워크플로우 네임스페이스가
    붙은 dotted 문자열이다 (예: "balance.account_hint", "transfer.recipient").

왜 이렇게 하나:
  LangGraph는 스키마에 선언되지 않은 top-level 키 업데이트를 조용히 버린다.
  워크플로우마다 필드를 여기에 추가하는 방식은 지속 불가능하고,
  "transfer.recipient" 같은 dotted 키는 TypedDict 필드가 될 수도 없다.
  data 채널 하나에 reducer(merge_data)를 달아 임의의 업무 키를 안전하게
  병합한다. 새 워크플로우를 추가해도 이 파일은 수정할 필요가 없다.

규칙:
  - 노드/tool은 변경분(delta)만 반환한다. state["data"]를 in-place로
    수정하지 않는다 (reducer가 반환된 delta를 기존 data와 병합한다).
  - 시스템 키/업무 키 분리는 엔진(subgraph_builder._split_updates)이 담당한다.
"""

from __future__ import annotations

from typing import Annotated, TypedDict


def merge_data(left: dict | None, right: dict | None) -> dict:
    """data 채널 reducer: 얕은 병합, 오른쪽(새 업데이트) 우선, None 안전.

    입력 dict는 변형하지 않고 항상 새 dict를 반환한다.
    """
    if not left:
        return dict(right or {})
    if not right:
        return dict(left)
    return {**left, **right}


class AgentState(TypedDict, total=False):
    # ══ 시스템 필드 (엔진 소속, 고정) ══════════════════════════════════════
    # 여기 있는 키들은 subgraph_builder.SYSTEM_KEYS와 1:1로 동기화된다
    # (test_system_keys_match_agent_state_fields가 강제). 필드를 추가하면
    # SYSTEM_KEYS에도 함께 추가할 것.

    # ── 대화 식별 / 입력 ──
    # 요청 사용자 id. mock 원장(MOCK_ACCOUNTS 등)의 조회 키로 쓰인다.
    # service._new_state가 턴 시작 시 채운다.
    user_id: str
    # 이번 턴의 사용자 발화 원문. 슬롯 추출/가드레일/업무 분류의 입력.
    user_input: str

    # ── 라우팅 (엔진이 다음 갈 곳을 정하는 데 쓰는 필드) ──
    # 매칭된 업무 워크플로우 id (예: "wf_balance_inquiry").
    # workflow_matching_node가 채우고, 최상위 그래프가 서브그래프 디스패치에 쓴다.
    workflow_id: str | None
    # 방금 실행된 스텝 id. 라우팅에는 안 쓰이고 디버깅/trace 판독용.
    current_step_id: str | None
    # 직전 스텝이 남긴 "다음 갈림길 열쇠" — 라우팅의 핵심.
    # 각 tool이 반환하고(예: "confirmed", "insufficient"), 엔진 라우터가
    # workflows.yaml의 routes에서 이 값으로 다음 스텝을 찾는다.
    route_key: str | None
    # 턴의 종료 상태. graph.py의 출구 노드들이 설정하고
    # (completed/blocked/no_match/workflow_failed), service가 API status로 매핑.
    status: str

    # ── 사용자에게 노출되는 값 ──
    # 사용자에게 보여줄 최종 응답 문장. response 스텝/가드레일/실패 안내가
    # 설정하며, service가 ChatResponse.reply로 내보낸다.
    final_response: str | None
    # interrupt(멈춤) 상태에서 기다리는 입력의 data 키
    # (예: "balance.account_selection_input"). 클라이언트에는 opaque 문자열.
    prompt_for: str | None
    # 다음 input 스텝(interrupt)에서 보여줄 동적 질문 텍스트.
    # tool이 만들어 두면(예: 계좌 선택지 목록) input 노드가 정적 step_message
    # 대신 사용하고, 소비 후 None으로 비운다 (다음 질문 오염 방지).
    prompt_message: str | None
    # 질문에 곁들일 구조화 UI 힌트 (frontend 렌더링용 — account_card_list,
    # confirm_modal 등). prompt_message와 같은 수명 규칙: 소비 후 클리어.
    prompt_ui: dict | None

    # ── 기록 (검사 결과 / 감사 로그 / 실행 이력) ──
    # 전역 가드레일 검사 결과 ({"triggered": bool, "rule_id": ...}).
    # global_guardrail_node가 채운다.
    guardrail_result: dict | None
    # 이번 턴 감사 로그 항목의 id (write_audit_log가 발급, 예: "log_0001").
    log_id: str | None
    # 감사 로그 항목 누적 리스트. 각 항목에 최종 응답과 실행 경로 텍스트 포함.
    logs: list
    # 지나온 스텝의 [{"step": id, "route_key": key}, ...] 목록.
    # 모든 노드가 실행 후 append — 노트북/디버깅에서 실행 경로를 보는 용도.
    execution_trace: list | None

    # ══ 업무 데이터 버킷 (워크플로우별, 무제한) ═══════════════════════════
    # 모든 업무 값이 여기에 네임스페이스 dotted 키로 들어간다:
    #   data["balance.selected_accounts"]  — 잔액조회가 확정한 계좌 목록
    #   data["transfer.recipient"]         — 송금이 확정한 수취인 dict
    # 키 계약은 시트 Tool_v2 탭(input/write_state_keys)이 정본이다.
    # merge_data reducer가 각 노드의 반환 delta를 기존 값과 병합한다.
    data: Annotated[dict, merge_data]
