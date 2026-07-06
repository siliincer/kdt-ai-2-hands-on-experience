# 시트 v2 검토 결과와 구조 개편 기록

스프레드시트(config의 source of truth) 개편에 맞춰 agent 구조를 검토·개편한
기록이다. 시트: `18gNcQfyC4EhYZricaSHLXbCmjkT5_VDE1c6jmlgChao`

## 1. 시트에서 바뀐 것

| 항목 | v1 | v2 |
|---|---|---|
| tool 계약 | Tool 탭: `input_params` / `output_schema` / `implementation_status` | **Tool_v2 탭**: `input_state_keys` / `write_state_keys`(네임스페이스 state 키) / `tool_type` |
| state 키 | flat (`account_hint`, `selected_accounts`) | **네임스페이스** (`balance.account_hint`, `transfer.recipient`) |
| Data Schema | 키 나열 | `data_scope`(slot/context) 컬럼 추가 + 네임스페이스 키 |
| 라우팅 탭 이름 | Workflow Router | **Workflow Routing** (+ `route_name`, `condition_description` 컬럼) |
| wf_external_transfer | tool 절반이 미정의 | **전면 재설계** — 22개 tool 전부 스펙화 (수취인 입력/해석/검증, 잔액 확인, 송금 정책 검사, 승인 카드(edit_* 라우트), 본인 인증, 실행 직전 검사) |
| wf_balance_inquiry | 실패 안내 없음 | `show_balance_failed` 스텝 + `generate_balance_response`/`fetch_balance`/`verify_account`의 failed·error 라우트 추가 |

## 2. 시트 내부 모순 (시트 팀 정리 요청)

구현은 아래 모순을 전부 흡수했지만, 시트에서 정리되면 좋은 항목들이다.
sync 스크립트가 매 실행마다 같은 내용을 경고로 출력한다.

| # | 모순 | 현재 코드의 흡수 방식 | 시트 권고 |
|---|---|---|---|
| a | Step 시트는 tool_id `get_balance`, Tool_v2는 `fetch_balance` | 레지스트리에 두 id 모두 같은 함수로 등록 | 한쪽으로 통일 |
| b | Step 시트가 쓰는 `apply_account_selection`이 Tool_v2에 없음 | 레지스트리 등록 유지 | Tool_v2에 행 추가 (또는 ask_account_selection이 선택 적용까지 담당하도록 Step 수정) |
| c | balance Data Schema에 네임스페이스/flat 키 중복 행 (`balance.account_hint`와 `account_hint` 공존) | 네임스페이스 키를 정본으로 채택, flat은 변환 시 매핑 | flat 행 삭제 |
| d | Tool_v2에 `ask_account_selection`/`write_audit_log`가 중복 정의 (송금용/잔액용 변형) | 첫 행 유지 + 경고 | tool_id를 워크플로우별로 분리하거나 한 행으로 병합 |
| e | show_transfer_blocked 등 response 스텝의 tool_id가 `final_response` (실존 tool 아님) | 미등록 tool → error 라우팅으로 무해 | tool_id 비우기 (response 스텝은 step_message로 동작) |
| f | transfer 스텝들의 task_id 다수가 Task 탭에 없음 | 경고만 (task는 메타데이터) | Task 탭 보강 |

## 3. state 구조 개편 (핵심 변경)

### 문제

기존 `AgentState`는 잔액조회 전용 flat 필드(`account_hint`,
`selected_accounts`...)만 선언한 TypedDict였다. 두 가지 이유로 지속 불가능했다:

1. **LangGraph는 스키마에 선언 안 된 top-level 키를 조용히 버린다** (langgraph
   1.2.7에서 직접 검증). 송금 tool이 반환하던 `selected_recipient` 등은 전부
   유실되고 있었다.
2. 시트 v2의 키는 `transfer.recipient` 같은 dotted 문자열이라 TypedDict
   필드명이 될 수 없다.

### 해결: 시스템 필드 + 단일 data 버킷

```python
class AgentState(TypedDict, total=False):
    # 시스템 필드 (엔진 소속, 고정): user_id, user_input, workflow_id,
    # current_step_id, route_key, status, final_response, prompt_for,
    # prompt_message, guardrail_result, log_id, logs, execution_trace
    ...
    data: Annotated[dict, merge_data]   # 모든 업무 데이터
```

- 업무 데이터는 전부 `state["data"]` 안에 **네임스페이스 dotted 키**로 저장:
  `data["balance.account_hint"]`, `data["transfer.recipient"]`
- `merge_data` reducer가 각 노드의 반환 delta를 기존 data와 병합 (얕은 병합,
  새 값 우선, 원본 비변형)
- **새 워크플로우를 추가해도 state.py 수정이 필요 없다**

### 시스템/업무 키 분리는 엔진이 담당

tool은 flat dict를 반환하면 되고, `subgraph_builder._split_updates`가
`SYSTEM_KEYS`(route_key, final_response 등)는 top-level로, 나머지는 data
버킷으로 분리한다. `output_data_key`와 interrupt 답변 저장도 같은 규칙을
따른다 (`_store_output`).

규칙 (tool 작성 시):
- 업무 키는 네임스페이스로 반환: `{"balance.selected_accounts": [...]}`
- 변경분(delta)만 반환, state를 in-place 수정 금지
- `SYSTEM_KEYS`와 `AgentState` 필드가 일치하는지 테스트가 강제한다
  (`test_subgraph_builder.py::test_system_keys_match_agent_state_fields`)

### API 계약 영향

`ChatResponse.prompt_for` 값이 네임스페이스 키가 됐다
(`account_selection_input` → `balance.account_selection_input`).
frontend/backend는 이 값을 opaque 문자열로만 다루므로 코드 변경은 없다.

## 4. sync 스크립트

`agent/scripts/sync_config_from_sheets.py` — 시트에서 config YAML 5개를 생성.

```bash
uv run python agent/scripts/sync_config_from_sheets.py --dry-run   # 경고만 검토
uv run python agent/scripts/sync_config_from_sheets.py             # 재생성
uv run python agent/scripts/sync_config_from_sheets.py --xlsx f.xlsx  # 오프라인
```

fin-ai 원본과의 차이:
- gid 대신 **탭 이름으로 페치** (gviz endpoint) — 탭 추가/재정렬에 안전.
  시트가 비공개면 HTML이 내려오는데, 이를 감지해 명확한 오류를 낸다
- tools는 Tool_v2 탭 사용, `input_state_keys`/`write_state_keys`를 리스트로
  파싱 (콤마/`|`/개행 구분 지원)
- Step의 flat `output_data_key`를 네임스페이스 키로 매핑 (모순 c 흡수).
  매핑 테이블에 없는 flat 키는 워크플로우 네임스페이스를 자동 접두 + 경고
- 라우트 하드닝: 빈 `to_step_id` → `END` 합성, 깨진 step 참조 라우트 → 드롭,
  중복 (from, route_key) → 첫 행 유지 — 전부 경고 출력, 서브그래프 컴파일 보장
- 검증: TOOL_REGISTRY 대조 포함. **경고는 전부 advisory** — 생성은 항상
  성공하고, 경고 목록이 곧 시트 정리 요청 목록이다 (2절)

주의: `workflow_loader._cache`와 matcher의 lru_cache는 프로세스 수명이다.
서버/테스트 실행 중에 config를 재생성했다면 재시작해야 반영된다.

## 5. 현재 동작 범위

- **wf_balance_inquiry**: end-to-end 동작 (신규 show_balance_failed 경로 포함).
  API 키 없이도 키워드/규칙 폴백으로 완주
- **wf_external_transfer**: **end-to-end 동작.** Tool_v2 계약대로 송금 tool
  15개를 구현했고 (레거시 tool은 삭제), 승인·인증·경고는 tool이 직접
  interrupt()를 호출하는 대화형으로 처리한다. 전 과정이 API 키 없이
  결정적으로 완주된다. 시나리오: `agent/notebooks/03_external_transfer.ipynb`,
  자동 테스트: `agent/tests/test_transfer_flow.py`

### 구현 과정에서 흡수한 시트 정합성 이슈 (추가 정리 요청)

- input 스텝 `ask_recipient`에 `output_data_key`가 비어 있어 답변 저장
  위치가 없음 → sync가 Tool_v2 동명 항목의 write_state_keys로 백필
  (시트에 `transfer.recipient` 기입 권고)
- input 스텝들의 route_key가 제각각 (`resolved` vs `submitted`) → 엔진이
  스텝별 route 정의를 따라가도록 일반화 (통일 권고)
- `show_transfer_cancelled`의 step_message가 승인 카드 문구 복사본
  ("송금 내용을 확인해주세요.") → 엔진이 앞 스텝의 final_response를
  우선하도록 처리 (메시지 수정 권고)
