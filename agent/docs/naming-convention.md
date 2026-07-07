# step_id / tool_id 명명규칙과 전체 재작성안

시트(Workflow Step / Tool_v2)의 id 작명이 규칙 없이 자라면서 생긴 혼동
(`show_transfer_warning` step ↔ `transfer_warning` tool, `show_transfer_review`
step ↔ `create_approval` tool, 가짜 tool_id `final_response` 등)을 없애기 위한
**명명규칙 + 현재 id 전량 재작성안 + 시트 수정 지시서**다.

> **상태: 반영 완료 (2026-07-07)** — 아래 재작성안은 시트·sync·코드에 모두
> 적용되었다. 3절 지시서와 4절 후속 작업 표는 변경 이력으로 남긴다.
> 반영 중 확정된 결정 2건이 본문과 다르니 주의:
> ① 인증 tool_id는 `request_user_authentication`이 아니라 **step과 동일한
> `authenticate_user`로 확정** (auth는 1:1 전용이라 동일화 — 규칙 5의 예외).
> ② Tool_v2의 계좌 선택 UI는 공용 1행이 아니라 **두 행으로 분리**
> (`ask_from_account` 송금용 / `ask_account_selection` 잔액용 — 이름 충돌이
> 사라져 병합 근거가 없어짐. input 행은 항상 step_id와 1:1).

- 대상 시트: `18gNcQfyC4EhYZricaSHLXbCmjkT5_VDE1c6jmlgChao`
- 행 번호 기준일: **2026-07-07** (헤더 = 1행). 행이 밀렸으면 함께 적어둔
  id로 재확인한다.
- 과거 `sheet-cleanup-guide.md`(시트 정리 지시서 — 반영 완료 후 삭제됨)의
  A-1 / A-4 / A-6을 이 문서가 대체·확장했다.

---

## 1. 명명규칙

### 공통

1. snake_case 영어 소문자, `동사_목적어[_수식어]` — **반드시 동사로 시작**한다.
2. state 필드명(`final_response`, `amount` 등)을 id로 쓰지 않는다.
   (tool_id 자리에 `final_response`를 적는 것은 "tool 없음"의 잘못된 표기)
3. step_id는 워크플로우 안에서 유일하다. 두 워크플로우가 **완전히 같은
   동작**을 하는 스텝만 같은 step_id를 재사용한다 (`write_audit_log`).
   tool_id는 전역에서 유일하다.

### step_id — 흐름 관점, step_type이 동사를 결정한다

| step_type | 동사 | 형태 | 예 |
|---|---|---|---|
| tool | 기능 동사 | `extract/check/verify/resolve/apply/fetch/execute_*` | `verify_amount` |
| input | ask | `ask_<슬롯명>` — **output_data_key 마지막 세그먼트와 일치** | `ask_recipient` (transfer.recipient) |
| response (안내/실패) | show | `show_<상황>` | `show_transfer_blocked` |
| response (성공 결과) | show | `show_<대상>_result` | `show_transfer_result` |
| guardrail | run | `run_<범위>_guardrail` | `run_transfer_guardrail` |
| approval | review | `review_<대상>` | `review_transfer` |
| auth | authenticate | `authenticate_<대상>` | `authenticate_user` |
| log | write | `write_<로그>` | `write_audit_log` |

### tool_id — 구현 관점, 기능 동사

4. **판단/조회/변환 tool은 step_id와 동일하게** 쓴다. 1:1 전용 + 같은 동사면
   같은 이름이 정상이다 (`verify_amount` step = `verify_amount` tool).
5. **대화형(interrupt) tool은 다른 동사**를 쓴다 — 스텝은 화면(흐름) 관점,
   tool은 상호작용(기능) 관점이므로 이름이 갈리는 것이 신호다:
   - `request_*`: 사용자에게 결정/인증을 **요청**하고 답을 받는다
   - `confirm_*`: 사용자에게 **확인**을 받는다
6. 응답 문장을 만드는 tool은 `generate_*`.
7. **순수 안내 response 스텝은 tool이 없다** — tool_id를 비우고
   step_message가 담당한다.
8. 읽는 법: **step_id와 tool_id가 같으면 1:1 전용 기능**, 다르면
   대화형(`request_/confirm_`)이거나 공용 tool이다.

### 예외 (개명하지 않음)

- `wf_global_agent_entry`의 스텝(`return_response` 등)은 그래프 엔진 내장
  노드와 1:1이므로 코드 노드명을 따른다. Step 탭 notes에 "엔진 내장" 표기.
- input 스텝의 완료 route_key는 `submitted`로 통일한다.

---

## 2. 전체 인벤토리 — 판정과 재작성안

### wf_global_agent_entry (전부 유지 — 엔진 내장 예외)

| step_id | step_type | 판정 |
|---|---|---|
| run_global_guardrail | guardrail | 유지 (`run_*_guardrail` 부합) |
| match_workflow | routing | 유지 (엔진 내장) |
| execute_matched_workflow | subworkflow | 유지 (엔진 내장) |
| return_response | response | 유지 (엔진 내장 예외 — notes 표기) |
| show_global_blocked / show_no_matching_workflow / show_workflow_failed | response | 유지 (`show_*` 부합, tool 없음 ✓) |

### wf_external_transfer

| step_order | 현재 step_id | 판정 → 제안 step_id | 현재 tool_id → 제안 |
|---|---|---|---|
| 1 | extract_transfer_slots | 유지 | extract_transfer_slots 유지 (규칙 4) |
| 2 | check_recipient_input | 유지 | check_recipient_input 유지 |
| 3 | ask_recipient | 유지 (슬롯 transfer.recipient ✓) | (input — tool 없음) |
| 4 | resolve_recipient_input | 유지 | resolve_recipient_input 유지 |
| 5 | verify_recipient_account | 유지 | verify_recipient_account 유지 |
| 6 | show_invalid_recipient_account | 유지 | (tool 없음 ✓) |
| 8 | check_amount_input | 유지 | check_amount_input 유지 |
| 9 | ask_amount_input | **변경 → `ask_amount`** (슬롯 transfer.amount) | (input — tool 없음) |
| 10 | verify_amount | 유지 | verify_amount 유지 |
| 12 | verify_from_account | 유지 | verify_from_account 유지 |
| 13 | ask_account_selection | **변경 → `ask_from_account`** (슬롯 transfer.from_account) | (input — tool 없음, 공용 UI는 Tool_v2 12행) |
| 14 | check_balance | 유지 | check_balance 유지 |
| 15 | show_insufficient_balance | 유지 | (tool 없음 ✓) |
| 16 | run_transfer_guardrail | 유지 | run_transfer_guardrail 유지 |
| 17 | show_transfer_warning | 유지 (화면 관점) | transfer_warning → **`confirm_transfer_warning`** (규칙 5) |
| 18 | show_transfer_blocked | 유지 | final_response → **비움** (규칙 2·7) |
| 19 | show_transfer_review | **변경 → `review_transfer`** (approval 동사) | create_approval → **`request_transfer_approval`** (규칙 5) |
| 21 | show_transfer_cancelled | 유지 | final_response → **비움** |
| 22 | request_user_authentication | **변경 → `authenticate_user`** (auth 동사) | **`authenticate_user`** (step과 동일 — 반영 시 확정된 auth 예외) |
| 24 | show_authentication_failed | 유지 | final_response → **비움** |
| 25 | run_pre_execution_guardrail | 유지 | run_pre_execution_guardrail 유지 |
| 26 | execute_transfer | 유지 | transfer_money → **`execute_transfer`** (1:1 전용인데 이름이 달랐음 — 규칙 4·8) |
| 27 | show_transfer_failed | 유지 | final_response → **비움** |
| 28 | generate_transfer_response | **변경 → `show_transfer_result`** (response 스텝은 show_) | generate_transfer_response 유지 (규칙 6) |
| 30 | write_audit_log | 유지 | write_audit_log 유지 (공용) |

### wf_balance_inquiry

| step_order | 현재 step_id | 판정 → 제안 step_id | 현재 tool_id → 제안 |
|---|---|---|---|
| 1 | extract_balance_slots | 유지 | extract_balance_slots 유지 |
| 2 | verify_account | 유지 | verify_account 유지 |
| 3 | ask_account_selection | 유지 (슬롯 balance.account_selection_input ✓) | (input — tool 없음) |
| 4 | apply_account_selection | 유지 | apply_account_selection 유지 |
| 5 | fetch_balance | 유지 | get_balance → **`fetch_balance`** (A-1과 동일 — Tool_v2 정본에 맞춤) |
| 6 | generate_balance_response | **변경 → `show_balance_result`** | generate_balance_response 유지 |
| 7 | show_balance_failed | 유지 | (tool 없음 ✓) |
| 8 | write_audit_log | 유지 | write_audit_log 유지 |

**요약: step_id 변경 6건, tool_id 변경 5건 (비우기 4건 포함 시 9건).**

---

## 3. 시트 수정 지시서

### 3-1. Workflow Step 탭

step_id 컬럼 (6건):

| 행 | 현재 step_id | 변경값 |
|---|---|---|
| 16 | ask_amount_input | `ask_amount` |
| 19 | ask_account_selection | `ask_from_account` |
| 25 | show_transfer_review | `review_transfer` |
| 27 | request_user_authentication | `authenticate_user` |
| 32 | generate_transfer_response | `show_transfer_result` |
| 39 | generate_balance_response | `show_balance_result` |

tool_id 컬럼 (7건):

| 행 | step_id (확인용) | 현재 tool_id | 변경값 |
|---|---|---|---|
| 23 | show_transfer_warning | transfer_warning | `confirm_transfer_warning` |
| 24 | show_transfer_blocked | final_response | (비움) |
| 25 | show_transfer_review → review_transfer | create_approval | `request_transfer_approval` |
| 26 | show_transfer_cancelled | final_response | (비움) |
| 28 | show_authentication_failed | final_response | (비움) |
| 30 | execute_transfer | transfer_money | `execute_transfer` |
| 31 | show_transfer_failed | final_response | (비움) |
| 38 | fetch_balance | get_balance | `fetch_balance` |

### 3-2. Workflow Routing 탭 — 개명된 step_id가 등장하는 모든 행

`ask_amount_input` → `ask_amount`:

| 행 | 컬럼 |
|---|---|
| 23 | to_step_id (check_amount_input missing) |
| 24, 25 | from_step_id |
| 27 | to_step_id (verify_amount invalid) |
| 48 | to_step_id (review_transfer edit_amount) |

`ask_account_selection` → `ask_from_account` (**wf_external_transfer 행만** — 잔액 쪽 67·71·72·74행은 유지):

| 행 | 컬럼 |
|---|---|
| 30 | to_step_id (verify_from_account needs_selection) |
| 32, 33 | from_step_id |
| 37 | to_step_id (show_insufficient_balance completed) |
| 49 | to_step_id (review_transfer edit_from_account) |

`show_transfer_review` → `review_transfer`:

| 행 | 컬럼 |
|---|---|
| 38 | to_step_id (run_transfer_guardrail allowed) |
| 42 | to_step_id (show_transfer_warning confirmed) |
| 45~50 | from_step_id (6행) |

`request_user_authentication` → `authenticate_user`:

| 행 | 컬럼 |
|---|---|
| 45 | to_step_id (review_transfer approved) |
| 52, 53 | from_step_id |

`generate_transfer_response` → `show_transfer_result`:

| 행 | 컬럼 |
|---|---|
| 59 | to_step_id (execute_transfer success) |
| 62, 63 | from_step_id |

`generate_balance_response` → `show_balance_result`:

| 행 | 컬럼 |
|---|---|
| 68 | to_step_id (fetch_balance success) |
| 76, 77 | from_step_id |

추가 (B-7 동일): 15행 ask_recipient의 route_key `resolved` → `submitted`.

### 3-3. Tool_v2 탭

| 행 | 현재 tool_id | 변경값 | 비고 |
|---|---|---|---|
| 9 | ask_amount_input | `ask_amount` | input UI 스펙 행 — 스텝명과 일치 유지 |
| 16 | show_transfer_warning | `confirm_transfer_warning` | A-4 대체 |
| 18 | show_transfer_review | `request_transfer_approval` | A-4 대체 |
| 23 | transfer_money | `execute_transfer` | |
| 12 | ask_account_selection | 유지 | 공용 select UI — description에 "송금 ask_from_account / 잔액 ask_account_selection 두 스텝이 사용" 표기 (A-2 병합과 함께) |

### 3-4. Guardrail Rule 탭 — applies_to_ids의 `transfer_money` → `execute_transfer`

| 행 | guardrail_rule_id |
|---|---|
| 5 | insufficient_balance |
| 6 | high_amount_transfer |
| 7 | new_recipient_warning |
| 8 | approval_required_for_execution |
| 9 | post_result_validation |

신규 추가 예정 행 `high_amount_transfer_block`(1,000만 원 차단 — 현재
`config/guardrail_rules.yaml`에만 있음)도 applies_to_ids를 `execute_transfer`로
기입한다.

### 3-5. Workflow Data Schema 탭 — source_step_id 갱신 (행 번호 대신 data_key로 확인)

| data_key | source_step_id 현재 → 변경 |
|---|---|
| final_response (잔액) | generate_balance_response → `show_balance_result` |
| transfer.approval (B-1 추가분) | show_transfer_review → `review_transfer` |
| transfer.transfer_result (B-1 추가분) | execute_transfer 유지 |

---

## 4. 반영 절차와 코드 후속 작업

시트가 source of truth이므로 **반드시 시트 → sync → 코드 순서**로 진행한다.
(코드를 먼저 바꾸면 다음 sync에서 어긋난다.)

```bash
# 1. 시트 반영 후 경고 확인
uv run python agent/scripts/sync_config_from_sheets.py --dry-run
# 2. config 재생성 (백업은 config/backup/)
uv run python agent/scripts/sync_config_from_sheets.py
# 3. 코드 리네임 (아래 목록) 후 회귀 확인
uv run pytest agent
```

sync 후 필요한 코드 리네임 (agent 파트):

| 대상 | 변경 |
|---|---|
| `tools/registry.py` | 키 `transfer_warning`→`confirm_transfer_warning`, `create_approval`→`request_transfer_approval`, `transfer_money`→`execute_transfer`. `get_balance`/`fetch_balance` alias는 한 줄로 정리 |
| `tools/bank_tools.py` | 함수명 동조 리네임 (`transfer_warning`→`confirm_transfer_warning`, `create_approval`→`request_transfer_approval`, `transfer_money`→`execute_transfer`, `get_balance`→`fetch_balance`) + `run_transfer_guardrail`/`run_pre_execution_guardrail`의 `target_id="transfer_money"` → `"execute_transfer"` |
| `config/guardrail_rules.yaml` | sync가 재생성 (수동 수정 불필요 — 단 high_amount_transfer_block이 시트에 없으면 유실되니 시트 추가 선행) |
| `tests/` | step trace/함수 import 참조 갱신 (`test_transfer_flow.py`, `test_transfer_tools.py`, `test_guardrail_engine.py`의 transfer_money 참조 등) |
| `notebooks/01~03` | 재실행해 baked 출력 갱신 (execution_trace의 step_id가 바뀜) |
| `docs/` | `api-contract.md`(create_approval 언급 없음 — 확인만), `agent-integration.md`의 `create_approval`, `transfer_money` 예시 갱신 |

주의: `ask_from_account`로 개명해도 Step 탭 19행의 output_data_key
(`from_account`)가 채워져 있어 sync의 Tool_v2 백필에 의존하지 않는다
(ask_recipient는 A-5대로 output_data_key 직접 기입 필요).
