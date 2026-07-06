# 스프레드시트 정리 지시서

이 문서만 보고 시트를 수정할 수 있도록 **탭 / 행 / 컬럼 / 현재값 / 변경값**
단위로 작성했습니다.

- 대상 시트: `18gNcQfyC4EhYZricaSHLXbCmjkT5_VDE1c6jmlgChao`
- 행 번호 기준일: **2026-07-06** (헤더 = 1행). 이후 행이 추가/삭제됐다면
  행 번호 대신 함께 적어둔 **tool_id / step_id로 위치를 재확인**하세요.
- 우선순위: **A 필수** (동작 정확성 — 지금은 코드가 임시 흡수 중) /
  **B 권고** (일관성·중복 정리) / **C 참고**
- 수정 후 반영 절차는 맨 아래 참조.

현재 sync 스크립트 실행 시 **경고 41건**이 나옵니다. A+B를 반영하면
대부분 사라집니다.

---

## A. 필수 수정 (동작 정확성)

### A-1. tool 이름 통일: `get_balance` → `fetch_balance`

같은 기능의 tool이 두 이름으로 존재합니다. Tool_v2의 `fetch_balance`가
정본이므로 Workflow Step 쪽을 맞춥니다.

| 위치 | 컬럼 | 현재값 | 변경값 |
|---|---|---|---|
| Workflow Step **38행** (step_id `fetch_balance`) | tool_id | `get_balance` | `fetch_balance` |

- 이유: Tool_v2 30행은 `fetch_balance`로 정의. 현재 코드는 두 id를 같은
  함수에 alias로 등록해 흡수 중 — 시트 수정 후 alias를 제거할 수 있습니다
  (`agent/src/agent/tools/registry.py`의 `fetch_balance` 항목 주석 참조).

### A-2. Tool_v2 중복 tool_id 병합 (2쌍)

tool_id는 고유해야 합니다. sync는 현재 "첫 행 유지"로 처리해 뒤 행이
조용히 버려집니다.

**① `ask_account_selection` (12행 송금용 / 29행 잔액용)**

| 위치 | 처리 |
|---|---|
| Tool_v2 **12행** | 유지. description을 "출금(송금)/조회(잔액) 계좌 선택 UI — 두 워크플로우가 공용"으로 갱신. write_state_keys는 **비움** (실제 저장 위치는 Workflow Step의 output_data_key가 정본: 송금 `transfer.from_account`, 잔액 `balance.account_selection_input`) |
| Tool_v2 **29행** | **행 삭제** |

**② `write_audit_log` (26행 송금용 / 32행 잔액용)**

| 위치 | 처리 |
|---|---|
| Tool_v2 **26행** | 유지. description을 "모든 워크플로우 공통 감사 로그 기록"으로 갱신, input_state_keys 비움 |
| Tool_v2 **32행** | **행 삭제** |

### A-3. Tool_v2에 `apply_account_selection` 행 추가

Workflow Step 37행(잔액조회 4스텝)이 쓰는 tool인데 Tool_v2에 없습니다.
아래 값으로 행을 추가하세요:

| 컬럼 | 값 |
|---|---|
| tool_id | `apply_account_selection` |
| tool_name | 선택 계좌 적용 |
| tool_type | verification |
| input_state_keys | `balance.account_selection_input, balance.account_candidates` |
| write_state_keys | `balance.selected_accounts` |
| risk_level 등급 | R1 |
| description | 계좌 선택 답변을 해석해 조회 대상 계좌를 확정한다. 유효한 선택이 없으면 invalid로 재질문한다. |

### A-4. Tool_v2 대화형 tool의 tool_id를 Step 탭과 일치시키기

승인/경고 tool의 id가 Tool_v2와 Step 탭에서 서로 다릅니다. 코드는 Step 탭
기준(`transfer_warning`, `create_approval`)으로 구현되어 있습니다.

| 위치 | 컬럼 | 현재값 | 변경값 |
|---|---|---|---|
| Tool_v2 **16행** | tool_id | `show_transfer_warning` | `transfer_warning` |
| Tool_v2 **18행** | tool_id | `show_transfer_review` | `create_approval` |

- 참고: 16·18행의 현재 tool_id는 **step_id**와 같은 이름입니다. Step 탭의
  tool_id 컬럼(23행 `transfer_warning`, 25행 `create_approval`)이 정본입니다.

### A-5. `ask_recipient`의 답변 저장 위치 지정

| 위치 | 컬럼 | 현재값 | 변경값 |
|---|---|---|---|
| Workflow Step **11행** (step_id `ask_recipient`) | output_data_key | (빈 값) | `transfer.recipient` |

- 이유: input 스텝은 사용자 답변을 output_data_key에 저장합니다. 비어 있으면
  답변이 유실됩니다. 현재는 sync가 Tool_v2 4행의 write_state_keys에서
  백필해 흡수 중 — 시트에 직접 기입되면 백필 경고가 사라집니다.
- 같은 행의 step_message `(계좌번호 선택화면 ex. 토스에서 송금시)`는 메모
  성격이므로 실제 사용자 문구(예: "누구에게 보낼까요? 이름 또는 계좌번호를
  입력해주세요.")로 교체 권고.

### A-6. response 스텝의 가짜 tool_id `final_response` 비우기

`final_response`는 tool이 아니라 state 필드명입니다. response 스텝은
tool 없이 step_message로 동작합니다.

| 위치 (Workflow Step) | step_id | 컬럼 | 현재값 | 변경값 |
|---|---|---|---|---|
| **24행** | show_transfer_blocked | tool_id | `final_response` | (비움) |
| **26행** | show_transfer_cancelled | tool_id | `final_response` | (비움) |
| **28행** | show_authentication_failed | tool_id | `final_response` | (비움) |
| **31행** | show_transfer_failed | tool_id | `final_response` | (비움) |

- 현재는 엔진의 response 노드 폴백이 흡수 중입니다 (미등록 tool → step_message).

### A-7. `show_transfer_cancelled` 문구 수정

| 위치 | 컬럼 | 현재값 | 변경값 |
|---|---|---|---|
| Workflow Step **26행** | step_message | `송금 내용을 확인해주세요.` | `송금을 취소했습니다.` |

- 이유: 승인 카드(25행) 문구가 복사된 것으로 보입니다. 현재는 엔진이 앞
  스텝의 final_response를 우선하도록 처리해 흡수 중입니다.

---

## B. 정리 권고 (일관성·중복)

### B-1. Workflow Data Schema의 flat/네임스페이스 중복 정리

잔액조회 키가 두 표기로 중복 등재되어 있습니다. 네임스페이스가 정본입니다.

| 위치 (Data Schema) | data_key | 처리 |
|---|---|---|
| **10행** | `account_hint` | 삭제 (8행 `balance.account_hint`가 정본) |
| **11행** | `account_candidates` | `balance.account_candidates`로 키 변경 (data_scope: context 유지) |
| **12행** | `account_selection_input` | `balance.account_selection_input`으로 키 변경 (slot 유지) |
| **13행** | `selected_accounts` | 삭제 (9행 `balance.selected_accounts`가 정본) |
| **14행** | `balance_results` | `balance.balance_results`로 키 변경 |
| **15행** | `final_response` | 유지 (시스템 필드 — data_scope에 "system" 표기 권고) |
| **16행** | `log_id` | 유지 (시스템 필드 — 동일) |

그리고 **구현이 실제로 사용하는 송금 키 3개를 추가**하세요
(wf_external_transfer):

| data_key | data_scope | source_step_id | data_type | 설명 |
|---|---|---|---|---|
| `transfer.risk` | context | run_transfer_guardrail | object | 정책 검사 결과 (risk_level/decision/reason) |
| `transfer.approval` | context | show_transfer_review | object | 승인 요약 — 실행 직전 검사가 실행 내용과 대조 |
| `transfer.transfer_result` | context | execute_transfer | object | 송금 실행 결과 (transaction_id, amount 등) |

### B-2. Task 탭 보강 (누락 21건)

wf_external_transfer 스텝들이 참조하는 task_id가 Task 탭에 없습니다.
아래 목록을 Task 탭에 추가하거나, 안 쓸 거면 Step 탭의 task_id를 비우세요
(둘 중 하나로 통일 — 추가를 권고):

```
transfer_slot_extraction, recipient_input_check, recipient_input,
recipient_input_classification, recipient_account_verification,
invalid_recipient_account_response, amount_input_check, amount_input,
amount_verification, from_account_verification, from_account_selection,
balance_check, transfer_guardrail_check, transfer_warning_response,
transfer_blocked_response, transfer_cancelled_response,
user_authentication, authentication_failed_response,
pre_execution_guardrail_check, transfer_failed_response,
transfer_response_generation
```

- 참고: `user_approval`, `external_transfer`, `audit_log_recording`은 이미
  있습니다. task는 현재 런타임에서 메타데이터로만 쓰이므로 급하지 않지만,
  sync 경고의 절반이 이것입니다.

### B-3. 구버전 `Tool` 탭 정리

`Tool` 탭(구계약: input_params/output_schema)과 `Tool_v2`가 공존합니다.
sync는 Tool_v2만 읽으므로 구버전 탭은 **삭제하거나 탭 이름을
`Tool_deprecated`로 바꿔** 혼동을 방지하세요.

### B-4. Code Book의 step_type 코드 정비

| 항목 | 처리 |
|---|---|
| `auth` 코드 **누락** | 추가 (Workflow Step 27행 request_user_authentication이 사용 중) — 설명: "본인 인증을 요청하고 결과에 따라 분기하는 Step" |
| `risk` 코드 | 어떤 스텝도 사용하지 않음 — 삭제 또는 active=FALSE |
| `block` 코드 | 어떤 스텝도 사용하지 않음 (차단 안내는 response로 통일됨) — 삭제 또는 active=FALSE |

### B-5. Workflow Step의 구버전 라우팅 컬럼 삭제

`on_fail_condition` / `on_success_next_step_id` / `on_fail_next_step_id`
컬럼은 라우팅이 Workflow Routing 탭으로 분리되기 전의 잔재입니다.
두 곳에 라우팅이 적혀 있으면 어긋나기 쉬우므로 **Routing 탭만 정본으로
남기고 이 3개 컬럼은 삭제**를 권고합니다 (엔진은 Routing 탭만 읽습니다).

### B-6. 잡동사니 컬럼 삭제

여러 탭에 이름 없는 열이 남아 있습니다 (sync가 자동 제외 중):

- Workflow Step: `notes 2`, `1열`
- Workflow Routing: `1열`, `2열`

### B-7. input 스텝 route_key 통일 (`resolved` vs `submitted`)

입력 완료 route_key가 스텝마다 다릅니다:

| 스텝 | 현재 route_key |
|---|---|
| ask_recipient | `resolved` |
| ask_amount_input | `submitted` |
| ask_account_selection (송금/잔액) | `submitted` |

엔진이 스텝별 정의를 따라가도록 일반화되어 있어 **동작에는 문제가
없지만**, 규칙이 하나면 시트 작성이 쉬워집니다. `submitted`로 통일 권고
(Workflow Routing 14행의 `resolved` → `submitted`, 대응 to_step_id 유지).
변경해도 코드 수정은 필요 없습니다.

---

## C. 참고 (선택)

- **step_order 결번**: wf_external_transfer에 7, 11, 20, 23, 29번이
  비어 있습니다. 정렬만 쓰므로 동작 무관 — 의도(추후 스텝 예약)라면 유지.
- **엔진 내장 tool 표기**: wf_global_agent_entry의 `run_guardrail_check`
  (2행), `match_workflow`(3행)는 Tool 함수가 아니라 그래프 엔진이 직접
  구현합니다. Tool_v2에 없는 것이 정상이므로 Step 탭 notes에 "엔진 내장"
  이라고 적어두면 경고를 무시하기 쉽습니다.
- **미사용 task**: Task 탭의 `no_match_handling`, `transaction_history_inquiry`,
  `spending_analysis`, `budget_check`, `deposit_cash`, `withdraw_cash`,
  `internal_transfer`, `auto_savings_setup`, `recipient_verification`,
  `transfer_risk_assessment`는 현재 어떤 스텝도 참조하지 않습니다.
  미래 워크플로우용이면 그대로 두세요.
- **response 안내 스텝들의 Tool_v2 등재**: `show_invalid_recipient_account`
  (7행), `show_insufficient_balance`(14행), `show_transfer_blocked`(17행),
  `show_transfer_cancelled`(19행), `show_authentication_failed`(21행),
  `show_transfer_failed`(24행)는 실제 tool 구현이 없는 안내 화면입니다
  (step_message가 담당). UI 명세로 유지하려면 그대로 두되, tool 목록의
  정확성을 원하면 삭제해도 됩니다 (Step 탭 tool_id가 비어 있으면 무관).

---

## 수정 후 반영 절차

```bash
# 1. 경고가 줄었는지 확인 (A+B 반영 시 41건 -> 한 자릿수 기대)
uv run python agent/scripts/sync_config_from_sheets.py --dry-run

# 2. config 재생성 (기존 파일은 config/backup/에 백업됨)
uv run python agent/scripts/sync_config_from_sheets.py

# 3. 회귀 확인
uv run pytest agent
```

A-1(fetch_balance 통일)을 반영했다면 코드에서도 alias를 제거할 수 있습니다:
`agent/src/agent/tools/registry.py`에서 `"get_balance": get_balance` 또는
`"fetch_balance": get_balance` 중 시트가 안 쓰는 쪽 한 줄 삭제 + 함수명
`get_balance` → `fetch_balance` 리네임(선택).
