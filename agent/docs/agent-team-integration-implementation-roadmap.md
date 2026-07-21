# Agent 팀 Backend 연동 전환 실행 로드맵

> 대상: Agent 담당자, Backend 담당자, Frontend 담당자
>
> 상태: 초안
>
> 작성일: 2026-07-14
>
> 목적: Agent가 원장과 Frontend를 직접 호출하던 기존 Workflow를 Backend 중계 구조로 전환하기 위해 필요한 결정, 문서, 관리시트, 구현, 검증 작업을 순서대로 정의한다.

---

## 1. 문서 목적

이 문서는 Agent 팀이 앞으로 수행해야 할 작업을 실행 순서에 맞게 정리한 작업 기준서다.

현재 필요한 작업은 단순히 기존 Tool의 호출 주소를 바꾸는 것이 아니다. 다음 항목을 하나의 계약으로 다시 맞춰야 한다.

- Agent와 Backend의 책임
- Workflow와 Workflow Step
- Agent Tool 분류
- Agent Tool API
- Webhook과 HITL
- Backend에서 Agent를 재개하는 resume 계약
- Agent State 데이터 스키마
- 공통 변수명
- Backend 개발 요청사항
- Agent 구현과 계약 테스트

이 문서를 기준으로 세부 문서와 관리시트를 순차적으로 갱신한다.

---

## 2. 문서별 정본과 데이터 연동 원칙

모든 정보를 하나의 문서에 중복해서 관리하지 않고 문서별 담당 영역을 나누는 방식을 적용한다. 각 문서는 자신이 담당하는 영역에서만 정본이며, 다른 영역의 상세 내용을 다시 정의하지 않고 안정적인 계약 ID로 참조한다.

### 2.1 문서별 담당 영역

| 정보 영역 | 정본 | 관리 범위 |
|---|---|---|
| 시스템 책임과 통신 원칙 | `agent-backend-integration-contract.md` | Agent·Backend·Frontend 책임, Webhook과 resume 흐름 |
| Backend Tool API 계약 | `agent-tools-api-spec.md` | HTTP Method, Path, 요청·응답 Schema, 오류 코드, 멱등성, Backend 검증 항목 |
| UI와 HITL 계약 | Agent UI·HITL 계약 | `event_type`, `ui_type`, UI 상태, 표시 Payload, 사용자 제출값, resume Payload |
| Workflow 구조 | Google Spreadsheet 관리시트 | Workflow, Step, Route, 입출력 State, Tool·API·UI 계약 매핑 |
| Workflow State 변수 | 관리시트의 Data Schema 탭 | 변수명, 타입, 필수 여부, 생산 Step과 소비 Step |
| 실행 설정 | `workflows.yaml`, `tools.yaml`, `tasks.yaml` | 관리시트와 계약 문서를 기반으로 생성되는 실행 산출물 |
| 실행 코드 | Agent 구현 | 확정된 계약과 생성된 YAML을 준수하는 구현 |

관리시트는 Workflow 구조와 State의 정본이지만 API Path, 전체 요청·응답 JSON과 UI Payload의 정본은 아니다. API와 UI의 상세 계약은 각각의 Markdown 문서에서 관리한다.

현재 YAML과 기존 관리시트에는 Agent가 원장에 직접 접근하던 구조가 남아 있다. 따라서 현재 설정과 기존 관리시트는 참고 자료이며 새로운 계약의 정본으로 사용하지 않는다. 현재 생성된 `agent-management-sheet-v2.xlsx`도 중간 검토 산출물로 취급하고 계약 확정 후 다시 생성한다.

### 2.2 계약 ID

Google Spreadsheet와 Markdown은 파일 형식이 다르므로 제목, Path 또는 설명 문장을 직접 비교하지 않는다. API와 UI 계약에 변경되지 않는 `contract_id`를 부여하고 관리시트는 해당 ID만 참조한다.

```text
API-ACCOUNT-LIST
API-BALANCE-GET
API-RECIPIENT-RESOLVE
API-EXTERNAL-TRANSFER-PREPARE
API-TRANSFER-EXTERNAL-EXECUTE

UI-RECIPIENT-SELECT-INITIAL
UI-RECIPIENT-SELECT-NAME-CANDIDATES
UI-TRANSFER-CONFIRMATION
UI-AUTHENTICATION-REQUEST
UI-TRANSFER-RESULT
```

관리시트의 Step은 다음과 같이 계약을 참조한다.

| step_id | interaction_mode | contract_id |
|---|---|---|
| `resolve_recipient_hint` | `backend_tool_api` | `API-RECIPIENT-RESOLVE` |
| `request_recipient_selection` | `webhook_then_resume` | `UI-RECIPIENT-SELECT-NAME-CANDIDATES` |
| `prepare_external_transfer` | `backend_tool_api` | `API-EXTERNAL-TRANSFER-PREPARE` |

### 2.3 Markdown의 구조화된 계약 블록

검증 스크립트가 일반 Markdown 문장이나 표를 해석하도록 구현하지 않는다. API와 UI 명세의 각 항목에 정해진 형식의 `yaml contract` 블록을 포함하고, 자동화 도구는 이 블록만 읽는다.

````markdown
```yaml contract
contract_id: API-EXTERNAL-TRANSFER-PREPARE
contract_type: backend_tool_api
method: POST
path: /api/v1/agent-tools/transfers/external:prepare
request_fields:
  - from_account_id
  - to_recipient_id
  - to_recipient_candidate_id
  - amount
  - currency
response_fields:
  - outcome
  - confirmation_id
  - confirmation_view
```
````

UI 계약도 같은 형식을 사용한다.

````markdown
```yaml contract
contract_id: UI-RECIPIENT-SELECT-NAME-CANDIDATES
contract_type: webhook_hitl
event_type: need_input
ui_type: recipient_select
ui_state: name_candidates
interrupt: true
resume_fields:
  - recipient_id
```
````

사람은 Markdown의 설명과 JSON 예시를 검토하고 자동화 도구는 구조화된 계약 블록을 사용하여 관리시트와 교차 검증한다.

### 2.4 Google Spreadsheet Snapshot

편집 중인 Google Spreadsheet를 실행 설정 생성에 직접 사용하지 않는다. 검토가 완료된 시트를 XLSX 또는 CSV Snapshot으로 내보내고 해당 Snapshot을 YAML 생성의 입력으로 사용한다.

```text
Google Spreadsheet 편집
-> 검토 완료 상태로 변경
-> XLSX 또는 CSV Snapshot 생성
-> Markdown 계약과 교차 검증
-> 검증 성공 시 YAML 생성
```

Google Spreadsheet는 협업용 정본이고 Snapshot은 특정 계약 버전의 Agent 설정을 재현하기 위한 빌드 입력물이다. Snapshot에는 `contract_version`, `sheet_version`, `exported_at`과 검토 상태를 기록한다.

### 2.5 계약 버전

관리시트, API 명세와 UI 계약은 동일한 `contract_version`을 사용한다.

```text
contract_version: 2026-07-14.1
sheet_version: 1
status: approved
```

계약 버전이 서로 다르거나 관리시트 상태가 `approved`가 아니면 YAML 생성을 중단한다.

### 2.6 충돌 해결 기준

- 시스템 책임과 통신 방향이 다르면 `agent-backend-integration-contract.md`를 기준으로 한다.
- API Method, Path, 요청·응답과 오류 코드가 다르면 `agent-tools-api-spec.md`를 기준으로 한다.
- UI Type, 상태, 표시 Payload와 resume 필드가 다르면 UI·HITL 계약을 기준으로 한다.
- Workflow Step, Route와 State 생산자·소비자가 다르면 승인된 관리시트 Snapshot을 기준으로 한다.
- YAML이 관리시트와 다르면 YAML을 직접 수정하지 않고 다시 생성한다.
- Backend 또는 Frontend 구현이 계약과 다르면 구현을 자동으로 정답으로 간주하지 않는다. 담당 팀이 계약 변경을 합의한 후 정본 문서를 먼저 갱신한다.

### 2.7 교차 검증과 생성 중단 조건

YAML 생성 전 다음 항목을 자동 검사한다.

- 관리시트가 참조한 모든 `api_contract_id`가 API 명세에 존재하는지 여부
- 관리시트가 참조한 모든 `ui_contract_id`가 UI 계약에 존재하는지 여부
- API 출력 필드와 다음 Step 입력 State가 연결되는지 여부
- UI resume 필드가 Workflow Data Schema에 존재하는지 여부
- `interaction_mode`별 필수 계약 ID와 금지 필드 준수 여부
- Backend API 호출과 Webhook 전송이 하나의 Step에 포함되지 않았는지 여부
- Route의 출발 Step과 도착 Step 존재 여부
- 관리시트와 Markdown 계약 버전 일치 여부

오류가 하나라도 발견되면 `workflows.yaml`, `tools.yaml`, `tasks.yaml`을 생성하거나 덮어쓰지 않는다. 검증 결과에는 Workflow ID, Step ID, 계약 ID와 오류 원인을 함께 표시한다.

---

## 3. 목표 구조

### 3.1 전체 통신 구조

```text
Frontend
  -> 사용자 입력, 승인, 인증 결과
Backend
  -> 입력 검증과 상태 저장
  -> Agent Workflow 시작 또는 resume
Agent
  -> Workflow 선택과 Slot 수집
  -> Backend Agent Tool API 호출
  -> Backend Webhook으로 UI와 진행 이벤트 전송
Backend
  -> 금융 조회, 검증, 실행
  -> Webhook을 Redis Stream과 SSE로 중계
Frontend
  -> UI 렌더링
```

### 3.2 Agent 책임

- 사용자 발화 해석
- Workflow 선택
- Slot 추출과 정규화
- 누락 Slot 확인
- 다음 Step과 Route 결정
- Backend Agent Tool API 호출
- Backend가 반환한 결과의 Workflow 분기
- Webhook UI Payload와 사용자 응답 문장 생성
- LangGraph 중단과 resume 처리
- Agent 실행 Trace 기록

### 3.3 Backend 책임

- 사용자 인증과 권한 검증
- Chat Session 소유권 검증
- Execution Context 생성과 관리
- Agent Workflow 시작과 resume 호출
- 계좌와 수취인 소유 범위 검증
- 잔액, 거래내역, 한도, 정책 조회와 검증
- Confirmation과 Auth Context 관리
- 멱등성 관리
- 금융 원장 변경
- 금융 감사 로그 기록
- Agent Webhook 검증
- Redis Stream과 SSE 중계

### 3.4 Frontend 책임

- SSE 이벤트 수신
- `ui_type`에 맞는 UI 렌더링
- 사용자 입력 형식의 기본 검증
- 사용자 입력, 승인, 인증 결과를 Backend에 제출
- 전체 계좌번호와 인증 원문을 Agent에 직접 전달하지 않음

---

## 4. 확정해야 할 핵심 원칙

다음 원칙을 먼저 팀 간에 확정해야 한다.

1. Agent는 DB, 원장, Mock Financial Service를 직접 호출하지 않는다.
2. Agent는 Frontend를 직접 호출하지 않는다.
3. 금융 조회·검증·실행은 `/api/v1/agent-tools/*`를 사용한다.
4. UI 요청과 결과는 `POST /api/v1/webhooks/agent`로 보낸다.
5. 사용자 입력과 승인은 Backend가 검증한 후 Agent를 resume한다.
6. Backend가 검증해서 resume한 입력을 Agent가 다시 Backend에 검증 요청하지 않는다.
7. 금융 상태는 Prepare와 Execute에서 Backend가 다시 검증한다.
8. 사용자 승인과 추가 인증 상태를 Agent가 폴링하지 않는다.
9. 금융 감사 로그의 정본은 Backend가 관리한다.
10. Agent 실행 Trace는 Workflow Step이 아닌 공통 실행 계층에서 기록한다.
11. 한 Workflow Step에는 가능한 한 하나의 외부 동작만 둔다.
12. 전체 계좌번호, PIN, 생체정보와 인증 Assertion은 Agent State에 저장하지 않는다.

---

## 5. 현재 구조에서 우선 제거할 중복

### 5.1 수취인 입력 후 중복 검증

#### 5.1.1 기본 수취인 선택 화면

외부 송금의 기본 `recipient_select` 화면은 다음 두 영역으로 구성한다.

- 상단: 은행과 계좌번호를 입력하여 신규 수취인 계좌를 조회하는 영역
- 하단: 현재 사용자의 기존 출금 거래내역을 기준으로 구성한 최근 수취인 목록

기본 화면의 상단 입력란은 이름 검색 용도로 사용하지 않는다. 수취인 이름은 사용자가 화면에서 검색하는 값이 아니라, 최초 발화에서 Agent가 추출하여 Backend에 자동 확정 가능 여부를 요청할 때 사용하는 힌트다.

#### 5.1.2 최초 발화에 수취인 이름이 포함된 경우

Agent가 최초 발화에서 수취인 이름을 추출한 경우 다음 순서로 처리한다.

```text
사용자 최초 발화
-> Agent가 recipient_name_hint 추출
-> Agent가 Backend의 수취인 자동 확정 Tool API 호출
-> Backend가 현재 사용자의 기존 타인송금 거래에서 고유 수취인 확인
-> resolved이면 Agent가 to_recipient_id 저장
-> selection_required이면 Agent가 수취인 선택 화면 요청
```

수취인 자동 확정의 데이터 범위는 다음과 같이 제한한다.

- 인증된 현재 사용자의 기존 출금 거래내역만 사용한다.
- 전체 사용자 정보, 주소록, 연락처와 타 사용자의 거래내역은 검색하지 않는다.
- 입금 거래 상대방과 카드 결제 가맹점은 후보에서 제외한다.
- 이름을 정규화한 후 완전 일치를 기본 조건으로 사용한다.
- 동일 이름의 서로 다른 계좌는 각각 별도 후보로 유지한다.
- 동일 계좌의 반복 거래는 가장 최근 거래를 기준으로 하나의 후보로 합친다.
- 사용할 수 없는 계좌 또는 거래 제한 상태의 수취인은 후보에서 제외한다.
- 위 조건을 만족하는 고유한 `recipient_id`가 정확히 하나일 때만 자동 확정한다.

#### 5.1.3 자동 확정 결과에 따른 화면 전환

자동 확정 결과는 고유한 수취인 계좌 수를 기준으로 처리한다.

| Backend 판정 | 처리 방식 |
|---|---|
| `resolved` | 반환된 `to_recipient_id`를 Workflow State에 저장하고 다음 Slot으로 진행한다. 별도의 수취인 확인 화면은 표시하지 않는다. |
| `selection_required / no_match` | 기본 `recipient_select` 화면을 한 번 표시한다. 이름과 일치하는 거래가 없음을 안내하고 최근 수취인과 은행·계좌번호 입력 영역을 제공한다. |
| `selection_required / multiple_matches` | `recipient_select`의 `name_candidates` 상태를 한 번 표시하고 사용자가 계좌를 선택하게 한다. |

`resolved`는 사용자 확인 결과가 아니라 Backend 내부 판정이다. Agent는 자동 확정 직후에 "이 수취인이 맞는지"를 묻는 별도 UI를 요청하지 않는다. 선택된 수취인은 금액과 출금 계좌까지 결정된 뒤 최종 송금 확인 화면에 다른 송금 정보와 함께 표시한다.

복수 후보 선택 화면은 새로운 UI 타입을 추가하지 않고 `recipient_select`의 `name_candidates` 상태로 정의한다. Agent는 후보 목록을 받지 않고 `recipient_name_hint`만 Webhook으로 전달한다. Backend가 자동 확정 단계에서 확인한 후보를 이용해 다음 UI Payload를 구성하고 Frontend에 전달한다.

```json
{
  "type": "recipient_select",
  "payload": {
    "purpose": "external_transfer",
    "state": "name_candidates",
    "title": "송금할 계좌를 선택해 주세요.",
    "recipient_name_hint": "홍길동",
    "matched_recipients": [
      {
        "recipient_id": "rcp_001",
        "name": "홍길동",
        "bank_name": "신한은행",
        "masked_account_number": "110-***-123456",
        "last_transfer_at": "2026-07-01"
      },
      {
        "recipient_id": "rcp_003",
        "name": "홍길동",
        "bank_name": "우리은행",
        "masked_account_number": "1002-***-987654",
        "last_transfer_at": "2026-06-21"
      }
    ],
    "account_lookup": {
      "enabled": true
    },
    "actions": [
      "select_recipient",
      "verify_account",
      "show_all_recent",
      "cancel"
    ]
  }
}
```

`name_candidates` 화면에서도 사용자가 이름 검색 결과 대신 계좌번호를 직접 입력하거나 전체 최근 수취인 목록으로 이동할 수 있어야 한다. 단, 이름을 다시 입력하여 검색하는 입력란은 제공하지 않는다.

따라서 정상적인 Workflow에서 사용자에게 표시되는 수취인 선택 화면은 최대 한 번이다. 다만 최종 송금 확인 화면에서 사용자가 수취인 수정을 선택한 경우에는 기존 수취인 ID를 지우고 `recipient_select` 단계로 돌아간다. 이는 자동 확정 후 추가 확인을 요구하는 단계가 아니라 사용자가 명시적으로 수정한 경우의 재입력 흐름이다.

#### 5.1.4 Frontend 입력의 Backend 선검증

기존 흐름에는 다음 왕복이 포함되어 있다.

```text
Frontend 입력
-> Backend
-> Agent resume
-> Agent가 verify_recipient_account 호출
-> Backend가 다시 검증
```

Backend가 Frontend 입력을 검증하고 `to_recipient_id` 또는 `to_recipient_candidate_id`만 Agent에 전달한다면 `verify_recipient_account`는 중복이다.

목표 흐름은 다음과 같다.

```text
Agent -> need_input Webhook
Backend -> Frontend SSE
Frontend -> Backend 입력 제출
Backend -> 입력과 수취인 참조 검증
Backend -> 검증된 참조 ID로 Agent resume
Agent -> 다음 Slot Step 진행
Agent -> 송금 Prepare 호출
Backend -> Prepare에서 수취인 상태 재검증
Backend -> Execute에서 최종 재검증
```

따라서 다음 작업이 필요하다.

- UI 입력 경로의 `verify_recipient_account` Step 제거
- `ask_recipient` 성공 Route를 다음 Slot 확인 Step으로 직접 연결
- `/recipients:verify` Agent Tool API의 필요 여부 재검토
- Frontend 입력 검증과 Prepare·Execute 재검증의 책임 구분

사용자 최초 발화의 이름 힌트는 `/recipients:resolve`로 처리한다. 이 호출은 후보 목록을 Agent에 반환하지 않고, 기존 타인송금 거래에서 고유 수취인이 정확히 한 명일 때만 `to_recipient_id`로 자동 확정한다. 자동 확정할 수 없으면 Agent는 수취인 선택 Webhook만 전송하고 후보와 최근 수취인 데이터는 Backend와 Frontend가 처리한다.

### 5.2 Workflow의 `write_audit_log`

금융 감사 로그는 Backend가 다음 정보로 직접 기록해야 한다.

- 인증된 사용자
- `execution_context_id`
- Operation과 대상 리소스
- `confirmation_id`
- `auth_context_id`
- 정책 판정
- 실행 전 검증 결과
- `Idempotency-Key`
- 금융 실행 결과
- `transaction_id`
- 오류 코드와 처리 시각

Agent Webhook Payload를 그대로 저장하는 것은 금융 감사 로그가 아니다. Webhook 저장값은 이벤트 중계 또는 관측용 Trace로만 사용할 수 있다.

따라서 다음 작업이 필요하다.

- 모든 Workflow에서 `write_audit_log` Step 제거
- `log_id` State와 Data Schema 제거
- 결과, 실패, 취소 Step의 Route를 `END`로 직접 연결
- Agent 실행 Trace는 공통 미들웨어 또는 Callback으로 이동
- 금융 Audit는 Backend Tool API와 승인·인증 API 내부에서 자동 기록

### 5.3 송금 잔액 검사와 실행 직전 검증

송금 Workflow의 `check_balance`, `run_transfer_guardrail`, `run_pre_execution_guardrail`은 잔액과 금융 정책을 여러 단계에서 중복 판정한다. Agent는 원장 정보의 정본을 소유하지 않으므로 잔액 충분 여부, 한도, 승인 상태와 추가 인증의 최종 유효성을 직접 판정해서는 안 된다.

현재 흐름은 다음과 같다.

```text
check_balance
-> run_transfer_guardrail
-> 사용자 승인과 추가 인증
-> run_pre_execution_guardrail
-> execute_transfer
```

목표 흐름은 다음과 같다.

```text
송금 Slot 수집 완료
-> Agent가 Backend Prepare API 호출
-> Backend가 잔액·한도·계좌·수취인 상태 검증
-> Agent가 Prepare 결과에 따라 Route 선택
-> 사용자 승인과 추가 인증
-> Agent가 Backend Execute API 호출
-> Backend가 금융 조건을 최종 재검증하고 송금 실행
```

기존 Step은 다음과 같이 정리한다.

| 기존 Step | 변경 방향 |
|---|---|
| `check_balance` | 송금 Workflow에서 제거한다. |
| `run_transfer_guardrail` | `prepare_external_transfer`로 변경하고 Backend Prepare API 호출만 담당하게 한다. |
| `run_pre_execution_guardrail` | 송금 Workflow에서 제거한다. |
| `execute_transfer` | `execute_external_transfer`로 변경하고 Backend Execute API 호출만 담당하게 한다. |
| `show_insufficient_balance` | Prepare 또는 Execute의 오류 결과를 사용자에게 전달하는 Webhook Step으로 유지한다. |

#### 5.3.1 Backend Prepare 검증

Backend Prepare는 다음 항목을 검증한다.

- 출금 계좌 소유권과 활성 상태
- 현재 출금 가능 잔액
- 송금 금액과 통화
- 송금 한도
- 수취인 유효성
- 송금 준비 단계에 적용되는 금융 정책

잔액이 부족하면 Confirmation을 생성하지 않고 `INSUFFICIENT_BALANCE` 오류를 반환한다. Agent는 잔액을 직접 비교하거나 금융 판단을 수행하지 않고 Backend가 반환한 오류 코드로 Route만 선택한다.

```text
prepare_external_transfer
├─ prepared -> request_confirmation
├─ insufficient_balance -> show_insufficient_balance
├─ limit_exceeded -> show_transfer_limit_error
└─ invalid_recipient -> request_recipient_again
```

#### 5.3.2 Backend Execute 최종 검증

Prepare 이후 사용자 승인과 추가 인증을 처리하는 동안 다른 거래가 발생하여 잔액과 한도가 변경될 수 있다. 따라서 Backend Execute는 다음 항목을 다시 검증한다.

- 출금 가능 잔액과 송금 한도
- 출금 계좌와 수취인의 현재 상태
- Confirmation의 승인 상태와 만료 여부
- 추가 인증 상태와 만료 여부
- 금융 정책
- `Idempotency-Key`와 중복 실행 여부

Execute 시점에 잔액이 부족해진 경우 Backend는 송금을 실행하지 않고 `INSUFFICIENT_BALANCE`를 반환한다. Agent는 이 응답을 `show_insufficient_balance` Webhook Step으로 연결한다.

#### 5.3.3 구조적 요청 검사

금융 검증 Step을 제거하더라도 Agent가 형식이 잘못된 요청을 Backend에 보내서는 안 된다. Agent의 공통 Backend Tool API Adapter는 API 호출 전에 구조적 요청 검사를 수행한다.

구조적 요청 검사는 금융 실행 가능 여부를 판단하는 절차가 아니라, Backend API를 호출하기 위한 요청 데이터가 계약에 맞게 구성되었는지 확인하는 절차다.

검사 대상은 다음과 같다.

- 필수 필드의 존재 여부
- 각 필드의 타입과 허용 형식
- 금액이 숫자이고 0보다 큰지 여부
- `to_recipient_id`와 `to_recipient_candidate_id` 중 정확히 하나만 존재하는지 여부
- 해당 실행 요청에 필요한 `confirmation_id`와 `auth_context_id` 참조의 존재 여부
- 현재 Workflow가 Execute를 호출할 수 있는 상태인지 여부
- 계좌번호 원문, PIN, 생체정보와 인증 Assertion 등 금지된 민감정보의 포함 여부

다음 항목은 구조적 요청 검사에 포함하지 않는다.

- 실제 잔액이 충분한지 여부
- 출금 계좌가 현재 사용자의 계좌인지 여부
- 계좌와 수취인이 현재 송금 가능한 상태인지 여부
- 송금 한도를 초과했는지 여부
- Confirmation과 추가 인증이 실제로 유효한지 여부
- 같은 금융 요청이 이미 실행되었는지 여부
- 금융 정책상 실행 가능한지 여부

이러한 금융 유효성은 Backend Prepare와 Execute가 판정한다. 구조적 요청 검사는 별도 Workflow Step으로 만들지 않고 요청 Schema와 공통 Backend Tool API Adapter에서 일관되게 적용한다.

#### 5.3.4 잔액 조회 Workflow의 예외

사용자가 자신의 잔액을 조회해 달라고 요청한 경우 `wf_balance_inquiry`의 `fetch_balance`는 유지한다. 다만 이 Step도 Agent가 원장을 직접 조회하는 방식이 아니라 Backend 잔액 조회 Tool API를 호출하는 방식으로 구현한다.

즉, 잔액 조회 결과를 사용자에게 제공하는 조회 기능과 송금 가능 여부를 판정하는 금융 검증을 구분한다.

### 5.4 복합 Workflow Step 분리

하나의 Workflow Step은 최대 하나의 외부 동작만 수행한다. Backend Tool API 호출, Webhook 전송과 금융 실행 결과 전송이 연속해서 필요한 경우 각각 별도 Step으로 분리한다.

다음과 같은 복합 실행 방식은 사용하지 않는다.

```text
backend_tool_api_then_webhook
execute_then_webhook
create_auth_context_then_webhook
```

수취인 자동 확정과 선택 화면 요청은 다음과 같이 분리한다.

```text
resolve_recipient_hint
-> route_recipient_resolution
-> request_recipient_selection
-> interrupt
```

송금 Prepare와 승인 요청은 다음과 같이 분리한다.

```text
prepare_external_transfer
-> request_transfer_approval
-> interrupt
```

추가 인증 Context 생성과 인증 요청은 다음과 같이 분리한다.

```text
create_auth_context
-> request_authentication
-> interrupt
```

송금 Execute와 결과 전송은 다음과 같이 분리한다.

```text
execute_external_transfer
-> emit_transfer_result
-> END
```

이를 통해 Backend Tool API가 성공하고 Webhook이 실패한 경우 API를 다시 호출하지 않고 Webhook Step만 재시도할 수 있다. 특히 Prepare에서 생성한 `confirmation_id`, 인증 준비에서 생성한 `auth_context_id`, Execute에서 생성한 `transaction_id`를 Agent State에 먼저 저장한 후 다음 Step을 실행해야 한다.

다만 Webhook 전송과 LangGraph `interrupt`는 하나의 사용자 상호작용을 구성하므로 동일한 HITL Step에서 처리한다. 내부 데이터 정규화와 요청 Schema 검사는 외부 동작을 추가하지 않으므로 해당 API Step 내부에서 수행할 수 있다.

Workflow 정의와 실행 코드의 분리는 별개로 적용한다. 관리시트와 Workflow에서는 외부 동작별로 Step을 분리하되, 실제 구현은 공통 Backend Tool API Adapter와 공통 Webhook Executor를 재사용한다.

---

## 6. 작업 순서

## 6.1 단계 0. 책임과 설계 결정 확정

### 작업

| 결정 항목 | 상태 | 결정 내용 |
|---|---|---|
| Agent·Backend·Frontend 책임 경계 | 확정 | 4장의 핵심 원칙을 적용한다. |
| Frontend 수취인 입력 검증 | 확정 | Backend가 검증한 참조 ID만 Agent에 전달하며 Agent는 같은 입력을 다시 검증하지 않는다. |
| 최초 발화의 이름 검색 범위 | 확정 | 현재 사용자의 기존 출금 거래내역으로 제한한다. |
| 이름 복수 후보 UI | 확정 | 자동 확정이 불가능할 때 `recipient_select`의 `name_candidates` 상태를 한 번 표시한다. 자동 확정 후 별도의 수취인 확인 화면은 표시하지 않는다. |
| Agent Trace와 Backend 금융 Audit | 확정 | Agent Trace는 공통 실행 계층, 금융 Audit는 Backend에서 기록한다. |
| 송금 잔액 검사 | 확정 | 별도 `check_balance` Step을 제거하고 Backend Prepare와 Execute에서 검증한다. |
| 실행 직전 금융 검증 | 확정 | `run_pre_execution_guardrail`을 제거하고 Backend Execute가 최종 검증한다. |
| 구조적 요청 검사 | 확정 | 별도 Workflow Step 없이 요청 Schema와 공통 Backend Tool API Adapter에서 수행한다. |
| 복합 Step 분리 기준 | 확정 | 하나의 Step은 최대 하나의 외부 동작만 수행하며 Backend API와 Webhook은 반드시 분리한다. Webhook과 `interrupt`는 하나의 HITL Step으로 처리한다. |
| `/recipients:verify` Agent Tool API | 확정 | Agent 호출 경로에서 제거한다. 신규 계좌 검증은 Frontend와 Backend가 처리하고 검증된 `to_recipient_candidate_id`만 Agent에 전달한다. |
| 문서별 정본과 데이터 연동 | 확정 | 문서별 담당 영역을 분리하고 `contract_id`, 계약 버전, 승인된 Sheet Snapshot과 교차 검증으로 연결한다. YAML은 생성 산출물로 취급한다. |

### 산출물

- Agent·Backend 책임 결정 문서
- 미결정 항목 목록

### 완료 기준

- Agent, Backend, Frontend 담당자가 같은 흐름을 설명할 수 있음
- 같은 기능의 책임이 Agent와 Backend 양쪽에 중복되지 않음

---

## 6.2 단계 1. 공통 데이터 스키마와 변수명 사전 작성

관리시트를 최종 작성하기 전에 모든 통신과 State에서 사용할 이름을 정한다.

### 변수명 원칙

- 각 Workflow는 독립된 State를 사용한다.
- State 변수명은 점 표기 네임스페이스를 사용하지 않는다.
- 변수명은 영문 `snake_case`를 사용한다.
- Workflow 이름이나 도메인 이름을 모든 변수에 반복해서 붙이지 않는다.
- 같은 Workflow 안에서 역할이 다른 값은 `from_account_id`, `to_account_id`처럼 의미가 드러나게 구분한다.
- 공통 Context 필드도 별도 중첩 객체 없이 동일한 이름을 사용한다.

예를 들어 `account.hint` 대신 `account_hint`를 사용한다.

### 실행 Context

공통 Workflow State에는 다음 실행 Context를 저장한다.

| 변수명 | 타입 | 필수 | 발급 주체 | 생명주기 | 용도 |
|---|---|---:|---|---|---|
| `chat_session_id` | UUID | 필수 | Backend | 채팅방 유지 기간 | 대화와 SSE Stream 식별 |
| `execution_context_id` | UUID | 필수 | Backend | 단일 Workflow 실행 기간 | 사용자 권한 Context, Tool API 검증과 금융 Audit 식별 |
| `agent_thread_id` | string | 필수 | Agent | 단일 Workflow 실행 기간 | LangGraph Checkpoint와 resume 대상 식별 |
| `workflow_id` | string | 필수 | Agent | 단일 Workflow 실행 기간 | 실행 중인 Workflow 식별 |
| `workflow_version` | string | 필수 | Agent 빌드 | 단일 Workflow 실행 기간 | 실행에 사용한 관리시트와 계약 버전 식별 |
| `requested_at` | datetime | 필수 | Backend | 단일 Workflow 실행 기간 | 상대 기간 표현을 해석하는 고정 기준 시각 |
| `timezone` | string | 필수 | Backend | 단일 Workflow 실행 기간 | 사용자 기준 날짜 계산에 사용하는 IANA Timezone |

식별자 관계는 다음과 같이 정의한다.

```text
chat_session_id
└─ execution_context_id
   └─ agent_thread_id
```

- 하나의 `chat_session_id`에서 여러 Workflow 실행이 발생할 수 있다.
- 하나의 `execution_context_id`는 하나의 Workflow 실행을 나타낸다.
- `execution_context_id`와 `agent_thread_id`는 기본적으로 1:1 관계로 관리한다.
- Backend는 `execution_context_id`에 인증된 사용자, `chat_session_id`, `agent_thread_id`, 권한 Scope와 실행 상태를 연결한다.
- 현재 Backend의 `agent_executions.id`를 `execution_context_id`로 사용하는 방향을 우선 적용한다.
- 대화 기억이 필요한 경우 `chat_session_id` 기반 메모리를 별도로 사용하며 서로 다른 Workflow가 같은 `agent_thread_id`를 공유하지 않는다.

`request_id`는 단일 HTTP 요청을 추적하는 통신 계층 값이므로 Workflow State에 저장하지 않는다. 외부 요청을 보내는 서비스가 `X-Request-Id`를 생성하며 같은 HTTP 요청을 재시도할 때만 같은 값을 유지한다. 새로운 Backend Tool API 호출, Webhook 전송 또는 resume 요청에는 새로운 `request_id`를 사용한다.

공통 Backend Tool API Adapter는 조회·Prepare·Execute·Auth Context 생성 요청의 연결·응답 Timeout 또는 HTTP `502`, `503`, `504`에 한해 자동으로 최대 1회 재시도한다. 최초 호출을 포함한 최대 호출 횟수는 2회다. 통신 재시도에서는 같은 `X-Request-Id`를 유지하며, 상태 변경 요청은 같은 `Idempotency-Key`와 Body도 유지한다. `429`, 입력·권한·인증 오류와 `correction_required`, `blocked` 같은 업무 결과는 자동 재시도하지 않는다. 이 재시도는 API Adapter 내부 동작이므로 별도 Workflow Step을 만들지 않고, 재시도까지 실패한 경우에만 해당 API Step의 오류 Route로 이동한다.

다음 값도 공통 실행 Context에 포함하지 않는다.

| 변수명 | 제외 이유 | 관리 위치 |
|---|---|---|
| `user_id` | Agent가 금융 권한의 근거로 사용해서는 안 됨 | Backend Execution Context 내부 |
| `sse_session_id` | Frontend의 일회용 SSE 접속 티켓 | Frontend와 Backend |
| `idempotency_key` | 상태에 원문을 저장하지 않고 실행 식별자와 시도 번호로 생성 | 공통 Backend Tool API Adapter |
| `input_request_id` | 일반 사용자 입력 대기에만 필요 | HITL 대기 State |
| `confirmation_id` | Prepare 이후 승인과 실행에만 필요 | 변경 Workflow State |
| `auth_context_id` | 추가 인증이 필요한 실행에만 필요 | 인증 대기 Workflow State |
| `transaction_id` | 금융 실행 완료 이후에만 생성 | 실행 결과 State |

### 공통 Schema와 Workflow Schema 분리

공통 실행 Context를 각 Workflow Data Schema에 반복해서 작성하지 않는다. 관리시트에서는 공통 필드와 Workflow 업무 필드를 별도 탭에서 관리하고 Agent State 생성 시 병합한다.

```text
Common Data Schema
+ Workflow Data Schema
= Resolved Workflow Schema
```

`Common Data Schema`는 `chat_session_id`, `execution_context_id`, `agent_thread_id`, `workflow_id`, `workflow_version`, `requested_at`, `timezone`의 정본이다. `Workflow Data Schema`에는 계좌, 수취인, 금액, 기간과 실행 결과처럼 해당 Workflow에서만 사용하는 업무 필드를 정의한다.

생성기는 다음 순서로 최종 Workflow State Schema를 만든다.

1. Common Data Schema를 읽는다.
2. 대상 Workflow Data Schema를 읽는다.
3. 두 Schema의 `state_key` 중복과 타입 충돌을 검사한다.
4. 공통 필드와 Workflow 필드를 병합한다.
5. Step State Mapping과 State Constraint 참조를 검사한다.
6. 최종 Agent State 모델과 검토용 Resolved Workflow Schema를 생성한다.

공통 필드와 Workflow 필드에 같은 `state_key`가 존재하면 Workflow별 재정의로 처리하지 않고 생성 오류로 처리한다. 공통 Context의 타입과 의미는 모든 Workflow에서 동일해야 한다.

`Resolved Workflow Schema`는 읽기 전용 검토 탭으로 생성한다. 각 행에는 `workflow_id`, `state_key`, 최종 타입과 `schema_source`를 표시하여 하나의 Workflow가 실제로 사용하는 전체 State를 한 화면에서 확인할 수 있게 한다.

코드에서도 같은 구조를 적용한다.

```text
CommonWorkflowState
-> BalanceInquiryState
-> ExternalTransferState
-> InternalTransferState
-> 그 밖의 Workflow State
```

각 Workflow는 최종적으로 독립된 State와 Checkpoint를 사용하지만 공통 필드 정의는 하나의 Base Schema에서 재사용한다.

### 사용자 상호작용 State

| 변수명 | 타입 | 사용 시점 | 발급 주체 | 용도 |
|---|---|---|---|---|
| `input_request_id` | string 또는 null | 일반 입력 대기 | Agent | 일반 입력 요청과 resume 매칭 |
| `confirmation_id` | string 또는 null | Prepare 이후 승인과 Execute | Backend | 고정된 변경 요청, 승인과 실행 연결 |
| `auth_context_id` | string 또는 null | 추가 인증 | Backend | 추가 인증 요청과 실행 연결 |

`prompt_for`는 공통 State, Webhook, Frontend 제출값과 Agent resume 계약에서 제거한다. 일반 입력은 `input_request_id`로 요청 인스턴스를 식별하고 `ui_contract_id`로 제출 Payload Schema를 결정한다. 입력 결과가 저장될 State는 현재 Workflow Step의 Step State Mapping으로 결정한다.

Backend는 `input_request_id`에 `execution_context_id`, `agent_thread_id`, `ui_contract_id`, 상태를 연결하여 Pending Input으로 저장한다. Frontend는 `input_request_id`와 `value`만 제출하며 Backend는 저장된 UI 계약으로 값을 검증한 후 Agent를 resume한다.

```text
input_request_id
-> Pending Input 조회
-> ui_contract_id 확인
-> resume Schema로 value 검증
-> Agent resume
```

Backend 검증에 실패하면 Agent를 resume하지 않고 같은 `input_request_id`를 유지한다. Agent가 입력을 정상적으로 소비하면 해당 ID를 State에서 제거한다. 새로운 입력 요청에는 새로운 `input_request_id`를 발급한다.

한 `agent_thread_id`에는 동시에 하나의 활성 대기 상호작용만 허용한다. 승인 이후 추가 인증 단계에서는 `confirmation_id`와 `auth_context_id`가 함께 State에 존재할 수 있지만 실제 대기 대상은 `auth_context_id` 하나다.

### 계좌 State

계좌 확인 결과, 선택 UI 후보와 Workflow에서 확정하여 사용하는 계좌 참조를 분리한다.

| 변수명 | 타입 | 사용 범위 | 보존 범위 | 용도 |
|---|---|---|---|---|
| `account_hint` | string 또는 null | 일반 계좌 식별 Workflow | Workflow | 사용자 발화에서 추출한 은행명, 별칭 또는 계좌 유형 힌트 |
| `from_account_hint` | string 또는 null | 송금 Workflow | Workflow | 출금 계좌를 확인하기 위한 사용자 발화 힌트 |
| `to_account_hint` | string 또는 null | 본인송금 Workflow | Workflow | 입금 계좌를 확인하기 위한 사용자 발화 힌트 |
| `account_resolution_outcome` | string 또는 null | 계좌 자동 확정 Workflow | 입력 대기 | `resolved`, `selection_required`, `no_accounts` Backend 결과 |
| `accounts` | `list[AccountCandidate]` | 계좌 선택 UI가 필요한 Workflow | 입력 대기 | Backend가 반환한 마스킹된 계좌 선택 후보 |
| `account_selection_outcome` | string 또는 null | 계좌 선택 UI가 필요한 Workflow | 입력 대기 | Backend가 검증한 `selected`, `cancelled` 결과 |
| `account_ids` | `list[string]` | 잔액·거래내역 등 조회 Workflow | Workflow | 사용자 선택 또는 자동 확정으로 결정된 조회 대상 계좌 |
| `from_account_id` | string 또는 null | 외부 송금·본인 계좌 간 이체 | Workflow | 출금 계좌 참조 ID |
| `to_account_id` | string 또는 null | 본인 계좌 간 이체 | Workflow | 입금할 본인 계좌 참조 ID |
| `account_id` | string 또는 null | 별칭·기본계좌 변경 등 단일 대상 설정 | Workflow | 설정을 변경할 계좌 참조 ID |

Backend 계좌 확인 API와 선택 재개 Payload는 항상 `account_ids` 배열을 사용한다. 단일 계좌 Workflow는 배열 길이가 정확히 하나일 때만 Workflow 목적에 맞는 `account_id`, `from_account_id` 또는 `to_account_id`로 저장한다. 별도 `selection_mode`, 단일 `account_id` 재개 필드와 `account_candidate_ids`는 사용하지 않는다.

`AccountCandidate`에는 다음과 같은 UI 표시용 최소 필드만 허용한다.

```text
account_id
bank_name
account_alias
account_type
masked_account_number
is_default
```

전체 계좌번호, 계좌 비밀번호, PIN, 인증 Assertion, Backend 내부 사용자 ID와 원장 내부 식별자는 `accounts`에 포함하지 않는다. 잔액도 계좌 선택 화면에 반드시 필요하지 않으면 후보 정보에 포함하지 않는다.

Backend Tool API 호출과 Webhook 전송을 별도 Step으로 분리하므로 계좌 확인 Step이 반환한 `accounts`는 다음 선택 Step까지 Agent State에 임시 저장한다. Backend가 사용자 선택을 검증하여 Agent를 재개하면 후보 목록은 비우고 확정된 계좌 ID만 업무 State에 유지한다.

```text
resolve_accounts
-> account_resolution_outcome 확인
-> selection_required이면 accounts 임시 저장
-> request_account_selection
-> interrupt
-> Backend 검증 후 account_selection_outcome과 account_ids로 resume
-> accounts 제거
-> account_ids 또는 단일 계좌 ID 저장
```

`resolved`이면 `account_ids`가 정확히 하나인 경우 선택 화면을 생략한다. `selection_required`이면 Backend가 검증한 최신 `accounts`를 표시하고, `no_accounts`이면 같은 선택 UI의 빈 상태를 전송한 뒤 종료한다. Agent는 후보 개수만 보고 자동 확정하거나 빈 결과에서 임의로 다시 조회하지 않는다.

Workflow별 사용 기준은 다음과 같다.

- 잔액·거래내역처럼 복수 계좌를 조회할 수 있으면 `account_ids`를 사용한다.
- 외부 송금의 출금 계좌는 `from_account_id`를 사용한다.
- 외부 송금의 수취인은 `to_account_id`가 아니라 `to_recipient_id` 또는 `to_recipient_candidate_id`를 사용한다.
- 본인 계좌 간 이체는 `from_account_id`와 `to_account_id`를 사용한다.
- 별칭 변경과 기본계좌 변경처럼 단일 대상 계좌만 사용하는 독립 Workflow에서는 `account_id`를 사용한다.
- 본인 계좌 간 이체에서 출금 계좌와 입금 계좌를 순서대로 선택할 때는 임시 `accounts`, `account_resolution_outcome`, `account_selection_outcome`을 재사용한다.

다음과 같이 타입과 역할이 모호한 필드는 사용하지 않는다.

```text
account_candidate_ids
selected_account
from_account
to_account
```

계좌 후보와 선택 결과의 Step State Mapping 예시는 다음과 같다.

| step_id | direction | state_key | contract_field_path |
|---|---|---|---|
| `resolve_accounts` | `input` | `account_hint` | `query.account_hint` |
| `resolve_accounts` | `output` | `account_resolution_outcome` | `response.data.account_resolution_outcome` |
| `resolve_accounts` | `output` | `accounts` | `response.data.accounts` |
| `resolve_accounts` | `output` | `account_ids` | `response.data.account_ids` |
| `request_account_selection` | `input` | `accounts` | `webhook.metadata.ui.payload.accounts` |
| `request_account_selection` | `output` | `account_selection_outcome` | `resume.value.account_selection_outcome` |
| `request_account_selection` | `output` | `account_ids` | `resume.value.account_ids` |
| `fetch_balance` | `input` | `account_ids` | `request.account_ids` |

### 수취인 State

수취인 이름 힌트와 최종 수취인 참조를 분리한다. 이름 후보와 최근 수취인 목록은 Backend와 Frontend가 UI 표시용으로 관리하며 Agent State에 저장하지 않는다.

| 변수명 | 타입 | 보존 범위 | 용도 |
|---|---|---|---|
| `recipient_name_hint` | string 또는 null | Workflow | 최초 발화에서 추출한 수취인 이름 자동 확정 힌트 |
| `to_recipient_id` | string 또는 null | Workflow | 선택된 기존 수취인 참조 ID |
| `to_recipient_candidate_id` | string 또는 null | Workflow | Backend가 신규 계좌를 검증한 후 발급한 수취인 후보 참조 ID |

`recipient_name`은 검증된 실제 수취인명과 혼동될 수 있으므로 `recipient_name_hint`를 사용한다. 이름 후보, 최근 수취인과 신규 계좌 입력 데이터는 `UI-RECIPIENT-SELECT`를 처리하는 Backend와 Frontend의 책임이다.

최초 발화에 이름이 없는 경우 다음 상태로 시작한다.

```json
{
  "recipient_name_hint": null,
  "to_recipient_id": null,
  "to_recipient_candidate_id": null
}
```

최초 발화에 이름이 있으면 Agent는 `recipient_name_hint`로 `API-RECIPIENT-RESOLVE`를 호출한다. Backend는 현재 사용자의 완료된 기존 타인송금 거래에서 이름이 정확히 일치하는 고유 수취인 참조를 확인한다.

- 고유 수취인 1건: `outcome=resolved`와 `to_recipient_id`를 반환하며 선택 UI를 생략한다.
- 고유 수취인 2건 이상: `outcome=selection_required`, `selection_reason=multiple_matches`를 반환한다.
- 후보 없음: `outcome=selection_required`, `selection_reason=no_match`를 반환한다.

`selection_required`이거나 최초 발화에 이름이 없으면 Agent는 후보 목록을 조회하지 않고 `UI-RECIPIENT-SELECT` Webhook을 전송하고 중단한다. Backend는 Execution Context와 `recipient_name_hint`를 이용해 이름 후보 또는 최근 수취인을 조회하고 Frontend에 표시한다.

Backend가 기존 수취인 선택을 검증하여 Agent를 resume하면 `to_recipient_id`에 저장한다.

사용자가 은행과 계좌번호를 직접 입력하면 Backend가 Agent를 resume하기 전에 계좌를 검증한다. Agent에는 원본 `bank_code`, `account_number`, 예금주명과 검증 원문을 전달하지 않고, 사용자가 검증 결과를 확정한 후 `to_recipient_candidate_id`만 resume 값으로 전달한다. Agent는 같은 이름의 State 필드에 이를 저장한다.

Prepare를 호출하기 전에는 `to_recipient_id`와 `to_recipient_candidate_id` 중 정확히 하나만 존재해야 한다.

| workflow_id | constraint_id | constraint_type | state_keys | 적용 시점 |
|---|---|---|---|---|
| `wf_external_transfer` | `recipient_reference` | `exactly_one` | `to_recipient_id`, `to_recipient_candidate_id` | `prepare_external_transfer` 호출 전 |

수취인 관련 Step State Mapping 예시는 다음과 같다.

| step_id | direction | state_key | contract_field_path |
|---|---|---|---|
| `extract_transfer_slots` | `output` | `recipient_name_hint` | `agent.extracted.recipient_name_hint` |
| `resolve_recipient_hint` | `input` | `recipient_name_hint` | `request.recipient_name_hint` |
| `resolve_recipient_hint` | `output` | `to_recipient_id` | `response.data.to_recipient_id` |
| `request_recipient_selection` | `input` | `recipient_name_hint` | `webhook.metadata.ui.payload.recipient_name_hint` |
| `request_recipient_selection` | `output` | `to_recipient_id` | `resume.value.to_recipient_id` |
| `request_recipient_selection` | `output` | `to_recipient_candidate_id` | `resume.value.to_recipient_candidate_id` |
| `prepare_external_transfer` | `input` | `to_recipient_id` | `request.to_recipient_id` |
| `prepare_external_transfer` | `input` | `to_recipient_candidate_id` | `request.to_recipient_candidate_id` |

이름 힌트, 원본 입력 객체와 확정된 수취인 ID를 하나의 `recipient` 필드에 혼합하지 않는다.

### 송금 State

송금 State는 사용자 요청값, Prepare와 Confirmation, 추가 인증, Execute 결과와 멱등성 제어값으로 구분한다. 송금 메모는 현재 요구사항에서 사용하지 않으므로 `memo` 필드를 Workflow State, Prepare API 요청과 Confirmation 표시 데이터에서 제거한다.

| 변수명 | 타입 | 기본값 | 보존 범위 | 용도 |
|---|---|---|---|---|
| `amount` | integer 또는 null | null | Workflow | 송금 금액 |
| `currency` | string | `KRW` | Workflow | 송금 통화 |
| `confirmation_id` | string 또는 null | null | Prepare부터 Execute까지 | Backend가 고정한 승인 대상 참조 |
| `confirmation_view` | `ConfirmationView` 또는 null | null | 승인 입력 대기 | 마스킹된 승인 UI 표시 데이터 |
| `auth_context_id` | string 또는 null | null | 인증 Context 생성부터 Execute까지 | Backend 추가 인증 참조 |
| `auth_request_view` | `AuthRequestView` 또는 null | null | 인증 입력 대기 | 인증 UI 표시 데이터 |
| `transaction_id` | string 또는 null | null | 실행 결과 | 완료된 금융 거래 참조 |
| `completed_at` | datetime 또는 null | null | 실행 결과 | 금융 실행 완료 시각 |
| `prepare_attempt` | integer | 0 | Workflow | 새로운 Prepare 작업의 시도 번호 |
| `auth_attempt` | integer | 0 | Workflow | 새로운 Auth Context 생성 작업의 시도 번호 |

`amount`는 KRW 최소 화폐 단위의 정수로 저장하고 Agent는 정수이며 0보다 큰지만 구조적으로 검사한다. 실제 최소·최대 금액, 잔액, 한도와 정책은 Backend Prepare와 Execute가 검증한다. `currency`는 현재 `KRW`만 허용하며 외화 송금이 추가될 때 Enum을 확장한다.

#### Prepare와 승인 화면 데이터

Prepare API 응답의 `confirmation_id`는 Execute까지 유지한다. API 호출과 승인 Webhook을 분리하므로 마스킹된 계좌·수취인 정보, 경고 코드와 만료시각이 포함된 `confirmation_view`를 같은 이름의 State에 임시 저장한다.

```text
prepare_external_transfer
-> confirmation_id 저장
-> confirmation_view 저장
-> request_transfer_approval
-> interrupt
```

승인이 완료되면 `confirmation_view`는 제거하고 `confirmation_id`는 유지한다. 타인송금과 본인송금은 금액과 위험도에 관계없이 항상 추가 인증을 수행한다. 사용자가 출금 계좌, 입금 대상 또는 금액을 수정하면 Backend가 기존 Confirmation을 무효화하고 Agent는 해당 값을 반영한 뒤 `confirmation_id`, `confirmation_view`, 기존 인증 관련 State를 제거하여 새로운 Prepare를 수행한다.

#### 추가 인증 화면 데이터

Auth Context 생성 API와 인증 요청 Webhook도 별도 Step으로 분리한다. Backend가 반환한 인증 방식과 만료시각은 `auth_request_view`에 임시 저장한다.

```text
create_auth_context
-> auth_context_id 저장
-> auth_request_view 저장
-> request_authentication
-> interrupt
```

인증 완료 후 `auth_request_view`는 제거하고 `auth_context_id`는 Execute까지 유지한다. Agent는 인증 상태를 조회하거나 인증 원문을 저장하지 않는다.

#### Execute 결과

Execute 응답의 `transaction_id`와 `completed_at`을 State에 저장한 후 별도 결과 Webhook Step을 실행한다. `amount`와 `currency`는 이미 Workflow State에 있으므로 Execute 응답의 같은 값을 별도 결과 객체로 중복 저장하지 않는다.

```text
execute_external_transfer
-> transaction_id 저장
-> completed_at 저장
-> emit_transfer_result
-> END
```

#### 멱등성 키 생성 원칙

멱등성 키 원문은 Workflow State에 저장하지 않는다. Prepare와 Auth Context 생성은 State에 시도 번호를 저장하고, 공통 Backend Tool API Adapter가 Operation, 실행 식별자와 시도 번호를 조합해 같은 논리 요청에 항상 같은 키를 생성한다.

```text
Prepare
external_transfer_prepare:{execution_context_id}:{prepare_attempt}

Auth Context 생성
external_transfer_auth:{confirmation_id}:{auth_attempt}

Execute
external_transfer_execute:{confirmation_id}:{auth_attempt}
```

Prepare와 Auth Context 생성의 시도 번호는 API 호출 전에 별도 Agent 내부 Step에서 증가시키고 LangGraph Checkpoint에 저장한다.

```text
start_prepare_attempt
-> prepare_attempt 증가
-> Checkpoint 저장
-> prepare_external_transfer
```

```text
start_auth_attempt
-> auth_attempt 증가
-> Checkpoint 저장
-> create_auth_context
```

동일 요청이 timeout 또는 응답 유실로 재시도되는 경우 시도 번호를 증가시키지 않고 API Step만 다시 실행한다. 사용자 수정, 인증 실패 후 재인증처럼 새로운 논리 작업을 시작할 때만 시도 번호를 증가시킨다.

Execute에는 별도 `execute_attempt`를 만들지 않는다. 추가 인증이 필요한 송금 Execute는 `confirmation_id`와 `auth_attempt`로 키를 생성한다. 동일 인증 시도의 통신 재시도는 같은 키와 Body를 유지하고, 재인증으로 `auth_context_id`가 바뀌면 증가한 `auth_attempt`로 새 키를 생성한다. Backend는 키가 달라져도 같은 Confirmation이 두 번 실행되지 않도록 Confirmation 상태와 고유 제약으로 차단한다. 추가 인증을 사용하지 않는 설정 변경 Execute는 기존처럼 `confirmation_id`로 키를 고정한다.

Backend의 멱등성 저장소는 다음 규칙을 적용한다.

- 같은 Context, Operation, Key와 같은 요청 Body면 기존 응답을 반환한다.
- 같은 Key에 다른 요청 Body면 `IDEMPOTENCY_KEY_CONFLICT`를 반환한다.
- 처리 중인 요청은 중복 실행하지 않는다.
- 금융 실행 완료 후 응답이 유실되면 같은 키의 재시도에 기존 `transaction_id`를 반환한다.
- 멱등성 키 생성 규칙은 진행 중인 Workflow가 종료될 때까지 변경하지 않는다.

초기 송금 State 예시는 다음과 같다.

```json
{
  "amount": null,
  "currency": "KRW",
  "confirmation_id": null,
  "confirmation_view": null,
  "auth_context_id": null,
  "auth_request_view": null,
  "transaction_id": null,
  "completed_at": null,
  "prepare_attempt": 0,
  "auth_attempt": 0
}
```

### 기간 State

기간은 중첩 `period_range` 객체를 만들지 않고 `start_date`, `end_date` 두 필드로 관리한다.

| 변수명 | 타입 | 기본값 | 용도 |
|---|---|---|---|
| `start_date` | date 또는 null | null | 조회 시작일 |
| `end_date` | date 또는 null | null | 조회 종료일 |

두 필드는 `YYYY-MM-DD` 형식을 사용하며 사용자 관점에서 시작일과 종료일을 모두 포함한다. Backend는 원장을 조회할 때 사용자 Timezone을 기준으로 다음 반개구간으로 변환한다.

```text
transaction_at >= start_date 00:00:00
transaction_at < end_date 다음 날 00:00:00
```

상대 기간은 Agent 서버의 현재 시각이 아니라 Backend가 Workflow 시작 시 전달한 `requested_at`과 `timezone`을 기준으로 정규화한다. 초기 버전의 기본 Timezone은 `Asia/Seoul`로 한다. Workflow가 자정을 넘어 resume되더라도 최초 발화의 `오늘`과 `이번 달` 의미는 변경하지 않는다.

기준 시각이 `2026-07-14T10:30:00+09:00`인 경우 다음 규칙을 적용한다.

| 사용자 표현 | `start_date` | `end_date` |
|---|---|---|
| 오늘 | `2026-07-14` | `2026-07-14` |
| 어제 | `2026-07-13` | `2026-07-13` |
| 이번 달 | `2026-07-01` | `2026-07-14` |
| 지난달 | `2026-06-01` | `2026-06-30` |
| 최근 7일 | `2026-07-08` | `2026-07-14` |
| 2026년 5월 | `2026-05-01` | `2026-05-31` |

`최근 N일`은 요청일을 포함한 N개의 달력 날짜로 계산한다. 시작일만 명시하면 종료일을 `requested_at`의 현지 날짜로 보완한다. 종료일만 명시되어 있고 기본 조회 기간 정책으로 시작일을 확정할 수 없으면 기간 입력 UI를 요청한다.

기간을 입력하지 않은 초기 State는 다음과 같다.

```json
{
  "start_date": null,
  "end_date": null
}
```

Frontend가 날짜를 제출하면 Backend가 날짜 형식, 순서, 최대 조회 기간, 미래 날짜와 조회 가능 범위를 검증한 후 Agent를 resume한다. Agent는 검증된 날짜를 State에 저장하고 조회 Tool API를 호출한다.

조회 API 호출 전 다음 제약조건을 적용한다.

| constraint_id | constraint_type | state_keys | 적용 시점 |
|---|---|---|---|
| `period_required` | `all_required` | `start_date`, `end_date` | 거래내역·기간 합계 API 호출 전 |
| `period_order` | `less_than_or_equal` | `start_date`, `end_date` | 날짜 정규화와 Backend 입력 검증 |

기간 관련 Step State Mapping 예시는 다음과 같다.

| step_id | direction | state_key | contract_field_path |
|---|---|---|---|
| `start_execution` | `output` | `requested_at` | `request.requested_at` |
| `start_execution` | `output` | `timezone` | `request.timezone` |
| `extract_period_slots` | `input` | `requested_at` | `state.requested_at` |
| `extract_period_slots` | `input` | `timezone` | `state.timezone` |
| `extract_period_slots` | `output` | `start_date` | `agent.extracted.start_date` |
| `extract_period_slots` | `output` | `end_date` | `agent.extracted.end_date` |
| `request_period_selection` | `output` | `start_date` | `resume.value.start_date` |
| `request_period_selection` | `output` | `end_date` | `resume.value.end_date` |
| `query_transactions` | `input` | `start_date` | `request.start_date` |
| `query_transactions` | `input` | `end_date` | `request.end_date` |

`from_date`, `to_date`, `period_range`, `start_at`, `end_at`은 현재 날짜 기반 조회 Workflow State에서 사용하지 않는다. 시각 단위 조회가 필요해지면 별도 계약으로 `start_at`, `end_at`을 정의한다.

### Workflow별 State Schema

#### `wf_global_agent_entry`

글로벌 Agent 진입 Workflow는 사용자 요청의 안전성 검사, 지원 업무 분류와 업무 Workflow Dispatch만 담당한다. 선택된 업무 Workflow가 자체 결과·오류 Webhook과 HITL 중단·재개를 처리하므로 글로벌 Workflow는 업무 완료 후 별도 최종 응답을 생성하지 않는다.

| state_key | data_type | nullable | 기본값 | 역할 |
|---|---|---:|---|---|
| `guardrail_outcome` | string | true | null | 전역 안전성 검사의 `allowed`, `blocked` 결과 |
| `blocked_view` | `GlobalBlockedView` | true | null | 사용자에게 표시할 수 있는 전역 정책 차단 안내 |
| `workflow_match_outcome` | string | true | null | 업무 Workflow 분류의 `matched`, `no_match` 결과 |
| `matched_workflow_id` | string | true | null | 실행할 수 있는 업무 Workflow ID |
| `dispatch_outcome` | string | true | null | 업무 Workflow Dispatch의 `completed`, `failed` 결과 |

사용자 원문은 별도 업무 State 필드로 복제하지 않고 Agent Runtime의 입력 메시지를 사용한다. `run_global_guardrail`은 정책 위반 여부를 판정하지만 금융 계좌·잔액·한도와 같은 업무 검증은 수행하지 않는다. `match_workflow`는 지원되는 업무 Workflow 중 하나를 선택할 뿐 계좌·수취인·금액 Slot을 추출하지 않는다. Slot 추출은 Dispatch된 업무 Workflow의 첫 Step에서 수행한다.

```text
run_global_guardrail
-> allowed이면 match_workflow
-> blocked이면 emit_global_blocked -> END

match_workflow
-> matched이면 dispatch_matched_workflow
-> no_match이면 emit_no_matching_workflow -> END

dispatch_matched_workflow
-> completed이면 추가 Webhook 없이 END
-> Dispatch 자체가 실패하면 emit_workflow_dispatch_error -> END
```

`dispatch_outcome=completed`는 선택된 업무 Workflow가 자신의 결과 또는 오류 처리를 포함하여 정상적인 종료 지점에 도달했다는 뜻이다. 업무 Workflow가 이미 오류 Webhook을 전송하고 정상 종료한 경우도 글로벌 Workflow에서는 `completed`로 취급하여 중복 오류를 보내지 않는다. `failed`는 업무 Workflow를 시작하지 못했거나 처리되지 않은 예외로 Dispatch 자체가 실패한 경우에만 사용한다.

기존의 `execute_matched_workflow`, `return_response`, `show_global_blocked`, `show_no_matching_workflow`, `show_workflow_failed`는 현재 명명과 책임 기준에 맞게 다음 Step으로 대체한다.

| step_id | interaction_mode | contract_id |
|---|---|---|
| `run_global_guardrail` | `agent_internal` | 없음 |
| `match_workflow` | `agent_internal` | 없음 |
| `dispatch_matched_workflow` | `agent_internal` | 없음 |
| `emit_global_blocked` | `webhook` | `UI-GLOBAL-BLOCKED` |
| `emit_no_matching_workflow` | `webhook` | `UI-NO-MATCH` |
| `emit_workflow_dispatch_error` | `webhook` | `UI-COMMON-ERROR` |

Step State Mapping은 다음과 같다.

| step_id | direction | state_key | contract_field_path |
|---|---|---|---|
| `run_global_guardrail` | `output` | `guardrail_outcome` | `agent.state.guardrail_outcome` |
| `run_global_guardrail` | `output` | `blocked_view` | `agent.state.blocked_view` |
| `match_workflow` | `output` | `workflow_match_outcome` | `agent.state.workflow_match_outcome` |
| `match_workflow` | `output` | `matched_workflow_id` | `agent.state.matched_workflow_id` |
| `dispatch_matched_workflow` | `input` | `matched_workflow_id` | `agent.runtime.workflow_id` |
| `dispatch_matched_workflow` | `output` | `dispatch_outcome` | `agent.state.dispatch_outcome` |
| `emit_global_blocked` | `input` | `blocked_view` | `webhook.metadata.ui.payload` |

글로벌 Workflow의 `max_risk_level=R5`는 금지·차단 대상까지 판별 범위에 포함한다는 의미다. 실행 가능한 업무는 각 업무 Workflow의 위험등급을 따르며 글로벌 내부 Step 자체가 R5 금융 작업을 실행한다는 의미가 아니다.

#### `wf_account_list`

계좌 목록 조회는 사용자 선택을 기다리지 않는 읽기 전용 Workflow다. 업무 State는 다음 두 필드만 사용한다.

| state_key | data_type | nullable | 기본값 | 보존 범위 | 역할 |
|---|---|---:|---|---|---|
| `account_hint` | string | true | null | Workflow | 사용자 발화에서 추출한 선택적 계좌 검색 힌트 |
| `account_results` | `list[AccountSummary]` | false | `[]` | 결과 | Backend가 반환한 최종 계좌 목록 |

`account_results`는 결과 목록이므로 사용자 선택용 임시 값인 `accounts`와 구분한다. `AccountSummary`에는 `account_id`, `bank_name`, `account_alias`, `account_type`, `masked_account_number`, `currency`, `is_default`, `status`만 허용하며 전체 계좌번호와 잔액은 포함하지 않는다.

Workflow Step은 다음과 같이 구성한다.

```text
extract_account_list_slots
-> fetch_account_list
-> emit_account_list_result
-> END
```

`account_hint`가 있으면 계좌 목록 API의 `account_hint`에 그대로 매핑한다. `account_capability`와 `limit=20`은 사용자가 변경하는 State가 아니라 Tool 설정값으로 관리한다. 일반 계좌 목록 조회는 `account_capability`를 생략한다.

```text
account_hint: null
-> GET /accounts?limit=20

account_hint: 생활비
-> GET /accounts?account_hint=생활비&limit=20
```

조회 결과 Route는 다음과 같이 구분한다.

```text
fetch_account_list
├─ success -> emit_account_list_result
└─ backend_error -> emit_account_list_error
```

계좌가 없는 경우도 조회 성공이며 `accounts=[]`로 처리한다. Agent는 별도의 빈 결과 Step이나 UI 계약을 사용하지 않고 동일한 `account_list` 결과 Webhook을 보낸다. Frontend는 빈 배열을 기준으로 빈 상태를 표시한다. Backend 호출 실패만 오류 Route로 분리한다. 결과 Webhook은 사용자 입력을 기다리지 않으므로 `input_request_id`와 `interrupt`를 사용하지 않는다.

Step State Mapping은 다음과 같다.

| step_id | direction | state_key | contract_field_path |
|---|---|---|---|
| `extract_account_list_slots` | `output` | `account_hint` | `agent.extracted.account_hint` |
| `fetch_account_list` | `input` | `account_hint` | `query.account_hint` |
| `fetch_account_list` | `output` | `account_results` | `response.data.accounts` |
| `emit_account_list_result` | `input` | `account_results` | `webhook.metadata.ui.payload.accounts` |

계약 매핑은 다음과 같다.

| step_id | interaction_mode | contract_id |
|---|---|---|
| `extract_account_list_slots` | `agent_internal` | 없음 |
| `fetch_account_list` | `backend_tool_api` | `API-ACCOUNT-LIST` |
| `emit_account_list_result` | `webhook` | `UI-ACCOUNT-LIST-RESULT` |
| `emit_account_list_error` | `webhook` | `UI-COMMON-ERROR` |

#### `wf_balance_inquiry`

잔액 조회는 하나 또는 여러 계좌를 선택하여 Backend의 잔액 조회 결과를 표시하는 읽기 전용 Workflow다.

| state_key | data_type | nullable | 기본값 | 보존 범위 | 역할 |
|---|---|---:|---|---|---|
| `account_hint` | string | true | null | workflow | 사용자 발화에서 추출한 선택적 계좌 힌트 |
| `all_accounts_requested` | boolean | false | false | workflow | 사용자가 전체 계좌 조회를 명시했는지 여부 |
| `account_resolution_outcome` | string | true | null | interaction | Backend가 반환한 계좌 자동 확정 결과 |
| `accounts` | `list[AccountCandidate]` | false | `[]` | interaction | Backend가 검증하여 반환한 계좌 선택 UI 후보 |
| `account_ids` | `list[string]` | false | `[]` | workflow | 잔액을 조회할 하나 이상의 계좌 ID |
| `account_selection_outcome` | string | true | null | interaction | 계좌 선택 UI의 `selected`, `cancelled` 재개 결과 |
| `input_request_id` | string | true | null | interaction | 계좌 선택 요청과 resume 매칭 |
| `balance_results` | `list[BalanceResult]` | false | `[]` | result | Backend가 반환한 계좌별 잔액 결과 |

계좌 결정 규칙은 다음과 같다.

- Backend가 `account_resolution_outcome=resolved`와 검증된 `account_ids`를 반환하면 선택 UI를 생략한다.
- `all_accounts_requested=true`이면 Backend가 조회 가능한 전체 계좌를 검증하여 `account_ids`로 반환한다.
- Backend가 `account_resolution_outcome=selection_required`를 반환하면 `accounts`로 계좌 선택 UI를 표시한다.
- 후보가 없으면 `emit_balance_accounts_empty`가 동일한 계좌 선택 UI에 `accounts=[]`를 전달하여 빈 상태를 표시하고 Workflow를 종료한다. 별도의 UI 계약은 만들지 않는다.
- Backend가 선택값을 검증하여 Agent를 resume하면 `accounts`, `account_resolution_outcome`과 `input_request_id`를 제거한다.
- Agent는 후보 개수를 계산하여 계좌를 자동 확정하거나 resume된 계좌를 다시 검증하지 않는다.
- `account_selection_outcome=selected`이면 `query_balances`로 이동하고, `cancelled`이면 추가 API나 UI Webhook 없이 Workflow를 종료한다.

Workflow Step은 다음과 같이 구성한다.

```text
extract_balance_slots
-> resolve_balance_accounts
-> request_balance_account_selection, emit_balance_accounts_empty 또는 Backend 자동 확정 결과 사용
-> query_balances
-> emit_balance_result
-> END
```

현재 잔액 API의 단일 `account_id` 요청은 복수 계좌 선택과 하나의 Step에 하나의 외부 동작 원칙을 동시에 충족하지 못한다. Agent가 `query_balances` 한 Step에서 계좌별 API를 반복 호출하지 않도록 Backend에 배치 잔액 조회 계약을 요청한다.

```http
POST /api/v1/agent-tools/accounts/balances:query
```

단일 계좌와 복수 계좌 모두 `account_ids` 배열을 사용한다.

```json
{
  "account_ids": [
    "acc_001",
    "acc_002"
  ]
}
```

응답은 Agent State와 같은 이름인 `balance_results` 배열로 통일한다. Agent가 계좌 후보와 잔액을 직접 결합하지 않도록 Backend는 결과 UI에 필요한 마스킹된 계좌 표시 정보도 각 `BalanceResult`에 포함한다.

```text
account_id
bank_name
account_alias
masked_account_number
balance
available_balance
currency
as_of
```

Backend는 모든 계좌의 사용자 소유권과 조회 가능 상태, 중복 ID, 최대 조회 계좌 수와 잔액 조회 Scope를 검증한다. Agent는 잔액을 계산하거나 송금 가능 여부를 판정하지 않는다.

`balance_results`는 금융정보이므로 `sensitive=true`, `retention_scope=result`, `log_policy=exclude`로 관리한다. Workflow Checkpoint에는 결과 전달에 필요한 기간만 저장할 수 있지만 Agent Trace와 일반 로그에는 잔액 원문을 기록하지 않는다.

Route는 다음과 같다.

```text
resolve_balance_accounts
├─ resolved -> query_balances
├─ selection_required -> request_balance_account_selection
├─ no_accounts -> emit_balance_accounts_empty(accounts=[])
└─ backend_error -> emit_balance_error

request_balance_account_selection
├─ selected -> query_balances
└─ cancelled -> END

query_balances
├─ success -> emit_balance_result
└─ error -> emit_balance_error
```

`query_balances`의 Timeout 또는 HTTP `502`, `503`, `504`는 공통 API Adapter가 최대 1회 재시도한다. 재시도 대상이 아니거나 재시도 후에도 실패하면 Agent는 오류 유형별 복구 흐름을 임의로 선택하지 않고 Backend의 오류 코드와 사용자 공개 가능 메시지를 `emit_balance_error`에 전달한 뒤 종료한다. 사용자가 다시 요청하면 최신 계좌 상태로 새 Workflow를 시작한다.

Step State Mapping은 다음과 같다.

| step_id | direction | state_key | contract_field_path |
|---|---|---|---|
| `extract_balance_slots` | `output` | `account_hint` | `agent.extracted.account_hint` |
| `extract_balance_slots` | `output` | `all_accounts_requested` | `agent.extracted.all_accounts_requested` |
| `resolve_balance_accounts` | `input` | `account_hint` | `query.account_hint` |
| `resolve_balance_accounts` | `input` | `all_accounts_requested` | `query.all_accounts_requested` |
| `resolve_balance_accounts` | `output` | `account_resolution_outcome` | `response.data.account_resolution_outcome` |
| `resolve_balance_accounts` | `output` | `accounts` | `response.data.accounts` |
| `resolve_balance_accounts` | `output` | `account_ids` | `response.data.account_ids` |
| `request_balance_account_selection` | `input` | `accounts` | `webhook.metadata.ui.payload.accounts` |
| `request_balance_account_selection` | `output` | `account_selection_outcome` | `resume.value.account_selection_outcome` |
| `request_balance_account_selection` | `output` | `account_ids` | `resume.value.account_ids` |
| `emit_balance_accounts_empty` | `input` | `accounts` | `webhook.metadata.ui.payload.accounts` |
| `query_balances` | `input` | `account_ids` | `request.account_ids` |
| `query_balances` | `output` | `balance_results` | `response.data.balance_results` |
| `emit_balance_result` | `input` | `balance_results` | `webhook.metadata.ui.payload.accounts` |

계약 매핑은 다음과 같다.

| step_id | interaction_mode | contract_id |
|---|---|---|
| `extract_balance_slots` | `agent_internal` | 없음 |
| `resolve_balance_accounts` | `backend_tool_api` | `API-ACCOUNT-LIST` |
| `request_balance_account_selection` | `webhook_then_resume` | `UI-BALANCE-ACCOUNT-SELECTION` |
| `emit_balance_accounts_empty` | `webhook` | `UI-BALANCE-ACCOUNT-SELECTION` |
| `query_balances` | `backend_tool_api` | `API-BALANCE-QUERY` |
| `emit_balance_result` | `webhook` | `UI-BALANCE-RESULT` |
| `emit_balance_error` | `webhook` | `UI-COMMON-ERROR` |

#### `wf_transaction_history`

거래내역 조회는 하나 이상의 계좌와 기간, 선택적 검색 조건으로 첫 페이지를 조회하고 결과 UI를 표시하는 읽기 전용 Workflow다.

| state_key | data_type | nullable | 기본값 | 보존 범위 | 역할 |
|---|---|---:|---|---|---|
| `account_hint` | string | true | null | workflow | 사용자 발화에서 추출한 계좌 힌트 |
| `all_accounts_requested` | boolean | false | false | workflow | 사용자가 전체 계좌 거래내역 조회를 명시했는지 여부 |
| `account_resolution_outcome` | string | true | null | interaction | Backend가 반환한 계좌 자동 확정 결과 |
| `accounts` | `list[AccountCandidate]` | false | `[]` | interaction | Backend가 검증하여 반환한 계좌 선택 UI 후보 |
| `account_ids` | `list[string]` | false | `[]` | workflow | Backend가 검증한 조회 대상 계좌 ID |
| `account_selection_outcome` | string | true | null | interaction | 계좌 선택 UI의 `selected`, `cancelled` 재개 결과 |
| `input_request_id` | string | true | null | interaction | 계좌 또는 기간 입력 요청과 resume 매칭 |
| `start_date` | date | true | null | workflow | 조회 시작일 |
| `end_date` | date | true | null | workflow | 조회 종료일 |
| `period_selection_outcome` | string | true | null | interaction | 기간 선택 UI의 `selected`, `cancelled` 재개 결과 |
| `keyword` | string | true | null | workflow | 선택적 거래 검색어 |
| `transaction_type` | string | true | null | workflow | 선택적 `TransactionType` 거래 유형 필터 |
| `transaction_results` | `list[TransactionItem]` | false | `[]` | result | 첫 페이지 거래내역 |
| `transaction_query_id` | string | true | null | result | 이후 페이지 조회용 Backend Query Context |
| `next_cursor` | string | true | null | result | 다음 페이지 Cursor |

계좌 선택은 `wf_balance_inquiry`와 같은 Backend 자동 확정 규칙을 사용한다. `resolve_transaction_accounts`는 `API-ACCOUNT-LIST`에 `resolve_selection=true`, `account_capability=inquiry`를 Tool 설정값으로 사용하고 `account_hint`, `all_accounts_requested`를 전달한다. Agent는 후보 개수, 계좌 소유권과 조회 권한을 판단하지 않는다.

- `resolved`: Backend가 검증한 `account_ids`로 진행한다.
- `selection_required`: `accounts`로 단일·복수 계좌 선택 UI를 표시한다.
- `no_accounts`: `emit_transaction_accounts_empty`가 같은 계좌 선택 UI에 `accounts=[]`를 전송하고 종료한다.
- 선택 UI의 `selected`는 Backend가 검증한 `account_ids`로 진행하고 `cancelled`는 추가 호출 없이 종료한다.

복수 계좌 거래를 Agent가 계좌별로 조회하고 합치지 않도록 거래내역 Tool API도 `account_ids` 배열을 받는 배치 계약으로 변경한다.

사용자가 조회 기간을 말하지 않으면 Execution Context의 `requested_at`, `timezone`을 기준으로 최근 1개월을 `start_date`, `end_date`에 적용한다. Agent가 호출하는 첫 페이지의 `limit=10`은 사용자 State가 아니라 `query_transactions` Tool 설정값으로 관리한다. 사용자가 기간을 명시하면 Agent가 해당 표현을 날짜로 정규화하고, 기간 표현을 해석할 수 없으면 `request_period_selection`으로 이동한다.

기간 선택 UI의 프리셋은 자연어 입력이 아니라 `last_month` 같은 구조화된 값이다. Frontend는 프리셋 또는 직접 선택한 날짜를 Backend의 일반 입력 API로 보내고, Backend가 Execution Context의 `timezone`, 날짜 순서, 최대 조회 기간과 입력 요청 유효성을 검증한다. Agent에는 프리셋 원문이 아니라 `period_selection_outcome`, 정규화된 `start_date`, `end_date`만 resume한다.

```text
기간 미입력 -> 최근 1개월, 최신순 10건
기간 명시 및 해석 성공 -> 해당 기간, 최신순 10건
기간 명시 및 해석 실패 -> request_period_selection
```

최근 1개월에 거래가 없어도 더 과거로 조회 범위를 자동 확장하지 않는다. `transaction_results=[]`인 정상 결과를 표시하고, 사용자가 기간을 변경하면 Frontend와 Backend가 새 조회 조건을 처리한다.

거래내역이 있는 경우와 없는 경우 모두 `emit_transaction_result`가 같은 `transaction_list` UI 계약을 사용한다. `transaction_results=[]`이면 Frontend가 동일한 UI 안에서 빈 상태를 표시하므로 별도의 `emit_transaction_empty` Step과 빈 결과 전용 UI 계약은 사용하지 않는다.

```json
{
  "account_ids": [
    "acc_001",
    "acc_002"
  ],
  "start_date": "2026-07-01",
  "end_date": "2026-07-14",
  "keyword": null,
  "transaction_type": null,
  "limit": 10
}
```

Backend는 모든 계좌의 소유권, 조회 기간, 검색어, 거래 유형, 페이지 크기를 검증하고 여러 계좌의 거래를 통합하여 `occurred_at` 기준으로 정렬한 뒤 전역 Cursor를 생성한다.

요청 필터와 응답의 `transaction_type`은 같은 Enum을 사용한다.

```text
deposit
withdrawal
transfer
card_payment
atm_withdrawal
fee
interest
```

구체적인 유형에 해당하면 일반 `withdrawal` 또는 `deposit`보다 `card_payment`, `atm_withdrawal`, `fee`, `interest`를 우선한다. `transfer`는 본인 계좌 이체와 타인 계좌 송수신을 포함하는 계좌이체 거래에 사용한다. 이 Enum은 관리시트 `Enum Registry`의 `transaction_type` 그룹에서 관리한다.

거래내역의 대표 표시 문자열은 의미가 모호한 `display_name` 대신 `transaction_title`을 사용한다. `transaction_title`은 Backend가 거래 유형에 따라 가맹점명, 수취인명, 송금인명 또는 거래 설명을 선택하고 필요한 마스킹을 적용하여 만든 UI 표시용 제목이다.

```text
카드 결제 -> 가맹점명
외부 송금 -> 수취인명
외부 입금 -> 송금인명
본인 계좌 이체 -> 대상 계좌 별칭
ATM 출금 -> ATM 출금
수수료 -> 이체 수수료
이자 -> 예금 이자
```

`TransactionItem`에는 다음 필드를 사용한다.

```text
transaction_id
account_id
account_alias
occurred_at
transaction_type
amount
currency
transaction_title
category
```

`transaction_results`는 금융정보이므로 `sensitive=true`, `retention_scope=result`, `log_policy=exclude`로 관리한다. 거래 금액과 제목 원문을 Agent Trace와 일반 로그에 기록하지 않는다.

Agent는 최근 1개월 범위의 최신순 10건을 기본 첫 페이지로 조회하고 결과 Webhook을 보낸 뒤 Workflow를 종료한다. 단순 목록 페이지 이동에는 Agent의 판단이 필요하지 않으므로 이후 페이지는 Frontend와 Backend가 직접 처리한다.

```text
Agent -> Backend Tool API로 첫 페이지 조회
Agent -> transaction_query_id, next_cursor와 첫 페이지 결과 Webhook
Agent -> END
Frontend -> Backend 일반 API로 다음 페이지 조회
```

Frontend용 페이지 조회 예시는 다음과 같다.

```http
GET /api/v1/transactions/queries/{transaction_query_id}?cursor={next_cursor}
```

Backend는 `transaction_query_id`에 인증된 사용자, 계좌 범위, 기간, 검색 조건, 페이지 크기와 만료시각을 연결한다. Frontend의 다음 페이지 요청에서는 Query Context 소유권, 만료와 Cursor 유효성을 검사하고 최초 조회 조건을 변경할 수 없게 한다.

Workflow Step은 다음과 같이 구성한다.

```text
extract_transaction_slots
-> resolve_transaction_accounts
-> request_transaction_account_selection, emit_transaction_accounts_empty 또는 Backend 자동 확정 결과 사용
-> check_transaction_period
-> 기간 해석 실패 시 request_period_selection, 기간 미입력 시 최근 1개월 기본 적용
-> query_transactions
-> emit_transaction_result
-> END
```

`query_transactions` 응답에는 `total_amount`를 포함하지 않는다. 기간 합계는 별도 `wf_period_amount_summary`와 거래 합계 API가 담당한다.

계좌 관련 Route는 다음과 같다.

```text
resolve_transaction_accounts
├─ resolved -> check_transaction_period
├─ selection_required -> request_transaction_account_selection
├─ no_accounts -> emit_transaction_accounts_empty(accounts=[])
└─ backend_error -> emit_transaction_error

request_transaction_account_selection
├─ selected -> check_transaction_period
└─ cancelled -> END

check_transaction_period
├─ normalized_or_defaulted -> query_transactions
└─ interpretation_failed -> request_period_selection

request_period_selection
├─ selected -> query_transactions
└─ cancelled -> END

query_transactions
├─ success -> emit_transaction_result
└─ error -> emit_transaction_error
```

`query_transactions`의 성공 응답은 `transaction_results`가 빈 배열이어도 동일한 성공 Route를 사용한다. Timeout 또는 HTTP `502`, `503`, `504`는 공통 API Adapter가 최대 1회 재시도한다. 재시도 대상이 아니거나 재시도 후에도 실패하면 Agent는 오류 유형별 복구를 임의로 판단하지 않고 Backend의 사용자 공개 가능 오류를 `emit_transaction_error`로 전달한 뒤 종료한다.

Step State Mapping은 다음과 같다.

| step_id | direction | state_key | contract_field_path |
|---|---|---|---|
| `extract_transaction_slots` | `output` | `account_hint` | `agent.extracted.account_hint` |
| `extract_transaction_slots` | `output` | `all_accounts_requested` | `agent.extracted.all_accounts_requested` |
| `extract_transaction_slots` | `output` | `start_date` | `agent.extracted.start_date` |
| `extract_transaction_slots` | `output` | `end_date` | `agent.extracted.end_date` |
| `extract_transaction_slots` | `output` | `keyword` | `agent.extracted.keyword` |
| `extract_transaction_slots` | `output` | `transaction_type` | `agent.extracted.transaction_type` |
| `resolve_transaction_accounts` | `input` | `account_hint` | `query.account_hint` |
| `resolve_transaction_accounts` | `input` | `all_accounts_requested` | `query.all_accounts_requested` |
| `resolve_transaction_accounts` | `output` | `account_resolution_outcome` | `response.data.account_resolution_outcome` |
| `resolve_transaction_accounts` | `output` | `accounts` | `response.data.accounts` |
| `resolve_transaction_accounts` | `output` | `account_ids` | `response.data.account_ids` |
| `request_transaction_account_selection` | `input` | `accounts` | `webhook.metadata.ui.payload.accounts` |
| `request_transaction_account_selection` | `output` | `account_selection_outcome` | `resume.value.account_selection_outcome` |
| `request_transaction_account_selection` | `output` | `account_ids` | `resume.value.account_ids` |
| `emit_transaction_accounts_empty` | `input` | `accounts` | `webhook.metadata.ui.payload.accounts` |
| `request_period_selection` | `output` | `start_date` | `resume.value.start_date` |
| `request_period_selection` | `output` | `end_date` | `resume.value.end_date` |
| `request_period_selection` | `output` | `period_selection_outcome` | `resume.value.period_selection_outcome` |
| `query_transactions` | `input` | `account_ids` | `request.account_ids` |
| `query_transactions` | `input` | `start_date` | `request.start_date` |
| `query_transactions` | `input` | `end_date` | `request.end_date` |
| `query_transactions` | `input` | `keyword` | `request.keyword` |
| `query_transactions` | `input` | `transaction_type` | `request.transaction_type` |
| `query_transactions` | `output` | `transaction_results` | `response.data.transaction_results` |
| `query_transactions` | `output` | `transaction_query_id` | `response.data.transaction_query_id` |
| `query_transactions` | `output` | `next_cursor` | `response.data.next_cursor` |
| `emit_transaction_result` | `input` | `transaction_results` | `webhook.metadata.ui.payload.transactions` |

계약 매핑은 다음과 같다.

| step_id | interaction_mode | contract_id |
|---|---|---|
| `extract_transaction_slots` | `agent_internal` | 없음 |
| `resolve_transaction_accounts` | `backend_tool_api` | `API-ACCOUNT-LIST` |
| `request_transaction_account_selection` | `webhook_then_resume` | `UI-TRANSACTION-ACCOUNT-SELECTION` |
| `emit_transaction_accounts_empty` | `webhook` | `UI-TRANSACTION-ACCOUNT-SELECTION` |
| `request_period_selection` | `webhook_then_resume` | `UI-PERIOD-SELECTION` |
| `query_transactions` | `backend_tool_api` | `API-TRANSACTION-QUERY` |
| `emit_transaction_result` | `webhook` | `UI-TRANSACTION-LIST` |
| `emit_transaction_error` | `webhook` | `UI-COMMON-ERROR` |

#### `wf_period_amount_summary`

기간 합계 조회는 하나 이상의 계좌와 기간, 집계 유형으로 Backend의 집계 결과를 조회하는 읽기 전용 Workflow다. Agent는 전체 거래내역을 받거나 직접 합산하지 않는다.

| state_key | data_type | nullable | 기본값 | 보존 범위 | 역할 |
|---|---|---:|---|---|---|
| `account_hint` | string | true | null | workflow | 선택적 계좌 힌트 |
| `all_accounts_requested` | boolean | false | true | workflow | 계좌 힌트가 없을 때 전체 계좌 집계 여부 |
| `account_resolution_outcome` | string | true | null | interaction | Backend가 반환한 계좌 자동 확정 결과 |
| `accounts` | `list[AccountCandidate]` | false | `[]` | interaction | Backend가 검증하여 반환한 계좌 선택 UI 후보 |
| `account_ids` | `list[string]` | false | `[]` | workflow | Backend가 검증한 집계 대상 계좌 |
| `account_selection_outcome` | string | true | null | interaction | 계좌 선택 UI의 `selected`, `cancelled` 재개 결과 |
| `input_request_id` | string | true | null | interaction | 계좌·기간·집계 유형 입력 요청과 resume 매칭 |
| `start_date` | date | true | null | workflow | 집계 시작일 |
| `end_date` | date | true | null | workflow | 집계 종료일 |
| `period_selection_outcome` | string | true | null | interaction | 기간 선택 UI의 `selected`, `cancelled` 재개 결과 |
| `summary_type` | string | true | null | workflow | `spending` 또는 `income` |
| `summary_type_selection_outcome` | string | true | null | interaction | 합계 유형 선택 UI의 `selected`, `cancelled` 재개 결과 |
| `keyword` | string | true | null | workflow | 선택적 가맹점·상대방 검색어 |
| `summary_result` | `AmountSummary` | true | null | result | Backend 집계 결과 |

`spending`, `income`은 개별 원장 거래 유형이 아니라 집계 목적이므로 `transaction_type` 대신 `summary_type`을 사용한다. Backend는 원장 거래를 지출과 입금으로 분류하며 본인 계좌 간 이체처럼 소비나 소득이 아닌 거래를 집계에서 제외한다. Agent는 출금이면 지출, 입금이면 소득이라고 임의로 판정하지 않는다.

계좌 힌트가 없으면 `all_accounts_requested=true`를 적용하여 모든 조회 가능 계좌를 기본 집계 대상으로 한다. `resolve_summary_accounts`는 `API-ACCOUNT-LIST`에 `resolve_selection=true`, `account_capability=inquiry`를 Tool 설정값으로 사용한다. Backend가 전체 계좌 또는 단일 계좌를 검증·확정하고, 여러 후보가 있어 사용자 선택이 필요할 때만 `accounts`를 반환한다. Agent는 후보 개수, 계좌 소유권과 조회 권한을 판단하지 않는다.

- `resolved`: Backend가 검증한 `account_ids`로 진행한다.
- `selection_required`: `request_summary_account_selection`에서 단일·복수 계좌를 선택받는다.
- `no_accounts`: `emit_summary_accounts_empty`가 같은 계좌 선택 UI에 `accounts=[]`를 전송하고 종료한다.
- 계좌 선택 UI의 `selected`는 Backend가 검증한 `account_ids`로 진행하고 `cancelled`는 추가 호출 없이 종료한다.

`summary_type`을 발화에서 확정할 수 없으면 Agent가 기본값을 추측하지 않고 `UI-SUMMARY-TYPE-SELECTION`의 `option_select`로 `spending` 또는 `income`을 선택받는다. Frontend가 선택값을 Backend에 보내면 Backend가 `input_request_id`와 Enum을 검증하고 `summary_type_selection_outcome`, `summary_type`으로 Agent를 resume한다. `selected`이면 합계 조회를 계속하고 `cancelled`이면 추가 호출 없이 종료한다.

기간 규칙은 `wf_transaction_history`와 동일하게 사용한다. 사용자가 기간을 말하지 않으면 Execution Context의 `requested_at`, `timezone`을 기준으로 최근 1개월을 `start_date`, `end_date`에 적용한다. `이번 달`, `지난달`, `최근 한 달`처럼 명시된 기간은 해당 의미대로 정규화하며, 기간 표현을 안전하게 해석하지 못한 경우에만 `request_period_selection`으로 이동한다.

```text
기간 미입력 -> 최근 1개월
"이번 달" 명시 -> 이번 달 1일 ~ 요청일
"지난달" 명시 -> 지난달 1일 ~ 말일
기간 해석 실패 -> request_period_selection
```

기간 선택 UI의 프리셋 또는 직접 입력 날짜는 Backend가 `timezone`, 날짜 순서, 최대 조회 기간과 입력 요청 유효성을 검증한다. Agent에는 프리셋 원문이 아니라 `period_selection_outcome`, 정규화된 `start_date`, `end_date`만 resume한다.

Backend 합계 API는 복수 계좌를 `account_ids` 배열로 받는다.

```json
{
  "account_ids": [
    "acc_001",
    "acc_002"
  ],
  "start_date": "2026-07-01",
  "end_date": "2026-07-14",
  "summary_type": "spending",
  "keyword": null
}
```

Backend는 계좌 소유권, 기간, 집계 유형과 검색어를 검증하고 거래 분류, 본인 계좌 간 이체 제외, 통화별 집계, 합계와 거래 건수 계산을 수행한다. 결과는 `summary_result`에 저장한다.

```json
{
  "summary_type": "spending",
  "total_amount": 375000,
  "transaction_count": 18,
  "currency": "KRW",
  "start_date": "2026-07-01",
  "end_date": "2026-07-14"
}
```

`summary_result`는 금융정보이므로 `sensitive=true`, `retention_scope=result`, `log_policy=exclude`로 관리한다. 거래가 없으면 오류가 아니라 `total_amount=0`, `transaction_count=0`인 정상 결과로 처리한다.

기존 `fetch_transactions`, `sum_transactions` Step은 제거하고 Backend 집계 API를 한 번 호출하는 `query_transaction_summary`로 대체한다.

```text
extract_amount_summary_slots
-> resolve_summary_accounts
-> request_summary_account_selection, emit_summary_accounts_empty 또는 Backend 자동 확정 결과 사용
-> check_summary_period
-> 필요하면 request_period_selection
-> check_summary_type
-> 필요하면 request_summary_type
-> query_transaction_summary
-> emit_amount_summary
-> END
```

Route는 다음과 같다.

```text
resolve_summary_accounts
├─ resolved -> check_summary_period
├─ selection_required -> request_summary_account_selection
├─ no_accounts -> emit_summary_accounts_empty(accounts=[])
└─ backend_error -> emit_amount_summary_error

request_summary_account_selection
├─ selected -> check_summary_period
└─ cancelled -> END

check_summary_period
├─ normalized_or_defaulted -> check_summary_type
└─ interpretation_failed -> request_period_selection

request_period_selection
├─ selected -> check_summary_type
└─ cancelled -> END

check_summary_type
├─ resolved -> query_transaction_summary
└─ selection_required -> request_summary_type

request_summary_type
├─ selected -> query_transaction_summary
└─ cancelled -> END

query_transaction_summary
├─ success -> emit_amount_summary
└─ error -> emit_amount_summary_error
```

`summary_result.total_amount=0`, `transaction_count=0`도 정상 성공 Route를 사용한다. Timeout 또는 HTTP `502`, `503`, `504`는 공통 API Adapter가 최대 1회 재시도한다. 재시도 대상이 아니거나 재시도 후에도 실패하면 Agent는 오류 유형별 복구를 임의로 판단하지 않고 Backend의 사용자 공개 가능 오류를 `emit_amount_summary_error`로 전달한 뒤 종료한다.

Step State Mapping은 다음과 같다.

| step_id | direction | state_key | contract_field_path |
|---|---|---|---|
| `extract_amount_summary_slots` | `output` | `account_hint` | `agent.extracted.account_hint` |
| `extract_amount_summary_slots` | `output` | `all_accounts_requested` | `agent.extracted.all_accounts_requested` |
| `extract_amount_summary_slots` | `output` | `start_date` | `agent.extracted.start_date` |
| `extract_amount_summary_slots` | `output` | `end_date` | `agent.extracted.end_date` |
| `extract_amount_summary_slots` | `output` | `summary_type` | `agent.extracted.summary_type` |
| `extract_amount_summary_slots` | `output` | `keyword` | `agent.extracted.keyword` |
| `resolve_summary_accounts` | `input` | `account_hint` | `query.account_hint` |
| `resolve_summary_accounts` | `input` | `all_accounts_requested` | `query.all_accounts_requested` |
| `resolve_summary_accounts` | `output` | `account_resolution_outcome` | `response.data.account_resolution_outcome` |
| `resolve_summary_accounts` | `output` | `accounts` | `response.data.accounts` |
| `resolve_summary_accounts` | `output` | `account_ids` | `response.data.account_ids` |
| `request_summary_account_selection` | `input` | `accounts` | `webhook.metadata.ui.payload.accounts` |
| `request_summary_account_selection` | `output` | `account_selection_outcome` | `resume.value.account_selection_outcome` |
| `request_summary_account_selection` | `output` | `account_ids` | `resume.value.account_ids` |
| `emit_summary_accounts_empty` | `input` | `accounts` | `webhook.metadata.ui.payload.accounts` |
| `request_period_selection` | `output` | `start_date` | `resume.value.start_date` |
| `request_period_selection` | `output` | `end_date` | `resume.value.end_date` |
| `request_period_selection` | `output` | `period_selection_outcome` | `resume.value.period_selection_outcome` |
| `request_summary_type` | `output` | `summary_type` | `resume.value.summary_type` |
| `request_summary_type` | `output` | `summary_type_selection_outcome` | `resume.value.summary_type_selection_outcome` |
| `query_transaction_summary` | `input` | `account_ids` | `request.account_ids` |
| `query_transaction_summary` | `input` | `start_date` | `request.start_date` |
| `query_transaction_summary` | `input` | `end_date` | `request.end_date` |
| `query_transaction_summary` | `input` | `summary_type` | `request.summary_type` |
| `query_transaction_summary` | `input` | `keyword` | `request.keyword` |
| `query_transaction_summary` | `output` | `summary_result` | `response.data.summary_result` |
| `emit_amount_summary` | `input` | `account_ids` | `webhook.metadata.ui.payload.account_ids` |
| `emit_amount_summary` | `input` | `keyword` | `webhook.metadata.ui.payload.keyword` |
| `emit_amount_summary` | `input` | `summary_result` | `webhook.metadata.ui.payload.start_date` |
| `emit_amount_summary` | `input` | `summary_result` | `webhook.metadata.ui.payload.end_date` |
| `emit_amount_summary` | `input` | `summary_result` | `webhook.metadata.ui.payload.summary_type` |
| `emit_amount_summary` | `input` | `summary_result` | `webhook.metadata.ui.payload.total_amount` |
| `emit_amount_summary` | `input` | `summary_result` | `webhook.metadata.ui.payload.transaction_count` |
| `emit_amount_summary` | `input` | `summary_result` | `webhook.metadata.ui.payload.currency` |

계약 매핑은 다음과 같다.

| step_id | interaction_mode | contract_id |
|---|---|---|
| `extract_amount_summary_slots` | `agent_internal` | 없음 |
| `request_period_selection` | `webhook_then_resume` | `UI-PERIOD-SELECTION` |
| `resolve_summary_accounts` | `backend_tool_api` | `API-ACCOUNT-LIST` |
| `request_summary_account_selection` | `webhook_then_resume` | `UI-SUMMARY-ACCOUNT-SELECTION` |
| `emit_summary_accounts_empty` | `webhook` | `UI-SUMMARY-ACCOUNT-SELECTION` |
| `request_summary_type` | `webhook_then_resume` | `UI-SUMMARY-TYPE-SELECTION` |
| `query_transaction_summary` | `backend_tool_api` | `API-TRANSACTION-SUMMARY` |
| `emit_amount_summary` | `webhook` | `UI-AMOUNT-SUMMARY` |
| `emit_amount_summary_error` | `webhook` | `UI-COMMON-ERROR` |

#### `wf_set_default_account`

기본 출금 계좌 변경은 대상 계좌를 선택한 뒤 Backend가 변경 가능 여부와 현재 설정을 검증하고, 사용자 승인을 받은 후 실제 설정을 변경하는 쓰기 Workflow다. Agent는 현재 기본계좌를 직접 조회해 비교하거나 설정 테이블을 변경하지 않는다.

| state_key | data_type | nullable | 기본값 | 역할 |
|---|---|---:|---|---|
| `account_hint` | string | true | null | 발화에서 추출한 대상 계좌 힌트 |
| `account_resolution_outcome` | string | true | null | Backend가 반환한 계좌 자동 확정 결과 |
| `accounts` | `list[AccountCandidate]` | false | `[]` | Backend가 검증하여 반환한 대상 계좌 선택 UI 후보 |
| `account_id` | string | true | null | 새 기본 출금 계좌로 설정할 계좌 ID |
| `account_selection_outcome` | string | true | null | 계좌 선택 UI의 `selected`, `cancelled` 재개 결과 |
| `input_request_id` | string | true | null | 계좌 선택 입력 요청 식별자 |
| `confirmation_id` | string | true | null | Backend가 발급한 변경 승인 식별자 |
| `confirmation_view` | `ConfirmationView` | true | null | 승인 대기 중에만 보존하는 표시 데이터 |
| `approval_outcome` | string | true | null | Backend가 검증한 `approved`, `change_requested`, `cancelled` 승인 결과 |
| `correction_view` | `SettingCorrectionView` | true | null | Prepare 업무 결과의 수정 가능 항목 표시 데이터 |
| `prepare_attempt` | integer | false | `0` | Prepare 멱등성 키 생성을 위한 시도 번호 |
| `completed_at` | datetime | true | null | 기본 출금 계좌 변경 완료 시각 |

이 Workflow는 단일 설정 대상만 다루므로 `account_ids`나 `new_default_account_id`를 추가하지 않고 공통 단일 대상 필드인 `account_id`를 사용한다. 현재 기본계좌는 Backend가 판단하므로 Agent State에 `current_default_account_id`를 두지 않는다.

`resolve_default_account`는 `API-ACCOUNT-LIST`에 `resolve_selection=true`, `account_capability=settings`를 Tool 설정값으로 사용한다. `selection_mode`는 추가하지 않고 모든 자동 확정 응답에서 기존 `account_ids` 배열 계약을 유지한다.

Backend가 `account_resolution_outcome=resolved`를 반환하면 Agent는 `account_ids`가 정확히 한 개인지 구조적으로 확인하고 해당 값을 `account_id`에 저장한다. 이는 후보 선택이나 금융 검증이 아니라 단일 대상 Workflow의 응답 Schema 확인이다. `resolved`인데 배열이 비어 있거나 두 개 이상이면 계약 오류로 처리하며 임의로 첫 번째 후보를 선택하지 않는다.

여러 계좌와 일치하면 Backend가 `selection_required`와 `accounts`를 반환하고 `UI-DEFAULT-ACCOUNT-SELECTION`을 표시한다. 사용자 선택 resume도 `account_ids` 배열을 사용하며 Backend가 소유권과 선택 가능 여부를 검증한다. Agent는 배열이 정확히 한 개인지 확인한 뒤 `account_id`에 저장한다. `no_accounts`이면 같은 계좌 선택 UI에 `accounts=[]`를 전송하고 종료한다.

Prepare 호출 직전 별도 Agent 내부 Step인 `start_default_account_prepare`가 `prepare_attempt`를 증가시키고 Checkpoint를 저장한다. 멱등성 키는 다음 규칙으로 생성한다.

```text
default_account_prepare:{execution_context_id}:{prepare_attempt}
```

Prepare 요청의 업무 데이터는 대상 계좌 ID 하나다.

```json
{
  "account_id": "acc_002"
}
```

Backend는 다음 항목을 검증한다.

- 인증된 사용자가 소유한 계좌인지
- 계좌가 활성 상태인지
- 출금 계좌로 사용할 수 있는 상품인지
- 이미 기본 출금 계좌로 설정되어 있지 않은지

대상 계좌가 이미 기본 출금 계좌이면 `outcome=unchanged`를 반환한다. 이 결과는 실패나 재시도 대상이 아니며 Confirmation을 만들지 않고 `emit_default_account_unchanged` Step에서 공통 `setting_result` UI를 `outcome=unchanged`로 전송한 뒤 종료한다. 변경 완료 결과도 같은 `setting_result` UI를 `outcome=completed`로 사용한다. Workflow Step은 변경 실행 전 종료와 실행 완료를 구분하기 위해 별도로 유지하지만, UI 계약은 추가하지 않는다.

변경이 필요한 경우 Backend는 `outcome=ready_for_confirmation`, `confirmation_id`, 만료시각과 화면 표시 데이터를 반환한다. 화면 표시 데이터는 Backend가 원장 정보를 마스킹해 생성하며 현재 계좌와 변경 대상 계좌를 명확히 구분한다.

```json
{
  "confirmation_id": "confirm_default_123",
  "confirmation_view": {
    "current_default_account": {
      "account_id": "acc_001",
      "bank_name": "신한은행",
      "account_alias": "생활비",
      "masked_account_number": "110-***-123456"
    },
    "new_default_account": {
      "account_id": "acc_002",
      "bank_name": "국민은행",
      "account_alias": "급여",
      "masked_account_number": "123-***-456789"
    },
    "expires_at": "2026-07-14T10:05:00+09:00"
  }
}
```

Agent는 `confirmation_id`와 임시 `confirmation_view`를 저장한 뒤 승인 요청 Webhook을 전송하고 중단한다. Prepare API 호출과 승인 Webhook 전송은 서로 다른 Step으로 관리한다. Backend는 사용자와 Confirmation을 검증하고 승인 화면의 `approve`, `modify`, `cancel` 결정을 각각 `approved`, `change_requested`, `cancelled`의 `approval_outcome`으로 Agent에 전달한다.

- `approved`: `confirmation_view`와 `approval_outcome`을 제거하고 승인된 `confirmation_id`만 유지한 채 Execute로 이동한다.
- `change_requested`: Backend가 기존 Confirmation을 무효화한 뒤 Agent를 재개한다. Agent는 `reset_default_account_target`에서 기존 대상·후보·승인 관련 임시 State를 제거하고 최신 계좌 확인 단계로 돌아간다.
- `cancelled`: Backend가 Confirmation을 취소 처리한 뒤 Agent를 재개한다. Agent는 승인 관련 임시 State를 제거하고 추가 Tool API나 UI Webhook 없이 Workflow를 종료한다.

기본계좌 변경에서 수정 가능한 대상은 계좌 하나뿐이므로 Agent 재개 Payload와 State에 별도 `change_target`을 추가하지 않는다.

Execute 멱등성 키는 Confirmation당 하나로 고정한다.

```text
default_account_execute:{confirmation_id}
```

Execute 요청은 `confirmation_id`만 전달한다. Backend는 유효하고 승인된 Confirmation인지 다시 확인하고, 한 사용자에게 기본 출금 계좌가 하나만 존재하도록 트랜잭션 안에서 기존 기본계좌 해제와 새 기본계좌 설정을 함께 처리한다. 같은 Confirmation의 중복 실행은 Backend가 차단하거나 최초 실행 결과를 재응답한다.

Execute 시점에 대상 계좌가 더 이상 기본 출금 계좌로 적합하지 않으면 Backend는 `outcome=correction_required`와 `allowed_change_targets=["account"]`를 반환하고 기존 Confirmation을 재사용할 수 없게 처리한다. Agent는 `reset_default_account_target`을 거쳐 최신 계좌 목록을 다시 조회한다. 설정 변경이 차단되면 종료한다. Timeout 또는 HTTP `502`, `503`, `504`는 같은 Execute 멱등성 키와 Body로 최대 1회 재시도하고, 다시 실패하면 `emit_default_account_error`로 종료한다.

`reset_default_account_target`은 API를 호출하지 않는 Agent 내부 Step이다. `account_hint`, `account_resolution_outcome`, `accounts`, `account_id`, `account_selection_outcome`, `input_request_id`, `confirmation_id`, `confirmation_view`, `approval_outcome`을 초기화하고 `prepare_attempt`와 `correction_view`는 유지한다. 이후 `resolve_default_account`를 계좌 힌트 없이 다시 호출하여 최신 계좌 상태와 후보를 받는다. `correction_view`가 있으면 다음 계좌 선택 UI에 수정 사유를 함께 표시한다. 사용자가 새 계좌를 확정한 뒤 `start_default_account_prepare`에서 `correction_view`를 제거하고 `prepare_attempt`를 증가시키므로 새로운 Prepare는 새 멱등성 키를 사용한다.

이 설정 변경에는 별도 추가 인증을 요구하지 않으므로 `auth_context_id`, `auth_request_view`, `auth_attempt`는 사용하지 않는다. 향후 보안 정책이 바뀌면 공통 인증 흐름을 별도 계약 버전으로 연결한다.

Workflow Step은 다음과 같이 구성한다.

```text
extract_default_account_slots
-> resolve_default_account
-> request_default_account_selection, emit_default_account_selection_empty 또는 Backend 자동 확정 결과 사용
-> start_default_account_prepare
-> prepare_default_account_change
-> 이미 기본계좌이면 emit_default_account_unchanged -> END
-> 계좌 수정이 필요하면 reset_default_account_target -> resolve_default_account
-> 설정 변경이 차단되면 emit_default_account_blocked -> END
-> request_default_account_approval
-> interrupt
-> approved이면 execute_default_account_change
-> change_requested이면 reset_default_account_target -> resolve_default_account
-> cancelled이면 추가 Webhook 없이 END
-> completed이면 emit_default_account_result -> END
-> correction_required이면 reset_default_account_target -> resolve_default_account
-> blocked이면 emit_default_account_blocked -> END
```

Step State Mapping은 다음과 같다.

| step_id | direction | state_key | contract_field_path |
|---|---|---|---|
| `extract_default_account_slots` | `output` | `account_hint` | `agent.extracted.account_hint` |
| `resolve_default_account` | `input` | `account_hint` | `query.account_hint` |
| `resolve_default_account` | `output` | `account_resolution_outcome` | `response.data.account_resolution_outcome` |
| `resolve_default_account` | `output` | `accounts` | `response.data.accounts` |
| `resolve_default_account` | `output` | `account_id` | `response.data.account_ids[0]` |
| `request_default_account_selection` | `input` | `accounts` | `webhook.metadata.ui.payload.accounts` |
| `request_default_account_selection` | `input` | `correction_view` | `webhook.metadata.ui.payload.correction_view` |
| `request_default_account_selection` | `output` | `account_selection_outcome` | `resume.value.account_selection_outcome` |
| `request_default_account_selection` | `output` | `account_id` | `resume.value.account_ids[0]` |
| `emit_default_account_selection_empty` | `input` | `accounts` | `webhook.metadata.ui.payload.accounts` |
| `start_default_account_prepare` | `output` | `prepare_attempt` | `agent.state.prepare_attempt` |
| `start_default_account_prepare` | `output` | `correction_view` | `agent.state.correction_view=null` |
| `prepare_default_account_change` | `input` | `account_id` | `request.account_id` |
| `prepare_default_account_change` | `input` | `prepare_attempt` | `header.Idempotency-Key` |
| `prepare_default_account_change` | `output` | `confirmation_id` | `response.data.confirmation_id` |
| `prepare_default_account_change` | `output` | `confirmation_view` | `response.data.confirmation_view` |
| `prepare_default_account_change` | `output` | `correction_view` | `response.data.correction_view` |
| `request_default_account_approval` | `input` | `confirmation_id` | `webhook.interaction.confirmation_id` |
| `request_default_account_approval` | `input` | `confirmation_view` | `webhook.metadata.ui.payload` |
| `request_default_account_approval` | `output` | `approval_outcome` | `resume.value.approval_outcome` |
| `reset_default_account_target` | `output` | `account_hint` | `agent.state.account_hint=null` |
| `reset_default_account_target` | `output` | `account_resolution_outcome` | `agent.state.account_resolution_outcome=null` |
| `reset_default_account_target` | `output` | `accounts` | `agent.state.accounts=[]` |
| `reset_default_account_target` | `output` | `account_id` | `agent.state.account_id=null` |
| `reset_default_account_target` | `output` | `account_selection_outcome` | `agent.state.account_selection_outcome=null` |
| `reset_default_account_target` | `output` | `input_request_id` | `agent.state.input_request_id=null` |
| `reset_default_account_target` | `output` | `confirmation_id` | `agent.state.confirmation_id=null` |
| `reset_default_account_target` | `output` | `confirmation_view` | `agent.state.confirmation_view=null` |
| `reset_default_account_target` | `output` | `approval_outcome` | `agent.state.approval_outcome=null` |
| `execute_default_account_change` | `input` | `confirmation_id` | `request.confirmation_id` |
| `execute_default_account_change` | `output` | `account_id` | `response.data.account_id` |
| `execute_default_account_change` | `output` | `completed_at` | `response.data.completed_at` |
| `execute_default_account_change` | `output` | `correction_view` | `response.data.correction_view` |
| `emit_default_account_unchanged` | `input` | `account_id` | `webhook.metadata.ui.payload.account.account_id` |
| `emit_default_account_result` | `input` | `account_id` | `webhook.metadata.ui.payload.account.account_id` |

계약 매핑은 다음과 같다.

| step_id | interaction_mode | contract_id |
|---|---|---|
| `extract_default_account_slots` | `agent_internal` | 없음 |
| `resolve_default_account` | `backend_tool_api` | `API-ACCOUNT-LIST` |
| `request_default_account_selection` | `webhook_then_resume` | `UI-DEFAULT-ACCOUNT-SELECTION` |
| `emit_default_account_selection_empty` | `webhook` | `UI-DEFAULT-ACCOUNT-SELECTION` |
| `start_default_account_prepare` | `agent_internal` | 없음 |
| `prepare_default_account_change` | `backend_tool_api` | `API-DEFAULT-ACCOUNT-PREPARE` |
| `emit_default_account_unchanged` | `webhook` | `UI-DEFAULT-ACCOUNT-RESULT` |
| `emit_default_account_blocked` | `webhook` | `UI-SETTING-BLOCKED` |
| `request_default_account_approval` | `webhook_then_resume` | `UI-DEFAULT-ACCOUNT-CONFIRMATION` |
| `reset_default_account_target` | `agent_internal` | 없음 |
| `execute_default_account_change` | `backend_tool_api` | `API-DEFAULT-ACCOUNT-EXECUTE` |
| `emit_default_account_result` | `webhook` | `UI-DEFAULT-ACCOUNT-RESULT` |
| `emit_default_account_error` | `webhook` | `UI-COMMON-ERROR` |

#### `wf_set_account_alias`

계좌 별칭 변경은 대상 계좌와 새 별칭을 확정한 뒤 Backend가 변경 가능 여부를 검증하고, 사용자 승인을 받은 후 실제 별칭을 변경하는 쓰기 Workflow다. Agent는 계좌 테이블을 직접 조회하거나 별칭을 직접 변경하지 않는다.

| state_key | data_type | nullable | 기본값 | 역할 |
|---|---|---:|---|---|
| `account_hint` | string | true | null | 발화에서 추출한 대상 계좌 힌트 |
| `account_resolution_outcome` | string | true | null | Backend가 반환한 계좌 자동 확정 결과 |
| `accounts` | `list[AccountCandidate]` | false | `[]` | Backend가 검증하여 반환한 대상 계좌 선택 UI 후보 |
| `account_id` | string | true | null | 별칭을 변경할 계좌 ID |
| `account_selection_outcome` | string | true | null | 계좌 선택 UI의 `selected`, `cancelled` 재개 결과 |
| `alias` | string | true | null | 새로 설정할 계좌 별칭 |
| `alias_input_outcome` | string | true | null | 별칭 입력 UI의 `submitted`, `cancelled` 재개 결과 |
| `input_request_id` | string | true | null | 계좌 또는 별칭 입력 요청 식별자 |
| `confirmation_id` | string | true | null | Backend가 발급한 변경 승인 식별자 |
| `confirmation_view` | `ConfirmationView` | true | null | 승인 대기 중에만 보존하는 표시 데이터 |
| `approval_outcome` | string | true | null | Backend가 검증한 `approved`, `change_requested`, `cancelled` 승인 결과 |
| `change_target` | string | true | null | `account`, `alias` 중 사용자가 수정할 대상 |
| `correction_view` | `SettingCorrectionView` | true | null | Prepare·Execute 업무 결과의 수정 가능 항목 표시 데이터 |
| `prepare_attempt` | integer | false | `0` | Prepare 멱등성 키 생성을 위한 시도 번호 |
| `completed_at` | datetime | true | null | 계좌 별칭 변경 완료 시각 |

Agent State와 Prepare 요청에는 `account_label`과 `current_alias`를 두지 않는다. 변경 업무에 필요한 값은 대상 계좌를 참조하는 `account_id`와 적용할 값인 `alias`뿐이다.

별칭 변경 의도가 확정되면 `alias`가 없어도 Workflow에 진입할 수 있다. 다만 `prepare_account_alias_change` 호출 전에는 `account_id`와 `alias`가 모두 존재해야 한다.

```text
Workflow 진입 조건
- 계좌 별칭 변경 의도가 확정됨

Prepare 호출 조건
- account_id가 존재함
- alias가 존재함
- Backend의 사용자 입력 검증을 통과함
```

예를 들어 “급여 계좌 별명 바꿔줘”는 `wf_set_account_alias`에 진입한 후 `request_account_alias_input`으로 새 별칭을 입력받는다. “급여 계좌 별명을 월급 통장으로 바꿔줘”처럼 대상과 새 별칭이 모두 확정되면 입력 요청을 생략한다.

`resolve_account_alias_target`은 `API-ACCOUNT-LIST`에 `resolve_selection=true`, `account_capability=settings`를 Tool 설정값으로 사용한다. 기본계좌 변경과 동일하게 `selection_mode`를 추가하지 않고 자동 확정 응답과 사용자 선택 resume 모두 `account_ids` 배열 계약을 유지한다.

Backend가 `account_resolution_outcome=resolved`를 반환하면 Agent는 `account_ids`가 정확히 한 개인지 구조적으로 확인하고 해당 값을 `account_id`에 저장한다. 배열이 비어 있거나 두 개 이상이면 임의로 첫 번째 값을 선택하지 않고 계약 오류로 처리한다. 여러 계좌와 일치하면 `selection_required`와 `accounts`를 받아 `UI-ACCOUNT-ALIAS-SELECTION`을 표시하고, `no_accounts`이면 같은 UI에 `accounts=[]`를 전송하고 종료한다.

새 별칭이 없으면 `UI-ACCOUNT-ALIAS-INPUT`을 표시한다. Frontend가 보낸 계좌 선택과 `alias`는 Backend가 사용자, 계좌 소유권과 문자열 형식을 검증한 뒤 Agent를 재개한다. Agent는 Backend가 검증한 단일 계좌 ID와 정규화된 별칭만 Workflow State에 저장한다.

Backend의 별칭 입력 검증은 다음 항목을 포함한다.

- 앞뒤 공백 제거와 정규화
- 빈 문자열 여부
- 최소·최대 길이
- 허용 문자와 금칙어
- 제어문자와 화면 표시를 훼손하는 문자열 차단

Frontend가 입력한 별칭이 검증에 실패하면 Backend는 Agent를 재개하지 않고 같은 입력 UI에 오류를 표시한다. 검증을 통과한 경우에만 `alias_input_outcome=submitted`와 정규화된 `alias`로 Agent를 재개한다. 사용자가 취소하면 `alias_input_outcome=cancelled`, `alias=null`로 재개하며 Agent는 추가 Tool API나 UI Webhook 없이 Workflow를 종료한다.

Prepare 호출 직전 `start_account_alias_prepare`가 `prepare_attempt`를 증가시키고 Checkpoint를 저장한다. 멱등성 키는 다음 규칙으로 생성한다.

```text
account_alias_prepare:{execution_context_id}:{prepare_attempt}
```

Prepare 요청은 다음 두 업무 필드만 사용한다.

```json
{
  "account_id": "acc_001",
  "alias": "여행 자금"
}
```

Backend는 계좌 소유권과 활성 상태, 별칭 정책을 다시 확인한다. 현재 별칭과 정규화된 `alias`가 같으면 `outcome=unchanged`를 반환한다. 이 경우 Confirmation을 생성하지 않고 `emit_account_alias_unchanged` Step에서 공통 `setting_result` UI를 `outcome=unchanged`로 전송한 뒤 종료한다. 변경 완료 결과도 같은 UI 계약을 `outcome=completed`로 사용한다. Workflow Step은 실행 전 종료와 실행 완료를 구분하기 위해 별도로 유지한다.

변경이 필요한 경우 Backend는 `outcome=ready_for_confirmation`, `confirmation_id`, 만료시각과 최소한의 화면 표시 데이터를 반환한다. `account_label`과 `current_alias`는 표시 데이터에도 포함하지 않는다.

```json
{
  "confirmation_id": "confirm_alias_123",
  "confirmation_view": {
    "account": {
      "account_id": "acc_001",
      "bank_name": "신한은행",
      "masked_account_number": "110-***-123456"
    },
    "alias": "여행 자금",
    "expires_at": "2026-07-14T10:05:00+09:00"
  }
}
```

Agent는 `confirmation_id`와 임시 `confirmation_view`를 저장한 뒤 승인 요청 Webhook을 전송하고 중단한다. Backend는 사용자와 Confirmation을 검증하고 승인 화면의 결정을 `approval_outcome`으로 Agent에 전달한다.

- `approved`: `confirmation_view`, `approval_outcome`, `change_target`을 제거하고 승인된 `confirmation_id`만 유지한 채 Execute로 이동한다.
- `change_requested / account`: Backend가 기존 Confirmation을 무효화한 뒤 Agent를 재개한다. Agent는 `reset_account_alias_target`에서 계좌·승인 관련 임시 State를 제거하고 `alias`는 유지한 채 최신 계좌를 다시 조회한다.
- `change_requested / alias`: Backend가 기존 Confirmation을 무효화한 뒤 Agent를 재개한다. Agent는 `reset_account_alias_value`에서 별칭·승인 관련 임시 State를 제거하고 `account_id`는 유지한 채 새 별칭 입력을 요청한다.
- `cancelled`: Backend가 Confirmation을 취소 처리한 뒤 Agent를 재개한다. Agent는 승인 관련 임시 State를 제거하고 추가 Tool API나 UI Webhook 없이 종료한다.

`reset_account_alias_target`은 `account_hint`, `account_resolution_outcome`, `accounts`, `account_id`, `account_selection_outcome`, `alias_input_outcome`, `input_request_id`, `confirmation_id`, `confirmation_view`, `approval_outcome`, `change_target`을 초기화한다. `alias`, `prepare_attempt`, `correction_view`는 유지하며 `resolve_account_alias_target`에서 최신 계좌를 다시 조회한다. `correction_view`가 있으면 다음 계좌 선택 UI에 수정 사유를 함께 표시한다.

`reset_account_alias_value`는 `alias`, `alias_input_outcome`, `input_request_id`, `confirmation_id`, `confirmation_view`, `approval_outcome`, `change_target`을 초기화한다. 확정된 `account_id`, `prepare_attempt`, `correction_view`는 유지하며 `request_account_alias_input`으로 이동한다. 입력 UI는 `correction_view`의 수정 사유를 표시한다. 두 초기화 Step 모두 API를 호출하지 않는 Agent 내부 Step이다. 새 계좌 또는 별칭이 확정되면 `start_account_alias_prepare`가 `correction_view`를 제거하고 `prepare_attempt`를 증가시킨다.

Execute 멱등성 키는 다음처럼 Confirmation당 하나로 고정한다.

```text
account_alias_execute:{confirmation_id}
```

Execute 요청은 `confirmation_id`만 전달한다. Backend는 Confirmation의 소유자, 승인 상태, 만료 여부와 미실행 상태를 검증한 뒤 별칭을 변경한다. 같은 Confirmation의 중복 실행은 차단하거나 최초 결과를 재응답한다. 이 설정 변경에는 별도 추가 인증을 요구하지 않는다.

Execute 시점에 계좌 상태 또는 별칭 정책이 바뀌면 Backend는 `outcome=correction_required`와 수정 가능한 `account` 또는 `alias`를 반환하고 기존 Confirmation을 재사용할 수 없게 처리한다. 설정 변경이 차단되면 종료한다. Timeout 또는 HTTP `502`, `503`, `504`는 같은 Execute 멱등성 키와 Body로 최대 1회 재시도하고, 다시 실패하면 `emit_account_alias_error`로 종료한다.

별칭 변경 Prepare와 Execute의 `correction_view.allowed_change_targets`는 정확히 하나의 값만 가진다. `account`이면 계좌 수정 Route, `alias`이면 별칭 수정 Route로 이동한다. 배열이 비어 있거나 두 개 이상이면 Agent는 우선순위를 추측하지 않고 계약 오류로 `emit_account_alias_error`에 연결한다. 여러 조건을 수정해야 하는 경우에는 한 값을 수정한 뒤 새 Prepare에서 다음 조건을 다시 평가한다.

Workflow Step은 다음과 같이 구성한다.

```text
extract_account_alias_slots
-> resolve_account_alias_target
-> request_account_alias_selection, emit_account_alias_selection_empty 또는 Backend 자동 확정 결과 사용
-> 계좌가 확정되면 check_account_alias_value
-> alias가 있으면 start_account_alias_prepare
-> alias가 없으면 request_account_alias_input
-> submitted이면 start_account_alias_prepare, cancelled이면 END
-> start_account_alias_prepare
-> prepare_account_alias_change
-> 별칭이 같으면 emit_account_alias_unchanged -> END
-> account 수정이 필요하면 reset_account_alias_target -> resolve_account_alias_target
-> alias 수정이 필요하면 reset_account_alias_value -> request_account_alias_input
-> 설정 변경이 차단되면 emit_account_alias_blocked -> END
-> request_account_alias_approval
-> interrupt
-> approved이면 execute_account_alias_change
-> change_requested/account이면 reset_account_alias_target -> resolve_account_alias_target
-> change_requested/alias이면 reset_account_alias_value -> request_account_alias_input
-> cancelled이면 추가 Webhook 없이 END
-> completed이면 emit_account_alias_result -> END
-> account 수정이 필요하면 reset_account_alias_target -> resolve_account_alias_target
-> alias 수정이 필요하면 reset_account_alias_value -> request_account_alias_input
-> blocked이면 emit_account_alias_blocked -> END
```

Step State Mapping은 다음과 같다.

| step_id | direction | state_key | contract_field_path |
|---|---|---|---|
| `extract_account_alias_slots` | `output` | `account_hint` | `agent.extracted.account_hint` |
| `extract_account_alias_slots` | `output` | `alias` | `agent.extracted.alias` |
| `resolve_account_alias_target` | `input` | `account_hint` | `query.account_hint` |
| `resolve_account_alias_target` | `output` | `account_resolution_outcome` | `response.data.account_resolution_outcome` |
| `resolve_account_alias_target` | `output` | `accounts` | `response.data.accounts` |
| `resolve_account_alias_target` | `output` | `account_id` | `response.data.account_ids[0]` |
| `request_account_alias_selection` | `input` | `accounts` | `webhook.metadata.ui.payload.accounts` |
| `request_account_alias_selection` | `input` | `correction_view` | `webhook.metadata.ui.payload.correction_view` |
| `request_account_alias_selection` | `output` | `account_selection_outcome` | `resume.value.account_selection_outcome` |
| `request_account_alias_selection` | `output` | `account_id` | `resume.value.account_ids[0]` |
| `emit_account_alias_selection_empty` | `input` | `accounts` | `webhook.metadata.ui.payload.accounts` |
| `check_account_alias_value` | `input` | `alias` | `agent.state.alias` |
| `request_account_alias_input` | `output` | `alias_input_outcome` | `resume.value.alias_input_outcome` |
| `request_account_alias_input` | `output` | `alias` | `resume.value.alias` |
| `request_account_alias_input` | `input` | `correction_view` | `webhook.metadata.ui.payload.correction_view` |
| `start_account_alias_prepare` | `output` | `prepare_attempt` | `agent.state.prepare_attempt` |
| `start_account_alias_prepare` | `output` | `correction_view` | `agent.state.correction_view=null` |
| `prepare_account_alias_change` | `input` | `account_id` | `request.account_id` |
| `prepare_account_alias_change` | `input` | `alias` | `request.alias` |
| `prepare_account_alias_change` | `input` | `prepare_attempt` | `header.Idempotency-Key` |
| `prepare_account_alias_change` | `output` | `confirmation_id` | `response.data.confirmation_id` |
| `prepare_account_alias_change` | `output` | `confirmation_view` | `response.data.confirmation_view` |
| `prepare_account_alias_change` | `output` | `correction_view` | `response.data.correction_view` |
| `request_account_alias_approval` | `input` | `confirmation_id` | `webhook.interaction.confirmation_id` |
| `request_account_alias_approval` | `input` | `confirmation_view` | `webhook.metadata.ui.payload` |
| `request_account_alias_approval` | `output` | `approval_outcome` | `resume.value.approval_outcome` |
| `request_account_alias_approval` | `output` | `change_target` | `resume.value.change_target` |
| `reset_account_alias_target` | `output` | `account_hint` | `agent.state.account_hint=null` |
| `reset_account_alias_target` | `output` | `account_resolution_outcome` | `agent.state.account_resolution_outcome=null` |
| `reset_account_alias_target` | `output` | `accounts` | `agent.state.accounts=[]` |
| `reset_account_alias_target` | `output` | `account_id` | `agent.state.account_id=null` |
| `reset_account_alias_target` | `output` | `account_selection_outcome` | `agent.state.account_selection_outcome=null` |
| `reset_account_alias_target` | `output` | `alias_input_outcome` | `agent.state.alias_input_outcome=null` |
| `reset_account_alias_target` | `output` | `input_request_id` | `agent.state.input_request_id=null` |
| `reset_account_alias_target` | `output` | `confirmation_id` | `agent.state.confirmation_id=null` |
| `reset_account_alias_target` | `output` | `confirmation_view` | `agent.state.confirmation_view=null` |
| `reset_account_alias_target` | `output` | `approval_outcome` | `agent.state.approval_outcome=null` |
| `reset_account_alias_target` | `output` | `change_target` | `agent.state.change_target=null` |
| `reset_account_alias_value` | `output` | `alias` | `agent.state.alias=null` |
| `reset_account_alias_value` | `output` | `alias_input_outcome` | `agent.state.alias_input_outcome=null` |
| `reset_account_alias_value` | `output` | `input_request_id` | `agent.state.input_request_id=null` |
| `reset_account_alias_value` | `output` | `confirmation_id` | `agent.state.confirmation_id=null` |
| `reset_account_alias_value` | `output` | `confirmation_view` | `agent.state.confirmation_view=null` |
| `reset_account_alias_value` | `output` | `approval_outcome` | `agent.state.approval_outcome=null` |
| `reset_account_alias_value` | `output` | `change_target` | `agent.state.change_target=null` |
| `execute_account_alias_change` | `input` | `confirmation_id` | `request.confirmation_id` |
| `execute_account_alias_change` | `output` | `account_id` | `response.data.account_id` |
| `execute_account_alias_change` | `output` | `alias` | `response.data.alias` |
| `execute_account_alias_change` | `output` | `completed_at` | `response.data.completed_at` |
| `execute_account_alias_change` | `output` | `correction_view` | `response.data.correction_view` |
| `emit_account_alias_unchanged` | `input` | `account_id` | `webhook.metadata.ui.payload.account.account_id` |
| `emit_account_alias_unchanged` | `input` | `alias` | `webhook.metadata.ui.payload.alias` |
| `emit_account_alias_result` | `input` | `account_id` | `webhook.metadata.ui.payload.account.account_id` |
| `emit_account_alias_result` | `input` | `alias` | `webhook.metadata.ui.payload.alias` |

계약 매핑은 다음과 같다.

| step_id | interaction_mode | contract_id |
|---|---|---|
| `extract_account_alias_slots` | `agent_internal` | 없음 |
| `resolve_account_alias_target` | `backend_tool_api` | `API-ACCOUNT-LIST` |
| `request_account_alias_selection` | `webhook_then_resume` | `UI-ACCOUNT-ALIAS-SELECTION` |
| `emit_account_alias_selection_empty` | `webhook` | `UI-ACCOUNT-ALIAS-SELECTION` |
| `check_account_alias_value` | `agent_internal` | 없음 |
| `request_account_alias_input` | `webhook_then_resume` | `UI-ACCOUNT-ALIAS-INPUT` |
| `start_account_alias_prepare` | `agent_internal` | 없음 |
| `prepare_account_alias_change` | `backend_tool_api` | `API-ACCOUNT-ALIAS-PREPARE` |
| `emit_account_alias_unchanged` | `webhook` | `UI-ACCOUNT-ALIAS-RESULT` |
| `emit_account_alias_blocked` | `webhook` | `UI-SETTING-BLOCKED` |
| `request_account_alias_approval` | `webhook_then_resume` | `UI-ACCOUNT-ALIAS-CONFIRMATION` |
| `reset_account_alias_target` | `agent_internal` | 없음 |
| `reset_account_alias_value` | `agent_internal` | 없음 |
| `execute_account_alias_change` | `backend_tool_api` | `API-ACCOUNT-ALIAS-EXECUTE` |
| `emit_account_alias_result` | `webhook` | `UI-ACCOUNT-ALIAS-RESULT` |
| `emit_account_alias_error` | `webhook` | `UI-COMMON-ERROR` |

#### `wf_internal_transfer`

본인 계좌 간 이체는 출금 계좌, 입금 계좌와 금액을 확정한 뒤 Backend가 소유권, 잔액, 한도와 거래 가능 상태를 검증하고 사용자 승인과 추가 인증을 모두 완료한 경우에만 실제 이체를 실행하는 쓰기 Workflow다. Agent는 원장을 직접 조회하거나 잔액과 이체 한도를 자체 판단하지 않는다.

본인 계좌 간 이동도 실제 금융 원장을 변경하는 송금이므로 위험등급을 `R3`이 아니라 타인송금과 동일한 고위험 실행 `R4`로 분류한다. `R5`는 실행 가능한 최고 위험등급이 아니라 정책상 차단·금지 요청에 사용한다. 향후 `risk_levels.yaml`과 관리시트를 다시 생성할 때 `R3`의 본인 계좌 간 이동 설명을 제거하고 본인송금 Workflow의 최대 위험등급과 Execute Step을 `R4` 기준으로 맞춘다.

| state_key | data_type | nullable | 기본값 | 역할 |
|---|---|---:|---|---|
| `from_account_hint` | string | true | null | 발화에서 추출한 출금 계좌 힌트 |
| `to_account_hint` | string | true | null | 발화에서 추출한 입금 계좌 힌트 |
| `account_resolution_outcome` | string | true | null | 현재 계좌 확인 Step의 Backend 자동 확정 결과 |
| `accounts` | `list[AccountCandidate]` | false | `[]` | 현재 계좌 선택 단계의 Backend 검증 UI 후보 |
| `account_selection_outcome` | string | true | null | 현재 계좌 선택 UI의 `selected`, `cancelled` 재개 결과 |
| `from_account_id` | string | true | null | 출금할 본인 계좌 ID |
| `to_account_id` | string | true | null | 입금할 본인 계좌 ID |
| `amount` | integer | true | null | 이체 금액 |
| `amount_input_outcome` | string | true | null | 금액 입력 UI의 `submitted`, `cancelled` 재개 결과 |
| `currency` | string | false | `KRW` | 이체 통화 |
| `input_request_id` | string | true | null | 계좌·금액·수정 입력 요청 식별자 |
| `confirmation_id` | string | true | null | Backend가 발급한 이체 승인 식별자 |
| `confirmation_view` | `ConfirmationView` | true | null | 승인 화면과 완료 결과 화면에서 재사용하는 Backend 표시 데이터 |
| `approval_outcome` | string | true | null | Backend가 검증한 `approved`, `change_requested`, `cancelled` 승인 결과 |
| `change_target` | string | true | null | `from_account`, `to_account`, `amount` 중 수정 대상 |
| `correction_view` | `TransferCorrectionView` | true | null | Prepare·Execute 업무 오류의 수정 가능 항목 표시 데이터 |
| `correction_selection_outcome` | string | true | null | 복수 수정 대상 선택 UI의 `selected`, `cancelled` 재개 결과 |
| `blocked_view` | `BlockedView` | true | null | Backend가 제공한 사용자 표시용 이체 차단 안내 |
| `auth_context_id` | string | true | null | Backend가 발급한 추가 인증 Context ID |
| `auth_request_view` | `AuthRequestView` | true | null | 인증 입력 대기 중에만 보존하는 표시 데이터 |
| `auth_status` | string | true | null | `verified`, `failed`, `cancelled`, `expired` 중 인증 결과 |
| `auth_retry_outcome` | string | true | null | 재인증 선택 UI의 `retry`, `cancelled` 재개 결과 |
| `prepare_attempt` | integer | false | `0` | Prepare 멱등성 키 생성을 위한 시도 번호 |
| `auth_attempt` | integer | false | `0` | Auth Context 멱등성 키 생성을 위한 시도 번호 |
| `transaction_id` | string | true | null | 완료된 본인 이체 거래 ID |
| `completed_at` | datetime | true | null | 이체 완료 시각 |

출금 계좌와 입금 계좌는 같은 계좌 목록에서 선택하더라도 업무 역할이 다르므로 `from_account_id`, `to_account_id`와 각각의 힌트를 분리한다. `account_resolution_outcome`, `accounts`, `account_selection_outcome`은 출금과 입금 계좌 확인 단계에서 순서대로 재사용하며 두 후보 목록을 동시에 State에 저장하지 않는다. `memo`는 사용하지 않는다.

본인 이체 의도가 확정되면 일부 업무 값이 없어도 Workflow에 진입할 수 있다. Prepare는 다음 조건을 모두 만족한 뒤에만 호출한다.

```text
Workflow 진입 조건
- 본인 계좌 간 이체 의도가 확정됨

Prepare 호출 조건
- from_account_id가 존재함
- to_account_id가 존재함
- amount가 존재함
- from_account_id와 to_account_id가 서로 다름
- Backend가 Frontend 입력을 검증한 뒤 Agent를 재개함
```

예를 들어 “저축 계좌로 10만 원 옮겨줘”는 입금 계좌 힌트와 금액을 먼저 저장하고 출금 계좌를 추가로 선택받는다. “생활비 계좌에서 저축 계좌로 옮겨줘”는 두 계좌를 확정한 뒤 금액을 추가로 입력받는다.

Backend 계좌 목록 응답을 이용해 출금 계좌와 입금 계좌를 순서대로 확정한다. 두 역할 모두 `resolve_selection=true`와 `account_ids` 배열 계약을 사용한다. `resolved`이면 Agent는 배열 길이가 정확히 한 개인지 구조적으로 확인한 뒤 각각 `from_account_id` 또는 `to_account_id`에 저장한다. 배열이 비어 있거나 두 개 이상이면 첫 값을 임의로 선택하지 않고 계약 오류로 처리한다. 여러 계좌와 일치하면 같은 계좌 선택 UI 계약에 서로 다른 `purpose`를 사용한다.

출금 계좌 조회는 `from_account_hint`를 API의 `account_hint`에 매핑하고 `account_capability=withdraw`를 고정값으로 전달한다. 입금 계좌 조회는 `to_account_hint`를 `account_hint`에 매핑하고 `account_capability=deposit`을 고정값으로 전달하며 `exclude_account_ids=[from_account_id]`를 함께 보낸다. 후보 제외와 계좌 거래 가능 여부 판단은 Backend가 수행하고 Agent가 후보 목록을 직접 필터링하지 않는다. 두 역할은 별도 API Step으로 관리한다.

```text
internal_transfer_from_account
internal_transfer_to_account
```

출금 계좌를 선택할 때는 출금 가능한 계좌만 보여주고, 입금 계좌를 선택할 때는 입금 가능한 계좌 중 확정된 출금 계좌를 제외한다. Frontend가 보낸 계좌 ID와 금액은 Backend가 사용자, Pending Input과 허용 후보를 검증한 뒤 Agent를 재개한다. 형식 검증에 실패하면 Agent를 재개하지 않고 같은 UI에서 오류를 표시해 다시 입력받는다.

입금 계좌가 확정되면 `check_internal_transfer_amount`가 `amount`의 존재 여부, 정수 형식과 0보다 큰지만 구조적으로 확인한다. 잔액, 한도와 실제 이체 가능 금액은 판단하지 않는다. 구조적으로 사용할 수 있는 금액이 없으면 `request_internal_transfer_amount`를 표시한다. Backend 검증을 통과한 입력은 `amount_input_outcome=submitted`와 정규화된 `amount`로 Agent를 재개하고, 취소는 `amount_input_outcome=cancelled`, `amount=null`로 재개한다. 취소 시 추가 Tool API나 UI Webhook 없이 종료한다.

Prepare 직전 `start_internal_transfer_prepare`가 `prepare_attempt`를 증가시키고 Checkpoint를 저장한다. 멱등성 키는 다음 규칙으로 생성한다.

```text
internal_transfer_prepare:{execution_context_id}:{prepare_attempt}
```

Prepare 요청은 다음 업무 필드만 사용한다.

```json
{
  "from_account_id": "acc_001",
  "to_account_id": "acc_002",
  "amount": 100000,
  "currency": "KRW"
}
```

Backend는 다음 항목을 검증한다.

- 두 계좌가 모두 인증된 사용자 소유인지
- 두 계좌가 서로 다른지
- 출금 계좌가 활성 상태이고 출금 가능한지
- 입금 계좌가 활성 상태이고 입금 가능한지
- 이체 금액과 통화가 유효한지
- 출금 가능 잔액이 충분한지
- 회당·일일 이체 한도를 넘지 않는지
- 계좌와 사용자에게 거래 제한이 없는지

따라서 Agent Workflow에는 `check_balance`, `check_transfer_limit`, `run_pre_execution_guardrail` 같은 금융 검증 Step을 두지 않는다.

Prepare 결과가 `ready_for_confirmation`이면 Backend는 Confirmation과 마스킹된 승인 화면 데이터를 반환한다. `from_account_label`, `to_account_label` 같은 별도 필드는 만들지 않고 계좌 객체의 `account_alias`를 사용한다.

```json
{
  "confirmation_id": "confirm_internal_123",
  "confirmation_view": {
    "from_account": {
      "account_id": "acc_001",
      "bank_name": "신한은행",
      "account_alias": "생활비",
      "masked_account_number": "110-***-123456"
    },
    "to_account": {
      "account_id": "acc_002",
      "bank_name": "국민은행",
      "account_alias": "저축",
      "masked_account_number": "123-***-456789"
    },
    "amount": 100000,
    "fee": 0,
    "total_debit": 100000,
    "currency": "KRW",
    "expires_at": "2026-07-14T10:05:00+09:00"
  }
}
```

승인 화면은 다음 동작을 제공한다.

```text
approve
modify_from_account
modify_to_account
modify_amount
cancel
```

Frontend는 수정 요청을 다음 의미로 Backend에 전달한다.

```json
{
  "confirmation_id": "confirm_internal_123",
  "decision": "modify",
  "change_target": "amount"
}
```

`change_target` Enum은 다음과 같다.

```text
from_account
to_account
amount
```

Backend는 수정이나 취소 요청을 받으면 Confirmation 소유권과 상태를 검증하고 기존 Confirmation을 무효화한 뒤 Agent를 재개한다. Agent가 Confirmation 무효화 Tool API를 다시 호출하지 않는다. Agent는 `approval_outcome`과 `change_target`으로 Route를 결정한 뒤 `confirmation_id`, `confirmation_view`, `approval_outcome`을 제거한다.

수정 대상별 Agent 내부 초기화 Step은 다음과 같다.

| change_target | 초기화 Step | 유지 필드 | 다음 Step |
|---|---|---|---|
| `from_account` | `reset_internal_from_account` | `to_account_id`, `amount`, `correction_view` | `resolve_internal_from_account` |
| `to_account` | `reset_internal_to_account` | `from_account_id`, `amount`, `correction_view` | `resolve_internal_to_account` |
| `amount` | `reset_internal_transfer_amount` | `from_account_id`, `to_account_id`, `correction_view` | `request_internal_transfer_amount` |

세 초기화 Step은 공통으로 `confirmation_id`, `confirmation_view`, `approval_outcome`, `change_target`, `correction_selection_outcome`, `blocked_view`, `auth_context_id`, `auth_request_view`, `auth_status`, `auth_retry_outcome`, `input_request_id`를 제거하고 `auth_attempt=0`으로 초기화한다. 계좌 수정 Step은 공통 계좌 확인 임시 State인 `account_resolution_outcome`, `accounts`, `account_selection_outcome`도 제거한다. 출금 계좌 수정은 `from_account_hint`, 입금 계좌 수정은 `to_account_hint`도 제거하여 최초 발화의 힌트로 같은 계좌가 다시 자동 확정되지 않게 한다. 금액 수정 Step은 `amount`, `amount_input_outcome`을 제거한다. 출금 또는 입금 계좌를 수정하더라도 유지하는 금액의 이전 `amount_input_outcome`은 상호작용 결과이므로 제거한다.

계좌 수정에서는 최신 계좌 상태와 선택 가능 여부를 반영하기 위해 계좌 목록을 다시 조회한다. 출금 계좌 재조회는 유지한 `to_account_id`, 입금 계좌 재조회는 유지한 `from_account_id`를 `exclude_account_ids`로 전달한다. `correction_view`는 다음 선택·입력 UI까지 유지하고 `start_internal_transfer_prepare`에서 제거한다. 수정한 값으로 Prepare를 다시 호출할 때 `prepare_attempt`를 증가시켜 새로운 멱등성 키와 Confirmation을 생성한다.

Prepare가 잔액 부족이나 한도 초과처럼 사용자가 수정할 수 있는 업무 오류를 반환하면 단순 실패로 종료하지 않는다. `route_internal_transfer_correction`은 `correction_view.allowed_change_targets`의 구조만 확인한다. 허용된 수정 대상이 하나면 해당 초기화 Route로 바로 이동하고, 두 개 이상이면 `request_internal_transfer_correction`을 표시해 사용자 선택 또는 취소를 입력받는다.

```json
{
  "reason": "insufficient_balance",
  "allowed_change_targets": [
    "from_account",
    "amount"
  ]
}
```

사용자가 선택한 `change_target`은 Backend가 `allowed_change_targets`에 포함되는지 검증한 뒤 `correction_selection_outcome=selected`로 Agent를 재개한다. 사용자가 취소하면 `correction_selection_outcome=cancelled`, `change_target=null`로 재개하며 Agent는 추가 Tool API나 UI Webhook 없이 종료한다. 배열이 비었거나 허용되지 않은 값이 있으면 Agent는 수정 대상을 추측하지 않고 계약 오류로 처리한다. 계좌 소유권 위반이나 정책 차단처럼 사용자 입력 수정으로 해결할 수 없는 오류는 수정 UI를 표시하지 않고 차단 결과로 종료한다.

Prepare 또는 Execute가 `outcome=blocked`를 반환하면 Agent는 자동 재시도하지 않는다. Backend가 함께 제공한 사용자 표시용 `blocked_view`를 `emit_internal_transfer_blocked` Webhook에 그대로 전달하고 종료한다. Agent는 정책 코드나 내부 차단 사유를 사용자 문장으로 다시 해석하지 않는다. `success=false`, `error.category=technical_error`는 차단과 구분하며 공통 조건에 해당할 때만 동일 요청을 최대 1회 재시도한 뒤 `emit_internal_transfer_error`로 종료한다.

Execute 멱등성 키는 인증 시도별로 생성한다.

```text
internal_transfer_execute:{confirmation_id}:{auth_attempt}
```

같은 인증 시도의 Timeout 또는 응답 유실 재시도에는 동일한 키와 Body를 사용한다. 재인증으로 새 `auth_context_id`가 생성된 경우에는 증가한 `auth_attempt`로 새 Execute 키를 생성한다. Backend는 멱등성 키가 달라져도 Confirmation의 미실행 상태를 검증하여 동일 Confirmation의 중복 송금을 차단한다.

사용자 승인 후 Agent는 본인송금용 Auth Context를 생성하고 인증 UI Webhook을 전송한 뒤 중단한다. 본인송금도 위험도와 금액에 관계없이 추가 인증을 필수로 수행하며 승인 후 바로 Execute로 이동하는 Route는 제공하지 않는다.

```text
사용자 승인
-> start_internal_auth
-> create_internal_auth_context
-> request_internal_authentication
-> interrupt
```

Auth Context 생성 요청은 송금 유형을 중복하지 않고 `confirmation_id`만 전달한다.

```json
{
  "confirmation_id": "confirm_internal_123"
}
```

멱등성 키는 다음 규칙으로 생성한다.

```text
internal_transfer_auth:{confirmation_id}:{auth_attempt}
```

Backend가 `auth_status=verified`로 Agent를 재개한 경우에만 Execute로 이동한다. `failed` 또는 `expired`이면 `request_internal_auth_retry`에서 재인증 여부를 입력받는다. `auth_retry_outcome=retry`이면 기존 `auth_context_id`, `auth_request_view`, `auth_status`, `auth_retry_outcome`을 제거하고 `auth_attempt`를 증가시켜 새 Auth Context를 생성한다. `auth_retry_outcome=cancelled`이거나 최초 인증 화면에서 `auth_status=cancelled`이면 Agent는 추가 취소 Webhook 없이 종료한다.

Execute 요청은 `confirmation_id`와 `auth_context_id`를 전달한다.

```json
{
  "confirmation_id": "confirm_internal_123",
  "auth_context_id": "auth_internal_123"
}
```

Backend는 승인된 Confirmation에 고정된 계좌, 금액과 통화를 사용한다. Execute 시점에도 Auth Context의 소유자, `verified` 상태와 만료, 잔액, 한도와 계좌 상태를 다시 검증하고, 출금과 입금 원장 반영, Transaction 생성, Confirmation 실행 처리와 금융 Audit 기록을 하나의 트랜잭션 경계에서 수행한다. 같은 Confirmation의 중복 실행은 차단하거나 최초 실행 결과를 재응답한다.

Execute가 완료되면 `emit_internal_transfer_result`는 Execute 응답의 `transaction_id`, `completed_at`과 Prepare에서 저장한 `confirmation_view`의 `from_account`, `to_account`, `amount`, `currency`를 조합해 완료 Webhook을 전송한다. Agent는 결과 화면을 위해 계좌를 다시 조회하거나 계좌 표시정보를 새로 만들지 않는다. `fee`, `total_debit`, `expires_at`처럼 승인 확인에는 필요하지만 완료 결과 계약에 포함되지 않은 필드는 전달하지 않는다.

```json
{
  "outcome": "completed",
  "transaction_id": "txn_internal_123",
  "completed_at": "2026-07-13T10:04:00+09:00",
  "from_account": {
    "account_id": "acc_001",
    "account_alias": "생활비",
    "bank_name": "신한은행",
    "masked_account_number": "110-***-123456"
  },
  "to_account": {
    "account_id": "acc_002",
    "account_alias": "저축",
    "bank_name": "신한은행",
    "masked_account_number": "110-***-987654"
  },
  "amount": 100000,
  "currency": "KRW"
}
```

Prepare 이후 잔액이 바뀌어 Execute에서 수정 가능한 업무 오류가 발생하면 Backend는 Confirmation과 Auth Context를 재사용할 수 없게 처리한다. Agent는 승인·인증 관련 State를 제거하고 `correction_view`를 표시한 뒤 금액 또는 출금 계좌 수정 Route로 이동한다. 자동으로 Execute를 재시도하지 않는다.

Confirmation은 승인된 유효 상태지만 Auth Context만 만료된 경우 Backend는 `outcome=reauthentication_required`를 반환한다. Agent는 `confirmation_id`, `from_account_id`, `to_account_id`, `amount`, `currency`를 유지하고 `auth_context_id`, `auth_request_view`, `auth_status`, `auth_retry_outcome`만 제거한 뒤 `start_internal_auth`로 이동한다. `start_internal_auth`는 `auth_attempt`를 증가시켜 새 Auth Context를 생성하며, 인증이 완료되면 Prepare와 사용자 승인을 반복하지 않고 Execute를 다시 호출한다. Confirmation도 만료되었거나 무효화된 경우에는 이 경로를 사용하지 않고 새로운 Prepare와 사용자 승인을 수행한다.

Workflow Step은 다음과 같이 구성한다.

```text
extract_internal_transfer_slots
-> resolve_internal_from_account
-> request_from_account_selection, emit_internal_from_accounts_empty 또는 Backend 자동 확정 결과 사용
-> resolve_internal_to_account
-> request_to_account_selection, emit_internal_to_accounts_empty 또는 Backend 자동 확정 결과 사용
-> check_internal_transfer_amount
-> 금액이 유효하면 start_internal_transfer_prepare
-> 금액이 없거나 구조 오류이면 request_internal_transfer_amount
-> submitted이면 start_internal_transfer_prepare, cancelled이면 END
-> start_internal_transfer_prepare
-> prepare_internal_transfer

ready_for_confirmation
-> request_internal_transfer_approval
-> interrupt
-> approve이면 start_internal_auth
-> create_internal_auth_context
-> request_internal_authentication
-> interrupt
-> verified이면 execute_internal_transfer
-> emit_internal_transfer_result
-> END

인증 failed 또는 expired
-> request_internal_auth_retry
-> auth_retry_outcome=retry이면 기존 인증 State 제거
-> auth_attempt 증가 후 새 Auth Context 생성
-> auth_retry_outcome=cancelled이면 추가 Webhook 없이 END

인증 cancelled
-> 추가 Webhook 없이 END

승인 화면 수정
-> from_account이면 reset_internal_from_account -> resolve_internal_from_account
-> to_account이면 reset_internal_to_account -> resolve_internal_to_account
-> amount이면 reset_internal_transfer_amount -> request_internal_transfer_amount
-> start_internal_transfer_prepare

승인 화면 취소
-> 승인 관련 State 제거
-> END

Prepare 또는 Execute의 correction_required
-> route_internal_transfer_correction
-> 수정 대상이 하나면 해당 초기화 Step
-> 수정 대상이 복수이면 request_internal_transfer_correction
-> selected이면 선택한 초기화 Step, cancelled이면 END
-> start_internal_transfer_prepare

Execute의 reauthentication_required
-> confirmation_id와 송금 조건 유지
-> 기존 인증 State만 제거
-> auth_attempt 증가 후 새 Auth Context 생성
-> 인증 성공 후 Prepare와 승인 없이 Execute 재호출
-> start_internal_auth

blocked
-> emit_internal_transfer_blocked
-> END

success=false / technical_error
-> 공통 조건에 해당하면 동일 멱등성 키로 최대 1회 재시도
-> 재시도 실패 또는 재시도 대상이 아니면 emit_internal_transfer_error
-> END
```

Step State Mapping은 다음과 같다.

| step_id | direction | state_key | contract_field_path |
|---|---|---|---|
| `extract_internal_transfer_slots` | `output` | `from_account_hint` | `agent.extracted.from_account_hint` |
| `extract_internal_transfer_slots` | `output` | `to_account_hint` | `agent.extracted.to_account_hint` |
| `extract_internal_transfer_slots` | `output` | `amount` | `agent.extracted.amount` |
| `resolve_internal_from_account` | `input` | `from_account_hint` | `query.account_hint` |
| `resolve_internal_from_account` | `input` | `to_account_id` | `query.exclude_account_ids[0]` |
| `resolve_internal_from_account` | `output` | `account_resolution_outcome` | `response.data.account_resolution_outcome` |
| `resolve_internal_from_account` | `output` | `accounts` | `response.data.accounts` |
| `resolve_internal_from_account` | `output` | `from_account_id` | `response.data.account_ids[0]` |
| `request_from_account_selection` | `input` | `accounts` | `webhook.metadata.ui.payload.accounts` |
| `request_from_account_selection` | `output` | `account_selection_outcome` | `resume.value.account_selection_outcome` |
| `request_from_account_selection` | `output` | `from_account_id` | `resume.value.account_ids[0]` |
| `emit_internal_from_accounts_empty` | `input` | `accounts` | `webhook.metadata.ui.payload.accounts` |
| `resolve_internal_to_account` | `input` | `to_account_hint` | `query.account_hint` |
| `resolve_internal_to_account` | `input` | `from_account_id` | `query.exclude_account_ids[0]` |
| `resolve_internal_to_account` | `output` | `account_resolution_outcome` | `response.data.account_resolution_outcome` |
| `resolve_internal_to_account` | `output` | `accounts` | `response.data.accounts` |
| `resolve_internal_to_account` | `output` | `to_account_id` | `response.data.account_ids[0]` |
| `request_to_account_selection` | `input` | `accounts` | `webhook.metadata.ui.payload.accounts` |
| `request_to_account_selection` | `output` | `account_selection_outcome` | `resume.value.account_selection_outcome` |
| `request_to_account_selection` | `output` | `to_account_id` | `resume.value.account_ids[0]` |
| `emit_internal_to_accounts_empty` | `input` | `accounts` | `webhook.metadata.ui.payload.accounts` |
| `check_internal_transfer_amount` | `input` | `amount` | `agent.state.amount` |
| `request_internal_transfer_amount` | `output` | `amount_input_outcome` | `resume.value.amount_input_outcome` |
| `request_internal_transfer_amount` | `output` | `amount` | `resume.value.amount` |
| `start_internal_transfer_prepare` | `output` | `prepare_attempt` | `agent.state.prepare_attempt` |
| `start_internal_transfer_prepare` | `output` | `correction_view` | `agent.state.correction_view=null` |
| `prepare_internal_transfer` | `input` | `from_account_id` | `request.from_account_id` |
| `prepare_internal_transfer` | `input` | `to_account_id` | `request.to_account_id` |
| `prepare_internal_transfer` | `input` | `amount` | `request.amount` |
| `prepare_internal_transfer` | `input` | `currency` | `request.currency` |
| `prepare_internal_transfer` | `input` | `prepare_attempt` | `header.Idempotency-Key` |
| `prepare_internal_transfer` | `output` | `confirmation_id` | `response.data.confirmation_id` |
| `prepare_internal_transfer` | `output` | `confirmation_view` | `response.data.confirmation_view` |
| `prepare_internal_transfer` | `output` | `correction_view` | `response.data.correction_view` |
| `prepare_internal_transfer` | `output` | `blocked_view` | `response.data.blocked_view` |
| `request_internal_transfer_approval` | `input` | `confirmation_id` | `webhook.interaction.confirmation_id` |
| `request_internal_transfer_approval` | `input` | `confirmation_view` | `webhook.metadata.ui.payload` |
| `request_internal_transfer_approval` | `output` | `approval_outcome` | `resume.value.approval_outcome` |
| `request_internal_transfer_approval` | `output` | `change_target` | `resume.value.change_target` |
| `request_internal_transfer_correction` | `input` | `correction_view` | `webhook.metadata.ui.payload` |
| `route_internal_transfer_correction` | `input` | `correction_view` | `agent.state.correction_view` |
| `request_internal_transfer_correction` | `output` | `correction_selection_outcome` | `resume.value.correction_selection_outcome` |
| `request_internal_transfer_correction` | `output` | `change_target` | `resume.value.change_target` |
| `reset_internal_from_account` | `output` | `from_account_id` | `agent.state.from_account_id=null` |
| `reset_internal_to_account` | `output` | `to_account_id` | `agent.state.to_account_id=null` |
| `reset_internal_from_account` | `output` | `from_account_hint` | `agent.state.from_account_hint=null` |
| `reset_internal_to_account` | `output` | `to_account_hint` | `agent.state.to_account_hint=null` |
| `reset_internal_transfer_amount` | `output` | `amount` | `agent.state.amount=null` |
| `reset_internal_transfer_amount` | `output` | `amount_input_outcome` | `agent.state.amount_input_outcome=null` |
| `reset_internal_from_account` | `output` | `auth_attempt` | `agent.state.auth_attempt=0` |
| `reset_internal_to_account` | `output` | `auth_attempt` | `agent.state.auth_attempt=0` |
| `reset_internal_transfer_amount` | `output` | `auth_attempt` | `agent.state.auth_attempt=0` |
| `create_internal_auth_context` | `input` | `confirmation_id` | `request.confirmation_id` |
| `create_internal_auth_context` | `input` | `auth_attempt` | `header.Idempotency-Key` |
| `create_internal_auth_context` | `output` | `auth_context_id` | `response.data.auth_context_id` |
| `create_internal_auth_context` | `output` | `auth_request_view` | `response.data.auth_request_view` |
| `request_internal_authentication` | `output` | `auth_status` | `resume.value.auth_status` |
| `request_internal_auth_retry` | `output` | `auth_retry_outcome` | `resume.value.auth_retry_outcome` |
| `execute_internal_transfer` | `input` | `confirmation_id` | `request.confirmation_id` |
| `execute_internal_transfer` | `input` | `auth_context_id` | `request.auth_context_id` |
| `execute_internal_transfer` | `input` | `auth_attempt` | `header.Idempotency-Key` |
| `execute_internal_transfer` | `output` | `transaction_id` | `response.data.transaction_id` |
| `execute_internal_transfer` | `output` | `completed_at` | `response.data.completed_at` |
| `execute_internal_transfer` | `output` | `correction_view` | `response.data.correction_view` |
| `execute_internal_transfer` | `output` | `blocked_view` | `response.data.blocked_view` |
| `emit_internal_transfer_result` | `input` | `transaction_id` | `webhook.metadata.ui.payload.transaction_id` |
| `emit_internal_transfer_result` | `input` | `completed_at` | `webhook.metadata.ui.payload.completed_at` |
| `emit_internal_transfer_result` | `input` | `confirmation_view` | `webhook.metadata.ui.payload.from_account` |
| `emit_internal_transfer_result` | `input` | `confirmation_view` | `webhook.metadata.ui.payload.to_account` |
| `emit_internal_transfer_result` | `input` | `confirmation_view` | `webhook.metadata.ui.payload.amount` |
| `emit_internal_transfer_result` | `input` | `confirmation_view` | `webhook.metadata.ui.payload.currency` |
| `emit_internal_transfer_blocked` | `input` | `blocked_view` | `webhook.metadata.ui.payload` |

계약 매핑은 다음과 같다.

| step_id | interaction_mode | contract_id |
|---|---|---|
| `extract_internal_transfer_slots` | `agent_internal` | 없음 |
| `resolve_internal_from_account` | `backend_tool_api` | `API-ACCOUNT-LIST` |
| `resolve_internal_to_account` | `backend_tool_api` | `API-ACCOUNT-LIST` |
| `request_from_account_selection` | `webhook_then_resume` | `UI-INTERNAL-TRANSFER-FROM-ACCOUNT` |
| `request_to_account_selection` | `webhook_then_resume` | `UI-INTERNAL-TRANSFER-TO-ACCOUNT` |
| `emit_internal_from_accounts_empty` | `webhook` | `UI-INTERNAL-TRANSFER-FROM-ACCOUNT` |
| `emit_internal_to_accounts_empty` | `webhook` | `UI-INTERNAL-TRANSFER-TO-ACCOUNT` |
| `check_internal_transfer_amount` | `agent_internal` | 없음 |
| `request_internal_transfer_amount` | `webhook_then_resume` | `UI-TRANSFER-AMOUNT-INPUT` |
| `start_internal_transfer_prepare` | `agent_internal` | 없음 |
| `prepare_internal_transfer` | `backend_tool_api` | `API-INTERNAL-TRANSFER-PREPARE` |
| `request_internal_transfer_approval` | `webhook_then_resume` | `UI-INTERNAL-TRANSFER-CONFIRMATION` |
| `reset_internal_from_account` | `agent_internal` | 없음 |
| `reset_internal_to_account` | `agent_internal` | 없음 |
| `reset_internal_transfer_amount` | `agent_internal` | 없음 |
| `route_internal_transfer_correction` | `agent_internal` | 없음 |
| `request_internal_transfer_correction` | `webhook_then_resume` | `UI-INTERNAL-TRANSFER-CORRECTION` |
| `start_internal_auth` | `agent_internal` | 없음 |
| `create_internal_auth_context` | `backend_tool_api` | `API-AUTH-CONTEXT-CREATE` |
| `request_internal_authentication` | `webhook_then_resume` | `UI-INTERNAL-TRANSFER-AUTH` |
| `request_internal_auth_retry` | `webhook_then_resume` | `UI-INTERNAL-TRANSFER-AUTH-RETRY` |
| `execute_internal_transfer` | `backend_tool_api` | `API-INTERNAL-TRANSFER-EXECUTE` |
| `emit_internal_transfer_result` | `webhook` | `UI-INTERNAL-TRANSFER-RESULT` |
| `emit_internal_transfer_blocked` | `webhook` | `UI-TRANSFER-BLOCKED` |
| `emit_internal_transfer_error` | `webhook` | `UI-COMMON-ERROR` |

#### `wf_external_transfer`

타인송금은 출금 계좌, 수취인과 금액을 확정한 뒤 Backend가 송금 가능 여부를 사전 검증하고, 사용자 승인과 추가 인증을 모두 완료한 경우에만 실제 송금을 실행하는 쓰기 Workflow다. 모든 타인송금은 위험도와 금액에 관계없이 추가 인증을 필수로 수행한다.

| state_key | data_type | nullable | 기본값 | 역할 |
|---|---|---:|---|---|
| `from_account_hint` | string | true | null | 발화에서 추출한 출금 계좌 힌트 |
| `account_resolution_outcome` | string | true | null | Backend가 반환한 출금 계좌 자동 확정 결과 |
| `accounts` | `list[AccountCandidate]` | false | `[]` | Backend가 검증한 출금 계좌 선택 UI 후보 |
| `account_selection_outcome` | string | true | null | 출금 계좌 선택 UI의 `selected`, `cancelled` 재개 결과 |
| `from_account_id` | string | true | null | 송금액을 출금할 사용자 계좌 ID |
| `recipient_name_hint` | string | true | null | 최초 발화에서 추출한 수취인 이름 힌트 |
| `recipient_resolution_outcome` | string | true | null | 기존 거래 수취인 자동 확정 결과인 `resolved`, `selection_required` |
| `recipient_selection_reason` | string | true | null | 선택 UI가 필요한 `multiple_matches`, `no_match` 사유 |
| `recipient_selection_outcome` | string | true | null | 수취인 선택 UI의 `selected`, `cancelled` 재개 결과 |
| `to_recipient_id` | string | true | null | 선택된 기존 수취인 ID |
| `to_recipient_candidate_id` | string | true | null | 신규 계좌 검증 후 Backend가 발급한 후보 ID |
| `amount` | integer | true | null | 송금 금액 |
| `amount_input_outcome` | string | true | null | 금액 입력 UI의 `submitted`, `cancelled` 재개 결과 |
| `currency` | string | false | `KRW` | 송금 통화 |
| `input_request_id` | string | true | null | 수취인·계좌·금액·수정 입력 요청 식별자 |
| `confirmation_id` | string | true | null | Backend가 발급한 송금 승인 식별자 |
| `confirmation_view` | `ConfirmationView` | true | null | 승인 화면과 완료 결과 화면에서 재사용하는 Backend 표시 데이터 |
| `approval_outcome` | string | true | null | Backend가 검증한 `approved`, `change_requested`, `cancelled` 승인 결과 |
| `change_target` | string | true | null | `from_account`, `recipient`, `amount` 중 수정 대상 |
| `correction_view` | `TransferCorrectionView` | true | null | Prepare·Execute 업무 오류의 수정 가능 항목 표시 데이터 |
| `correction_selection_outcome` | string | true | null | 복수 수정 대상 선택 UI의 `selected`, `cancelled` 재개 결과 |
| `blocked_view` | `BlockedView` | true | null | Backend가 제공한 사용자 표시용 송금 차단 안내 |
| `auth_context_id` | string | true | null | Backend가 발급한 추가 인증 Context ID |
| `auth_request_view` | `AuthRequestView` | true | null | 인증 입력 대기 중에만 보존하는 표시 데이터 |
| `auth_status` | string | true | null | `verified`, `failed`, `cancelled`, `expired` 중 인증 결과 |
| `auth_retry_outcome` | string | true | null | 재인증 선택 UI의 `retry`, `cancelled` 재개 결과 |
| `prepare_attempt` | integer | false | `0` | Prepare 멱등성 키 생성을 위한 시도 번호 |
| `auth_attempt` | integer | false | `0` | Auth Context 멱등성 키 생성을 위한 시도 번호 |
| `transaction_id` | string | true | null | 완료된 타인송금 거래 ID |
| `completed_at` | datetime | true | null | 송금 완료 시각 |

`additional_auth_required`는 사용하지 않는다. 추가 인증은 Backend 위험 판단 결과에 따른 선택 Route가 아니라 모든 타인송금에 적용되는 고정 단계다. `memo`와 수취 계좌번호 원문도 Agent State와 Tool API 요청에 포함하지 않는다.

타인송금 의도가 확정되면 일부 업무 값이 없어도 Workflow에 진입할 수 있다. Prepare는 다음 조건을 모두 만족한 뒤에만 호출한다.

```text
Workflow 진입 조건
- 타인송금 의도가 확정됨

Prepare 호출 조건
- from_account_id가 존재함
- amount가 존재함
- to_recipient_id와 to_recipient_candidate_id 중 정확히 하나만 존재함
- Backend가 Frontend 입력을 검증한 뒤 Agent를 재개함
```

##### 수취인 확정

최초 발화에서 이름이 추출되면 Agent는 `recipient_name_hint`로 Backend에 기존 거래 수취인 자동 확정을 요청한다. Backend는 현재 사용자의 완료된 기존 타인송금 거래에서 이름이 정확히 일치하는 고유 수취인 참조를 확인한다.

```text
고유 수취인 1건
-> recipient_resolution_outcome=resolved
-> to_recipient_id 자동 확정

고유 수취인 2건 이상
-> recipient_resolution_outcome=selection_required
-> recipient_selection_reason=multiple_matches
-> request_recipient_selection

후보 없음
-> recipient_resolution_outcome=selection_required
-> recipient_selection_reason=no_match
-> request_recipient_selection

이름 힌트 없음
-> resolve_recipient_hint 생략
-> request_recipient_selection
```

`request_recipient_selection`은 후보 목록을 Webhook에 싣지 않고 `recipient_name_hint`와 값이 있는 경우 `recipient_selection_reason`만 전달한다. `multiple_matches`이면 이름 후보가 표시된 상태, `no_match` 또는 이름 힌트가 없으면 최근 수취인과 계좌번호 입력이 가능한 초기 상태를 Backend와 Frontend가 구성한다. Frontend의 `recipient_select` 검색 입력은 계좌번호 조회에 사용하며 최초 발화의 이름 힌트 처리와 혼합하지 않는다.

사용자가 기존 수취인을 선택하면 Backend가 Pending Input, 사용자와 선택 가능한 수취인을 검증한 뒤 `recipient_selection_outcome=selected`와 `to_recipient_id`만 Agent에 전달한다. 사용자가 신규 은행과 계좌번호를 입력하면 Frontend와 Backend가 직접 계좌를 조회하고 검증 결과를 표시한다. 사용자가 검증 결과를 확정한 뒤 Backend는 `recipient_selection_outcome=selected`와 `to_recipient_candidate_id`만 Agent에 전달한다. `selected`에서는 두 수취인 참조 중 정확히 하나만 존재해야 한다. 사용자가 취소하면 Backend는 두 참조 없이 `recipient_selection_outcome=cancelled`로 Agent를 재개하고 Agent는 추가 Webhook 없이 종료한다.

```text
Frontend -> Backend: 은행과 계좌번호
Backend -> Frontend: 마스킹된 검증 결과
Frontend -> Backend: 검증 결과 확정
Backend -> Agent: to_recipient_candidate_id
```

Agent는 원본 은행 코드, 계좌번호와 예금주 검증 원문을 받지 않는다. Backend가 Agent를 재개하기 전에 수취인 참조를 검증하므로 Agent가 별도 `verify_recipient` Tool API를 다시 호출하지 않는다.

##### 출금 계좌와 금액 확정

Agent는 `resolve_external_from_account`에서 Backend 계좌 목록으로 송금 가능한 출금 계좌를 확인한다. 본인송금과 동일하게 `from_account_hint`를 API의 `account_hint`에 매핑하고 `account_capability=withdraw`, `resolve_selection=true`를 고정값으로 전달한다. Backend는 `account_resolution_outcome`과 `account_ids`, `accounts` 배열을 반환한다. `resolved`이면 `account_ids`가 정확히 하나일 때만 `from_account_id`로 저장하고, `selection_required`이면 `request_external_from_account_selection`, `no_accounts`이면 `emit_external_from_accounts_empty`로 이동한다.

선택 UI의 Backend 재개 값도 `account_ids` 배열을 사용한다. `account_selection_outcome=selected`이면 배열 길이가 정확히 하나일 때만 `from_account_id=account_ids[0]`으로 저장한다. `cancelled`이면 추가 Webhook 없이 종료하며, `selected`인데 배열 길이가 1이 아니면 계약 오류로 처리한다. 별도 `selection_mode`와 단일 `account_id` 재개 필드는 사용하지 않는다.

계좌 확정 후 `check_external_transfer_amount`는 `amount`가 존재하고 정수이며 0보다 큰지만 구조적으로 확인한다. 값이 없거나 구조 오류이면 `UI-TRANSFER-AMOUNT-INPUT`으로 입력받는다. Backend는 검증된 입력을 `amount_input_outcome=submitted`, `amount`로 전달하여 Agent를 재개하고, 사용자가 취소하면 `amount_input_outcome=cancelled`로 재개한다. 실제 최소·최대 금액, 잔액과 한도는 Backend Prepare가 검증하며, Frontend 입력 형식이 잘못되면 Backend는 Agent를 재개하지 않고 같은 UI에서 재입력받는다.

##### Prepare의 의미와 결과

Prepare는 실제 송금을 실행하지 않는다. 현재 출금 계좌, 수취인과 금액으로 승인 절차를 시작할 수 있는지 Backend가 사전 검증하고, 승인 대상 조건을 Confirmation으로 고정하는 단계다. 원장 변경, 사용자 승인과 추가 인증은 Prepare에서 수행하지 않는다.

Prepare 직전 `start_external_transfer_prepare`가 `prepare_attempt`를 증가시키고 Checkpoint를 저장한다. 멱등성 키는 다음 규칙으로 생성한다.

```text
external_transfer_prepare:{execution_context_id}:{prepare_attempt}
```

기존 수취인 Prepare 요청은 다음과 같다.

```json
{
  "from_account_id": "acc_001",
  "to_recipient_id": "rcp_001",
  "amount": 50000,
  "currency": "KRW"
}
```

신규 검증 수취인은 `to_recipient_id` 대신 `to_recipient_candidate_id`를 사용한다.

```json
{
  "from_account_id": "acc_001",
  "to_recipient_candidate_id": "rcp_candidate_001",
  "amount": 50000,
  "currency": "KRW"
}
```

Backend는 다음 항목을 검증한다.

- 출금 계좌 소유권, 활성 상태와 출금 가능 여부
- 기존 수취인 또는 신규 후보의 소유자, 검증 상태와 만료
- 송금 금액과 통화
- 현재 출금 가능 잔액
- 회당·일일 이체 한도
- 수수료와 총 출금 금액
- 신규 수취인, 고액 송금과 이상 거래 위험
- 계좌, 사용자와 수취인에 적용되는 거래 제한

Prepare의 업무 결과는 HTTP 성공·실패만으로 Route를 결정하지 않고 다음 `outcome`으로 구분한다.

| outcome | 의미 | Agent 처리 |
|---|---|---|
| `ready_for_confirmation` | 현재 조건으로 승인 화면을 생성할 수 있음 | 승인 요청으로 이동 |
| `correction_required` | 사용자 입력을 바꾸면 진행할 수 있음 | 허용된 수정 UI 표시 |
| `blocked` | 현재 Workflow에서 수정으로 해결할 수 없음 | 차단 안내 후 종료 |

`ready_for_confirmation`은 송금 완료를 의미하지 않는다. Backend가 Confirmation을 만들고 승인 화면을 표시할 준비가 됐다는 뜻이다.

```text
송금 완료: 아님
사용자 승인 완료: 아님
추가 인증 완료: 아님
원장 변경: 아님
```

`correction_required` 예시는 잔액 부족, 이체 한도 초과, 수취인 후보 만료와 출금 계좌 상태 변경이다. Backend는 수정 가능한 대상만 `correction_view.allowed_change_targets`로 반환한다.

```json
{
  "reason": "insufficient_balance",
  "allowed_change_targets": [
    "from_account",
    "amount"
  ]
}
```

`blocked`는 금융사기 의심 거래 차단, 법적 지급정지와 사용자 금융거래 제한처럼 값 수정으로 해결할 수 없는 결과다. 원장 시스템 장애나 Backend Timeout 같은 기술 오류는 업무 `outcome`이 아니라 `success=false`, `error.category=technical_error`인 공통 오류로 처리한다. 동일 Prepare 요청의 통신 재시도에는 시도 번호를 증가시키지 않고 같은 멱등성 키를 사용한다.

##### 승인 화면과 수정

Backend는 `ready_for_confirmation` 결과에 `confirmation_id`와 마스킹된 승인 화면 데이터를 반환한다. 위험 경고가 필요한 경우 별도 경고 확인과 최종 승인을 두 번 요구하지 않고 하나의 승인 화면에 `variant=warning`과 `warning_codes`를 포함한다. 별도 법적 동의가 필요한 정책이 추가될 때만 독립 경고 동의 계약을 만든다.

```json
{
  "confirmation_id": "confirm_123",
  "confirmation_view": {
    "from_account": {
      "account_id": "acc_001",
      "account_alias": "생활비",
      "bank_name": "신한은행",
      "masked_account_number": "110-***-123456"
    },
    "recipient": {
      "name": "홍*동",
      "bank_name": "국민은행",
      "masked_account_number": "123-***-456789"
    },
    "amount": 50000,
    "fee": 0,
    "total_debit": 50000,
    "currency": "KRW",
    "variant": "warning",
    "warning_codes": [
      "NEW_RECIPIENT"
    ],
    "expires_at": "2026-07-14T10:05:00+09:00"
  }
}
```

승인 화면은 다음 동작을 제공한다.

```text
approve
modify_from_account
modify_recipient
modify_amount
cancel
```

Backend는 수정이나 취소 요청을 받으면 Confirmation 소유권과 상태를 검증하고 기존 Confirmation을 무효화한 뒤 Agent를 재개한다. Agent가 Confirmation 무효화 Tool API를 호출하지 않는다.

| change_target | 초기화 Step | 유지 필드 | 다음 Step |
|---|---|---|---|
| `from_account` | `reset_external_from_account` | 수취인 참조, `amount`, `correction_view` | `resolve_external_from_account` |
| `recipient` | `reset_external_recipient` | `from_account_id`, `amount`, `correction_view` | `request_recipient_selection` |
| `amount` | `reset_external_transfer_amount` | `from_account_id`, 수취인 참조, `correction_view` | `request_external_transfer_amount` |

세 초기화 Step은 공통으로 `confirmation_id`, `confirmation_view`, `approval_outcome`, `change_target`, `correction_selection_outcome`, `blocked_view`, `auth_context_id`, `auth_request_view`, `auth_status`, `auth_retry_outcome`, `input_request_id`를 제거하고 `auth_attempt=0`으로 초기화한다. 출금 계좌 수정은 `from_account_hint`, `from_account_id`, `account_resolution_outcome`, `accounts`, `account_selection_outcome`을 제거한다. 수취인 수정은 `recipient_name_hint`, `recipient_resolution_outcome`, `recipient_selection_reason`, `recipient_selection_outcome`, `to_recipient_id`, `to_recipient_candidate_id`를 제거한다. 따라서 최초 발화의 이름 힌트로 같은 수취인이 다시 자동 확정되지 않고 초기 수취인 선택 화면으로 이동한다. 금액 수정은 `amount`, `amount_input_outcome`을 제거한다.

Prepare 또는 Execute의 `correction_view.allowed_change_targets`가 하나면 `route_external_transfer_correction`이 해당 초기화 Step으로 바로 이동한다. 두 개 이상이면 `request_external_transfer_correction`에서 사용자가 하나를 선택한다. 허용 목록이 비었거나 허용되지 않은 값이 포함되면 Agent는 수정 대상을 추측하지 않고 계약 오류로 처리한다. 수정 선택이 취소되거나 승인 화면에서 취소하면 추가 취소 Webhook 없이 종료한다.

`correction_view`는 다음 계좌·수취인·금액 UI까지 유지하고 `start_external_transfer_prepare`에서 제거한다. 수정한 값으로 Prepare를 다시 호출할 때 `prepare_attempt`를 증가시켜 새로운 Confirmation을 생성한다.

##### 필수 추가 인증

사용자가 송금을 승인하면 Agent는 항상 Auth Context를 생성한다. 승인 후 바로 Execute로 이동하는 Route는 제공하지 않는다.

```text
사용자 승인
-> start_external_auth
-> create_external_auth_context
-> request_external_authentication
-> interrupt
```

Auth Context 생성 요청은 다음과 같다.

```json
{
  "confirmation_id": "confirm_123"
}
```

멱등성 키는 다음 규칙으로 생성한다.

```text
external_transfer_auth:{confirmation_id}:{auth_attempt}
```

Confirmation에 타인송금 목적, 사용자와 송금 조건이 이미 고정되어 있으므로 Agent는 `purpose`를 중복해서 보내지 않는다. Backend는 `outcome=authentication_required`, `auth_context_id`와 인증 방식·만료시각이 포함된 `auth_request_view`를 반환한다. Agent는 인증 UI Webhook을 전송한 뒤 중단하고, Frontend와 Backend가 인증을 수행한다. Backend는 `auth_context_id`와 `auth_status`를 함께 전달하여 다음 상태 중 하나로 Agent를 재개한다.

```text
verified
failed
cancelled
expired
```

Agent는 인증 상태를 조회하거나 폴링하지 않으며 PIN, 비밀번호, 생체인증 결과와 Assertion 원문을 받지 않는다. `verified`만 Execute로 이동한다. `failed` 또는 `expired`이면 `request_external_auth_retry`에서 재인증 여부를 입력받는다. `auth_retry_outcome=retry`이면 기존 `auth_context_id`, `auth_request_view`, `auth_status`, `auth_retry_outcome`을 제거하고 `auth_attempt`를 증가시켜 새 Auth Context를 생성한다. `auth_retry_outcome=cancelled`이거나 최초 인증 화면에서 `auth_status=cancelled`이면 추가 취소 Webhook 없이 종료한다. Backend가 정한 최대 인증 실패 횟수를 넘으면 Confirmation도 실행할 수 없게 처리한다.

##### Execute와 최종 결과

Execute 멱등성 키는 인증 시도별로 생성한다.

```text
external_transfer_execute:{confirmation_id}:{auth_attempt}
```

같은 인증 시도의 Timeout 또는 응답 유실 재시도에는 동일한 키와 Body를 사용한다. 재인증으로 새 `auth_context_id`가 생성된 경우에는 증가한 `auth_attempt`로 새 Execute 키를 생성한다. Backend는 멱등성 키가 달라져도 Confirmation의 미실행 상태를 검증하여 동일 Confirmation의 중복 송금을 차단한다.

Execute 요청에서 `auth_context_id`는 필수다.

```json
{
  "confirmation_id": "confirm_123",
  "auth_context_id": "auth_123"
}
```

Backend는 Confirmation의 승인, Auth Context의 인증 완료와 만료, 출금 계좌와 수취인 상태, 현재 잔액과 한도, 실행 직전 정책을 다시 검증한다. Prepare 이후 사용자 승인과 인증 사이에 잔액이나 정책이 바뀔 수 있으므로 Prepare 검증만으로 원장을 변경하지 않는다.

검증을 통과하면 Backend가 멱등성 키 선점, 원장 변경, Transaction 생성, Confirmation 실행 처리, 금융 Audit과 멱등성 결과 저장을 하나의 일관된 실행 경계에서 수행한다. Agent Workflow의 `write_audit_log` Step은 사용하지 않는다.

Execute가 완료되면 `emit_external_transfer_result`는 Execute 응답의 `transaction_id`, `completed_at`과 Prepare에서 저장한 `confirmation_view`의 `from_account`, `recipient`, `amount`, `currency`를 조합해 완료 Webhook을 전송한다. Agent는 완료 화면을 위해 출금 계좌나 수취인을 다시 조회하거나 표시정보를 새로 만들지 않는다. `fee`, `total_debit`, `warning_codes`, `expires_at`처럼 승인 확인에는 필요하지만 완료 결과 계약에 포함되지 않은 필드는 전달하지 않는다.

```json
{
  "outcome": "completed",
  "transaction_id": "txn_123",
  "completed_at": "2026-07-15T10:04:00+09:00",
  "from_account": {
    "account_id": "acc_001",
    "account_alias": "생활비",
    "bank_name": "신한은행",
    "masked_account_number": "110-***-123456"
  },
  "recipient": {
    "name": "홍*동",
    "bank_name": "국민은행",
    "masked_account_number": "123-***-456789"
  },
  "amount": 50000,
  "currency": "KRW"
}
```

Execute에서 수정 가능한 업무 오류가 발생하면 Confirmation과 Auth Context를 재사용할 수 없게 처리하고 `outcome=correction_required`와 `correction_view`를 반환한다. Agent는 Backend가 허용한 수정 Route로 이동하고 Prepare, 승인과 추가 인증을 모두 다시 수행한다. 정책 차단은 `outcome=blocked`로 종료하며 기술 오류의 통신 재시도에는 같은 Execute 멱등성 키를 사용한다.

Prepare, Auth Context 생성 또는 Execute가 `outcome=blocked`를 반환하면 Agent는 자동 재시도하지 않는다. Backend가 제공한 사용자 표시용 `blocked_view`를 `emit_external_transfer_blocked` Webhook에 그대로 전달하고 종료한다. Agent는 내부 정책 코드나 차단 사유를 사용자 문장으로 다시 해석하지 않는다. `success=false`, `error.category=technical_error`는 차단과 구분하며 공통 조건에 해당할 때만 동일 요청을 최대 1회 재시도한 뒤 `emit_external_transfer_error`로 종료한다.

Confirmation은 아직 승인된 유효 상태지만 Auth Context만 만료된 경우 Backend는 `outcome=reauthentication_required`를 반환한다. Agent는 `confirmation_id`, `from_account_id`, 수취인 참조, `amount`, `currency`를 유지하고 `auth_context_id`, `auth_request_view`, `auth_status`, `auth_retry_outcome`만 제거한 뒤 `start_external_auth`로 이동한다. `start_external_auth`는 `auth_attempt`를 증가시켜 새 Auth Context를 생성하고, 인증 성공 후 Prepare와 사용자 승인을 반복하지 않고 Execute를 다시 호출한다. Confirmation도 만료되었거나 무효화되었으면 재인증만으로 실행하지 않고 새로운 Prepare와 사용자 승인을 수행한다.

Workflow Step은 다음과 같이 구성한다.

```text
extract_external_transfer_slots

recipient_name_hint가 있으면 resolve_recipient_hint
-> resolved이면 to_recipient_id 저장
-> selection_required이면 request_recipient_selection
recipient_name_hint가 없으면 request_recipient_selection
-> selected이면 수취인 참조 하나를 저장하고 resolve_external_from_account
-> cancelled이면 추가 Webhook 없이 END
-> selected인데 수취인 참조가 정확히 하나가 아니면 emit_external_transfer_error

resolve_external_from_account
-> 출금 계좌 자동 확정, request_external_from_account_selection 또는 emit_external_from_accounts_empty
-> check_external_transfer_amount
-> amount가 없거나 구조 오류이면 request_external_transfer_amount

start_external_transfer_prepare
-> prepare_external_transfer

ready_for_confirmation
-> request_external_transfer_approval
-> interrupt

correction_required
-> route_external_transfer_correction
-> 수정 대상이 하나면 해당 초기화 Step
-> 수정 대상이 복수이면 request_external_transfer_correction
-> selected이면 선택한 초기화 Step, cancelled이면 END
-> start_external_transfer_prepare

blocked
-> emit_external_transfer_blocked
-> END

success=false / technical_error
-> 공통 조건에 해당하면 동일 멱등성 키로 최대 1회 재시도
-> 재시도 실패 또는 재시도 대상이 아니면 emit_external_transfer_error

승인 화면 수정
-> from_account이면 reset_external_from_account -> resolve_external_from_account
-> recipient이면 reset_external_recipient -> request_recipient_selection
-> amount이면 reset_external_transfer_amount -> request_external_transfer_amount
-> start_external_transfer_prepare

승인 화면 취소
-> 승인 관련 State 제거
-> END

승인 완료
-> start_external_auth
-> create_external_auth_context
-> request_external_authentication
-> interrupt

인증 성공
-> execute_external_transfer

인증 실패 또는 만료
-> request_external_auth_retry
-> auth_retry_outcome=retry이면 기존 인증 State 제거
-> auth_attempt 증가 후 새 Auth Context 생성
-> auth_retry_outcome=cancelled이면 추가 Webhook 없이 END

인증 cancelled
-> 추가 Webhook 없이 END

Execute completed
-> emit_external_transfer_result
-> END

Execute correction_required
-> Confirmation과 인증 State 제거
-> route_external_transfer_correction
-> 단일 대상이면 해당 초기화 Step
-> 복수 대상이면 request_external_transfer_correction
-> selected이면 선택한 초기화 Step, cancelled이면 END
-> start_external_transfer_prepare

Execute reauthentication_required
-> confirmation_id와 송금 조건 유지
-> 기존 인증 State만 제거
-> auth_attempt 증가 후 새 Auth Context 생성
-> 인증 성공 후 Prepare와 승인 없이 Execute 재호출
-> start_external_auth

Execute blocked
-> emit_external_transfer_blocked
-> END

Execute success=false / technical_error
-> 공통 조건에 해당하면 동일 멱등성 키로 최대 1회 재시도
-> 재시도 실패 또는 재시도 대상이 아니면 emit_external_transfer_error
```

Step State Mapping은 다음과 같다.

| step_id | direction | state_key | contract_field_path |
|---|---|---|---|
| `extract_external_transfer_slots` | `output` | `from_account_hint` | `agent.extracted.from_account_hint` |
| `extract_external_transfer_slots` | `output` | `recipient_name_hint` | `agent.extracted.recipient_name_hint` |
| `extract_external_transfer_slots` | `output` | `amount` | `agent.extracted.amount` |
| `resolve_recipient_hint` | `input` | `recipient_name_hint` | `request.recipient_name_hint` |
| `resolve_recipient_hint` | `output` | `recipient_resolution_outcome` | `response.data.outcome` |
| `resolve_recipient_hint` | `output` | `recipient_selection_reason` | `response.data.selection_reason` |
| `resolve_recipient_hint` | `output` | `to_recipient_id` | `response.data.to_recipient_id` |
| `request_recipient_selection` | `input` | `recipient_name_hint` | `webhook.metadata.ui.payload.recipient_name_hint` |
| `request_recipient_selection` | `input` | `recipient_selection_reason` | `webhook.metadata.ui.payload.recipient_selection_reason` |
| `request_recipient_selection` | `output` | `recipient_selection_outcome` | `resume.value.recipient_selection_outcome` |
| `request_recipient_selection` | `output` | `to_recipient_id` | `resume.value.to_recipient_id` |
| `request_recipient_selection` | `output` | `to_recipient_candidate_id` | `resume.value.to_recipient_candidate_id` |
| `resolve_external_from_account` | `input` | `from_account_hint` | `query.account_hint` |
| `resolve_external_from_account` | `output` | `account_resolution_outcome` | `response.data.account_resolution_outcome` |
| `resolve_external_from_account` | `output` | `accounts` | `response.data.accounts` |
| `resolve_external_from_account` | `output` | `from_account_id` | `response.data.account_ids[0]` |
| `request_external_from_account_selection` | `input` | `accounts` | `webhook.metadata.ui.payload.accounts` |
| `request_external_from_account_selection` | `output` | `account_selection_outcome` | `resume.value.account_selection_outcome` |
| `request_external_from_account_selection` | `output` | `from_account_id` | `resume.value.account_ids[0]` |
| `emit_external_from_accounts_empty` | `input` | `accounts` | `webhook.metadata.ui.payload.accounts` |
| `check_external_transfer_amount` | `input` | `amount` | `agent.state.amount` |
| `request_external_transfer_amount` | `output` | `amount_input_outcome` | `resume.value.amount_input_outcome` |
| `request_external_transfer_amount` | `output` | `amount` | `resume.value.amount` |
| `start_external_transfer_prepare` | `output` | `prepare_attempt` | `agent.state.prepare_attempt` |
| `prepare_external_transfer` | `input` | `from_account_id` | `request.from_account_id` |
| `prepare_external_transfer` | `input` | `to_recipient_id` | `request.to_recipient_id` |
| `prepare_external_transfer` | `input` | `to_recipient_candidate_id` | `request.to_recipient_candidate_id` |
| `prepare_external_transfer` | `input` | `amount` | `request.amount` |
| `prepare_external_transfer` | `input` | `currency` | `request.currency` |
| `prepare_external_transfer` | `input` | `prepare_attempt` | `header.Idempotency-Key` |
| `prepare_external_transfer` | `output` | `confirmation_id` | `response.data.confirmation_id` |
| `prepare_external_transfer` | `output` | `confirmation_view` | `response.data.confirmation_view` |
| `prepare_external_transfer` | `output` | `correction_view` | `response.data.correction_view` |
| `prepare_external_transfer` | `output` | `blocked_view` | `response.data.blocked_view` |
| `request_external_transfer_approval` | `output` | `approval_outcome` | `resume.value.approval_outcome` |
| `request_external_transfer_approval` | `output` | `change_target` | `resume.value.change_target` |
| `route_external_transfer_correction` | `input` | `correction_view` | `agent.state.correction_view` |
| `request_external_transfer_correction` | `input` | `correction_view` | `webhook.metadata.ui.payload` |
| `request_external_transfer_correction` | `output` | `correction_selection_outcome` | `resume.value.correction_selection_outcome` |
| `request_external_transfer_correction` | `output` | `change_target` | `resume.value.change_target` |
| `reset_external_from_account` | `output` | `from_account_hint` | `agent.state.from_account_hint=null` |
| `reset_external_from_account` | `output` | `from_account_id` | `agent.state.from_account_id=null` |
| `reset_external_recipient` | `output` | `recipient_name_hint` | `agent.state.recipient_name_hint=null` |
| `reset_external_recipient` | `output` | `to_recipient_id` | `agent.state.to_recipient_id=null` |
| `reset_external_recipient` | `output` | `to_recipient_candidate_id` | `agent.state.to_recipient_candidate_id=null` |
| `reset_external_transfer_amount` | `output` | `amount` | `agent.state.amount=null` |
| `reset_external_transfer_amount` | `output` | `amount_input_outcome` | `agent.state.amount_input_outcome=null` |
| `create_external_auth_context` | `input` | `confirmation_id` | `request.confirmation_id` |
| `create_external_auth_context` | `input` | `auth_attempt` | `header.Idempotency-Key` |
| `create_external_auth_context` | `output` | `auth_context_id` | `response.data.auth_context_id` |
| `create_external_auth_context` | `output` | `auth_request_view` | `response.data.auth_request_view` |
| `request_external_authentication` | `output` | `auth_status` | `resume.value.auth_status` |
| `request_external_auth_retry` | `output` | `auth_retry_outcome` | `resume.value.auth_retry_outcome` |
| `execute_external_transfer` | `input` | `confirmation_id` | `request.confirmation_id` |
| `execute_external_transfer` | `input` | `auth_context_id` | `request.auth_context_id` |
| `execute_external_transfer` | `input` | `auth_attempt` | `header.Idempotency-Key` |
| `execute_external_transfer` | `output` | `correction_view` | `response.data.correction_view` |
| `execute_external_transfer` | `output` | `blocked_view` | `response.data.blocked_view` |
| `execute_external_transfer` | `output` | `transaction_id` | `response.data.transaction_id` |
| `execute_external_transfer` | `output` | `completed_at` | `response.data.completed_at` |
| `emit_external_transfer_result` | `input` | `transaction_id` | `webhook.metadata.ui.payload.transaction_id` |
| `emit_external_transfer_result` | `input` | `completed_at` | `webhook.metadata.ui.payload.completed_at` |
| `emit_external_transfer_result` | `input` | `confirmation_view` | `webhook.metadata.ui.payload.from_account` |
| `emit_external_transfer_result` | `input` | `confirmation_view` | `webhook.metadata.ui.payload.recipient` |
| `emit_external_transfer_result` | `input` | `confirmation_view` | `webhook.metadata.ui.payload.amount` |
| `emit_external_transfer_result` | `input` | `confirmation_view` | `webhook.metadata.ui.payload.currency` |
| `emit_external_transfer_blocked` | `input` | `blocked_view` | `webhook.metadata.ui.payload` |

계약 매핑은 다음과 같다.

| step_id | interaction_mode | contract_id |
|---|---|---|
| `extract_external_transfer_slots` | `agent_internal` | 없음 |
| `resolve_recipient_hint` | `backend_tool_api` | `API-RECIPIENT-RESOLVE` |
| `request_recipient_selection` | `webhook_then_resume` | `UI-RECIPIENT-SELECT` |
| `resolve_external_from_account` | `backend_tool_api` | `API-ACCOUNT-LIST` |
| `request_external_from_account_selection` | `webhook_then_resume` | `UI-EXTERNAL-TRANSFER-FROM-ACCOUNT` |
| `emit_external_from_accounts_empty` | `webhook` | `UI-EXTERNAL-TRANSFER-FROM-ACCOUNT` |
| `check_external_transfer_amount` | `agent_internal` | 없음 |
| `request_external_transfer_amount` | `webhook_then_resume` | `UI-TRANSFER-AMOUNT-INPUT` |
| `start_external_transfer_prepare` | `agent_internal` | 없음 |
| `prepare_external_transfer` | `backend_tool_api` | `API-EXTERNAL-TRANSFER-PREPARE` |
| `request_external_transfer_approval` | `webhook_then_resume` | `UI-EXTERNAL-TRANSFER-CONFIRMATION` |
| `reset_external_from_account` | `agent_internal` | 없음 |
| `reset_external_recipient` | `agent_internal` | 없음 |
| `reset_external_transfer_amount` | `agent_internal` | 없음 |
| `route_external_transfer_correction` | `agent_internal` | 없음 |
| `request_external_transfer_correction` | `webhook_then_resume` | `UI-EXTERNAL-TRANSFER-CORRECTION` |
| `start_external_auth` | `agent_internal` | 없음 |
| `create_external_auth_context` | `backend_tool_api` | `API-AUTH-CONTEXT-CREATE` |
| `request_external_authentication` | `webhook_then_resume` | `UI-EXTERNAL-TRANSFER-AUTH` |
| `request_external_auth_retry` | `webhook_then_resume` | `UI-EXTERNAL-TRANSFER-AUTH-RETRY` |
| `execute_external_transfer` | `backend_tool_api` | `API-EXTERNAL-TRANSFER-EXECUTE` |
| `emit_external_transfer_result` | `webhook` | `UI-EXTERNAL-TRANSFER-RESULT` |
| `emit_external_transfer_blocked` | `webhook` | `UI-TRANSFER-BLOCKED` |
| `emit_external_transfer_error` | `webhook` | `UI-COMMON-ERROR` |

### Workflow Data Schema

Workflow Data Schema는 State 필드 정의의 정본이다. 각 Workflow에서 사용하는 필드의 이름, 타입, null 허용 여부와 저장 정책을 한 번만 정의한다.

| 컬럼 | 설명 |
|---|---|
| `workflow_id` | State를 사용하는 Workflow |
| `state_key` | Agent State 필드명 |
| `data_type` | 문자열, 정수, 객체, 목록 등 |
| `nullable` | null 허용 여부 |
| `default_value` | 초기 기본값 |
| `description` | 업무 의미 |
| `source_type` | 사용자 입력, Backend API, Agent 내부 처리 등 |
| `sensitive` | 민감정보 여부 |
| `persist_in_agent_state` | Agent State 저장 가능 여부 |
| `persistence_scope` | 입력 대기, Workflow, 결과 등 보존 범위 |

### Step State Mapping

Step State Mapping은 Workflow Step과 State의 입력·출력 관계를 정의하는 정본이다. 하나의 관계를 한 행으로 관리하며 쉼표로 연결한 생산자·소비자 목록을 정본으로 사용하지 않는다.

| 컬럼 | 설명 |
|---|---|
| `workflow_id` | 대상 Workflow |
| `step_id` | State를 읽거나 쓰는 Step |
| `direction` | `input` 또는 `output` |
| `state_key` | Workflow Data Schema에 정의된 필드 |
| `contract_id` | 연결된 API 또는 UI 계약 ID |
| `contract_field_path` | 요청, 응답 또는 resume의 필드 경로 |
| `required_at_step` | 해당 Step에서 필수인지 여부 |
| `mapping_rule` | 조건부 매핑이나 정규화 규칙 |

예시는 다음과 같다.

| workflow_id | step_id | direction | state_key | contract_field_path |
|---|---|---|---|---|
| `wf_external_transfer` | `request_recipient_selection` | `output` | `to_recipient_id` | `resume.value.to_recipient_id` |
| `wf_external_transfer` | `request_recipient_selection` | `output` | `to_recipient_candidate_id` | `resume.value.to_recipient_candidate_id` |
| `wf_external_transfer` | `request_transfer_amount` | `output` | `amount` | `resume.value.amount` |
| `wf_external_transfer` | `request_transfer_amount` | `output` | `currency` | `resume.value.currency` |
| `wf_external_transfer` | `prepare_external_transfer` | `input` | `amount` | `request.amount` |
| `wf_external_transfer` | `prepare_external_transfer` | `output` | `confirmation_id` | `response.data.confirmation_id` |

### State 제약조건

여러 State 필드 사이의 조건은 별도 제약조건으로 관리한다. 예를 들어 외부 송금 Prepare 전에는 `to_recipient_id`와 `to_recipient_candidate_id` 중 정확히 하나만 존재해야 한다.

| workflow_id | constraint_id | constraint_type | state_keys | 적용 시점 |
|---|---|---|---|---|
| `wf_external_transfer` | `recipient_reference` | `exactly_one` | `to_recipient_id`, `to_recipient_candidate_id` | `prepare_external_transfer` 호출 전 |

Workflow Step 탭의 `input_state_keys`, `output_state_keys`는 Step State Mapping을 집계하여 생성하는 읽기 전용 요약 컬럼이다. 두 컬럼을 State 정의 또는 Step·State 관계의 정본으로 직접 편집하지 않는다.

### 산출물

- 공통 데이터 스키마 문서
- 변수명 사전
- Workflow별 State Data Schema 초안
- Step State Mapping 초안

### 완료 기준

- 하나의 필드에 여러 타입이 들어가지 않음
- API, Webhook, resume, Agent State 간 매핑이 명시됨
- 민감정보 저장 금지 필드가 구분됨
- 모든 Step의 입출력 State가 Step State Mapping에 한 행씩 정의됨
- Workflow Step의 입출력 요약 컬럼이 Mapping과 일치함

---

## 6.3 단계 2. Agent Tool API 명세 재작성

`agent-tools-api-spec.md`를 단계 1의 변수명과 데이터 스키마에 맞춘다.

### Endpoint별 필수 항목

- 호출 Workflow
- 호출 Step
- HTTP Method
- Path
- 공통 Header
- 요청 필드
- 응답 필드
- 성공 Route
- 오류 Route
- 오류 코드
- 멱등성 여부
- Backend 검증 항목
- Agent State 저장 필드
- 민감정보 처리 원칙

### API 분류

#### 조회

- 계좌 목록
- 잔액
- 거래내역
- 거래 합계
- 수취인 이름 힌트 자동 확정

#### Prepare

- 타인송금 Prepare
- 본인 계좌 간 이체 Prepare
- 기본 출금 계좌 변경 Prepare
- 계좌 별칭 변경 Prepare

#### 비동기 상호작용 준비

- Auth Context 생성

#### Execute

- 타인송금 Execute
- 본인 계좌 간 이체 Execute
- 기본 출금 계좌 변경 Execute
- 계좌 별칭 변경 Execute

### 제거 또는 축소 검토 대상

- 수취인 참조 검증 API
- Confirmation 상태 조회 API
- Auth Context 상태 조회 API
- Agent 금융 Audit 기록 API

Confirmation과 Auth Context 조회 API는 현재 계약에서 이미 제거한 상태를 유지한다.

### 산출물

- 갱신된 `agent-tools-api-spec.md`
- 공통 요청·응답 Schema
- 오류 코드 표
- Workflow Step과 API 매핑표

### 완료 기준

- 모든 Backend Tool API가 하나 이상의 Workflow Step에 연결됨
- 모든 API 요청 필드가 변수명 사전과 일치함
- 사용되지 않는 Endpoint가 없음

---

## 6.4 단계 3. Tool 목록 재분류

Tool을 다음 세 종류로 분리한다.

### A. Agent 내부 Tool

외부 호출 없이 Agent 내부에서 실행한다.

```text
extract_*_slots
check_*_input
normalize_period
match_workflow
route_*
generate_*_response
```

### B. Backend Tool API Adapter

Backend Agent Tool API만 호출한다.

```text
fetch_accounts
fetch_balance
fetch_transactions
fetch_transaction_summary
resolve_recipient_hint
prepare_external_transfer
execute_external_transfer
prepare_internal_transfer
execute_internal_transfer
prepare_default_account_change
execute_default_account_change
prepare_account_alias_change
execute_account_alias_change
create_auth_context
```

### C. Webhook·HITL Tool

Backend Webhook으로 이벤트를 보내고 필요하면 Workflow를 중단한다.

```text
request_input
request_approval
request_authentication
emit_component
emit_status
emit_done
emit_error
```

`ask_recipient`, `ask_amount`, `ask_period`를 각각 별도 네트워크 코드로 만들지 않고 공통 `request_input` 실행기가 `input_request_id`, `ui_contract_id`, Payload를 받아 처리하도록 구현할 수 있다.

Backend Tool API Adapter는 공통 요청 Schema를 사용하여 필수 필드, 타입, 상호 배타 조건과 민감정보 포함 여부를 검사한다. 이 검사는 Tool로 등록하거나 Workflow Step으로 노출하지 않는다.

### Tool 이름 변경 후보

| 기존 이름 | 변경 후보 | 이유 |
| --- | --- | --- |
| `check_balance` | 송금 Workflow에서 제거 | 송금 가능 잔액은 Backend Prepare와 Execute가 검증 |
| `run_transfer_guardrail` | `prepare_external_transfer` | 실제 책임이 Backend Prepare 호출 |
| `run_pre_execution_guardrail` | 제거 | 최종 금융 검증은 Backend Execute가 담당 |
| `sum_transactions` | `fetch_transaction_summary` | Agent 내부 합산을 하지 않음 |
| `apply_default_account` | `execute_default_account_change` | Backend Execute 호출임을 명확히 표시 |
| `apply_account_alias` | `execute_account_alias_change` | Backend Execute 호출임을 명확히 표시 |
| `authenticate_user` | `create_auth_context`, `request_authentication` | API 호출과 UI 대기를 분리 |

### 산출물

- Tool Catalog
- Tool별 입력·출력 State
- Tool별 실행 방식
- Tool과 Backend API 매핑
- Tool Registry 변경 목록

### 완료 기준

- 각 Tool이 Agent 내부, Backend API, Webhook 중 하나로 분류됨
- 하나의 Tool이 금융 검증과 UI 요청을 동시에 담당하지 않음
- 원장 직접 호출 Tool이 없음

---

## 6.5 단계 4. Workflow 관리시트 전면 재작성

단계 1부터 3까지 확정된 계약으로 관리시트를 다시 만든다.

관리시트는 사람이 Workflow를 이해하고 검토하는 정본으로 사용한다. API와 UI의 상세 요청·응답 Schema는 Markdown 계약을 정본으로 유지하며, 코드 생성에 필요한 구조화와 매핑은 Agent 개발 과정에서 생성·검증한다.

### 탭 구성

| 탭 | 역할 | 편집 방식 |
|---|---|---|
| `Workflow Catalog` | Workflow 목적, 유형, 위험등급과 승인·인증 정책 | 직접 편집 |
| `Workflow Steps` | Step 실행 방식, Tool과 계약 연결 | 직접 편집 |
| `Workflow Routes` | 사람이 읽는 조건과 다음 Step | 직접 편집 |
| `Workflow Data Schema` | 공통·Workflow State, 보존과 로그 정책 | 직접 편집 |
| `Step Data Mapping` | Step과 State, 계약 필드 경로 연결 | Agent가 생성하고 사람이 검토 |
| `Contract Registry` | API·UI 계약 색인 | Markdown 계약에서 생성 |
| `Contract Mapping` | Workflow Step과 계약 연결 View | 자동 생성 |
| `Enum Registry` | 드롭다운과 계약 Enum 검증값 | 설정·Markdown 계약에서 생성 |

### Workflow Catalog

```text
workflow_id
workflow_name
workflow_type
description
example_utterances
entry_step_id
max_risk_level
approval_policy
auth_policy
workflow_version
status
notes
```

`workflow_type`은 `global`, `inquiry`, `setting_change`, `transfer`를 사용한다. 조회 Workflow는 승인과 추가 인증을 요구하지 않는다. 설정 변경은 승인을 요구하고 추가 인증은 요구하지 않는다. 본인송금과 타인송금은 모두 승인과 추가 인증을 요구한다.

### Workflow Steps 직접 편집 컬럼

```text
workflow_id
step_order
step_id
step_name
step_purpose
interaction_mode
tool_id
contract_id
step_risk_level
status
notes
```

`task_id`는 새 관리시트에서 사용하지 않는다. Step의 업무 목적은 `step_purpose`, 실제 실행기 또는 Adapter는 `tool_id`로 관리한다. 기존 `tasks.yaml`의 존치·통합·제거는 관리시트 전환 이후 별도 마이그레이션으로 처리한다.

`api_contract_id`와 `ui_contract_id`는 `contract_id` 하나로 통합한다. `backend_tool_api`는 `API-*`, `webhook`과 `webhook_then_resume`은 `UI-*` 계약만 참조한다.

### Workflow Steps 자동 표시 컬럼

```text
external_action
input_state_keys
output_state_keys
route_summary
validation_result
```

`external_action`은 Backend Tool API이면 `POST /transfers/external:prepare`, UI 요청이면 `need_input · recipient_select`처럼 한 칸에 요약한다. 상세 Method, Path, UI Type과 Resume Schema는 Contract Registry와 원본 Markdown에서 확인한다.

### `interaction_mode` Enum

```text
agent_internal
backend_tool_api
webhook
webhook_then_resume
```

`backend_tool_api_then_webhook`, `execute_then_webhook` 같은 복합 Step은 만들지 않는다. Backend Tool API 호출 결과를 State에 저장한 후 별도의 Webhook Step을 실행한다.

### 복합 Step 분리 예시

```text
resolve_recipient_hint
- backend_tool_api
- POST /recipients:resolve

request_recipient_selection
- webhook_then_resume
- need_input
- recipient_select
```

```text
prepare_internal_transfer
- backend_tool_api
- POST /transfers/internal:prepare

review_internal_transfer
- webhook_then_resume
- need_approval
```

```text
create_auth_context
- backend_tool_api
- POST /auth-contexts

request_authentication
- webhook_then_resume
- auth_request
```

### Workflow Routes

Route는 코드식이나 비교 연산자를 사람이 직접 작성하지 않는다. 어떤 경우에 어디로 이동하는지를 자연어로 설명하고, 구현 시 API·UI 계약과 Workflow Data Schema를 기준으로 구조화한다.

```text
workflow_id
from_step_id
route_name
condition_description
to_step_id
status
notes
```

예시는 다음과 같다.

| from_step_id | route_name | condition_description | to_step_id |
|---|---|---|---|
| `prepare_external_transfer` | 승인 진행 | Backend가 송금 조건을 확인하고 승인 화면을 만들 수 있는 경우 | `request_external_transfer_approval` |
| `prepare_external_transfer` | 정보 수정 | 출금 계좌, 수취인 또는 금액을 수정하면 진행할 수 있는 경우 | `request_external_transfer_correction` |
| `prepare_external_transfer` | 진행 차단 | 입력을 수정해도 해결할 수 없는 금융거래 제한인 경우 | `emit_external_transfer_blocked` |
| `prepare_external_transfer` | 처리 오류 | Backend 장애로 금융 판단을 완료하지 못한 경우 | `emit_external_transfer_error` |

구현 시 Agent가 `condition_description`, Step의 `contract_id`, 계약 Outcome과 State Mapping을 함께 읽어 LangGraph 조건 분기를 생성한다. 둘 이상의 의미로 해석되는 조건만 사용자에게 다시 확인한다.

### Workflow Data Schema

공통 State와 Workflow 전용 State를 한 탭에서 관리하고 `schema_scope`로 구분한다.

```text
schema_scope
workflow_id
state_key
data_type
nullable
default_value
description
retention_scope
clear_when
sensitive
log_policy
notes
```

`schema_scope`은 `common`, `workflow`를 사용한다. `retention_scope`은 `interaction`, `workflow`, `result`를 사용하고, `log_policy`는 `allow`, `masked`, `exclude`를 사용한다.

Data Schema에 정의된 값은 Agent State에 저장 가능한 값으로 본다. 전체 계좌번호, PIN, 생체인증 Assertion과 인증 원문처럼 저장해서는 안 되는 값은 Data Schema에 등록하지 않으므로 `persist_in_agent_state` 컬럼을 별도로 사용하지 않는다.

### Step Data Mapping

State와 API·Webhook·resume의 필드 위치를 하나의 관계당 한 행으로 관리한다. 실제 매핑 행은 Agent가 계약 문서와 Workflow 설계를 읽어 작성하며, 사람은 `mapping_description`의 업무 의미를 검토한다.

```text
workflow_id
step_id
direction
state_key
contract_field_path
required_at_step
mapping_description
notes
validation_result
```

외부 계약 필드 경로는 다음 Prefix를 사용한다.

```text
query.
request.
response.data.
webhook.metadata.ui.payload.
resume.value.
```

Agent 내부 Step은 `contract_field_path`를 비워두고 `mapping_description`으로 입력·출력 의미를 설명할 수 있다. `contract_id`는 Workflow Steps에서 가져오므로 이 탭에서 중복 편집하지 않는다.

### Contract Registry와 Contract Mapping

Contract Registry는 계약의 상세 Schema를 복사하지 않고 원본 문서의 색인만 관리한다.

```text
contract_id
contract_type
contract_name
transport_target
contract_summary
source_document
source_section
contract_version
status
```

`contract_type`은 `agent_tool_api`, `ui_hitl`을 사용한다. API 계약은 `agent-tools-api-spec.md`, UI 계약은 UI·HITL 계약서를 정본으로 한다.

Contract Mapping은 Workflow Steps와 Contract Registry를 결합한 읽기 전용 View다. `workflow_id`, `step_id`, `interaction_mode`, `contract_id`, `transport_target`, `contract_version`을 표시한다.

### Enum Registry

Enum Registry에는 관리시트 드롭다운과 계약값 검증에 필요한 값만 관리한다.

```text
enum_group
enum_value
display_name
description
source_type
source_document
status
sort_order
```

`source_type=sheet_rule`인 `interaction_mode`, 위험등급, 보존·로그 정책은 시트 생성 설정에서 관리한다. `source_type=api_contract`, `ui_contract`인 Outcome, 승인 결정과 인증 상태는 Markdown 계약에서 동기화한다.

### 관리시트에서 제거할 항목

- 모든 `task_id`
- `execution_owner`
- `api_contract_id`, `ui_contract_id` 분리 컬럼
- `frontend_endpoint`
- `success_route`, `failure_route`
- 중복 표시용 Method, Path, UI Type과 Webhook 세부 컬럼
- `output_data_key`
- `persist_in_agent_state`
- UI 입력 뒤 중복되는 `verify_recipient_account`
- 송금 Workflow의 `check_balance`
- 송금 Workflow의 `run_pre_execution_guardrail`
- 모든 `write_audit_log`
- 모든 `log_id`
- 사용되지 않는 레거시 Tool
- 원장 직접 호출 설명
- Frontend 직접 호출 설명
- 역할이 불명확한 상태값

### 관리시트와 Markdown 연동

- 승인된 Google Spreadsheet를 XLSX 또는 CSV Snapshot으로 내보낸다.
- API·UI Markdown의 `yaml contract` 블록을 계약 Registry로 읽는다.
- 관리시트의 `contract_id`를 Registry와 교차 검증한다.
- 참조 ID와 계약 버전이 모두 유효할 때만 YAML을 생성한다.
- 검증 실패 시 기존 YAML을 변경하지 않고 오류 보고서를 생성한다.

### 산출물

- 새 Workflow 관리시트
- 관리시트 생성 스크립트
- Markdown 계약 동기화 결과
- Step Data Mapping과 Contract Mapping
- 관리시트 dry-run 결과

### 완료 기준

- Workflow Step 한 행만 보고 실행 방식과 호출 API를 알 수 있음
- 하나의 Step에 Backend Tool API 호출과 Webhook 전송이 함께 포함되지 않음
- `task_id` 없이 `step_purpose`와 `tool_id`로 실행 의미를 확인할 수 있음
- 모든 Route의 출발 Step과 도착 Step이 존재함
- 제거된 Step을 가리키는 Route가 없음
- 모든 Step Data Mapping의 State가 Workflow Data Schema에 존재함
- 모든 `contract_id`가 Contract Registry에 존재하고 상호작용 방식과 유형이 일치함
- 관리시트로 YAML을 생성할 수 있음
- Google Spreadsheet Snapshot과 Markdown 계약의 참조 ID 및 계약 버전이 일치함
- 계약 검증 실패 시 YAML이 생성되거나 변경되지 않음

---

## 6.6 단계 5. Backend 필요 기능 전달서 작성

Agent 팀은 Endpoint 목록과 함께 Workflow에 필요한 상태 전이, 검증 결과와 호출 시점을 전달한다. Backend 내부 파일 구조, 저장 모델과 구현 방식은 지정하지 않는다.

### Agent가 제공할 실행 API

```http
POST /internal/v1/executions
POST /internal/v1/executions/{agent_thread_id}/resume
```

### Frontend 입력 API

```http
POST /api/v1/agent/input
POST /api/v1/agent/approve
POST /api/v1/recipient-candidates:verify
추가 인증 완료 API
```

거래내역 첫 페이지 이후의 목록 탐색은 Agent를 resume하지 않고 Frontend용 Backend API로 처리한다.

```http
GET /api/v1/transactions/queries/{transaction_query_id}?cursor={next_cursor}
```

### Agent Webhook

```http
POST /api/v1/webhooks/agent
```

필요한 이벤트는 다음과 같다.

```text
status
token
tool_call
component
need_input
need_approval
done
error
```

### Backend에 요청할 외부 기능과 보장

- 유효한 Execution Context 발급과 검증
- Agent Thread와 Chat Session 연결 관계 보장
- 활성 입력 대기 요청과 사용자 회신의 정확한 매칭
- `input_request_id`와 저장된 `ui_contract_id`를 이용한 입력 Schema 검증
- Confirmation 생성, 승인, 거절, 만료, 무효화와 실행 완료 상태 보장
- Auth Context 생성과 검증된 인증 결과 상태 보장
- Backend에서 Agent로 input, approval, auth resume
- 수취인 후보 검증과 만료
- 동일 멱등성 요청의 중복 실행 방지와 충돌 응답
- 금융 처리 사실에 대한 Backend Audit 보장
- 공개 오류 코드
- 계좌번호와 개인정보 마스킹
- Webhook 재전송 중복 제거
- 단일·복수 계좌를 `account_ids` 배열로 처리하는 배치 잔액 조회 API
- 복수 계좌를 `account_ids` 배열로 처리하고 `transaction_query_id`를 발급하는 거래내역 조회 API
- `transaction_query_id`의 사용자, 조회 조건, Cursor와 만료 연결 보장
- 복수 계좌와 `summary_type`을 받아 원장 거래를 직접 집계하는 거래 합계 API
- `spending`, `income` 분류와 본인 계좌 간 이체 제외 정책

구체적인 저장 방식과 내부 서비스 구성은 Backend 팀이 결정한다.

### 산출물

- Backend 필요 기능 전달서
- Endpoint별 요청·응답 예시
- 필요한 상태 전이와 외부 보장
- Agent Route와 오류 코드 매핑
- OpenAPI 또는 JSON Schema 초안

### 완료 기준

- Backend 담당자가 추가 질문 없이 요청·응답 Schema를 구현할 수 있음
- 사용자 입력, 승인, 인증의 전체 resume 흐름이 포함됨
- 금융 감사와 Agent Trace의 차이가 명시됨

---

## 6.7 단계 6. Agent 코드 구현

계약과 관리시트가 확정된 이후 Agent 코드를 변경한다.

### 공통 State

- Pydantic 기반 Agent State 모델
- Execution Context 모델
- Workflow별 State 모델
- resume Payload 모델
- 민감정보 저장 방지 검증

### 통신 Client

- Backend Agent Tool API Client
- Agent Webhook Client
- timeout과 재시도 정책
- `Idempotency-Key` 관리
- Backend 공통 오류 변환

### Workflow 실행

- LangGraph Checkpointer
- `interrupt()` 기반 입력 대기
- input, approval, auth resume
- 관리시트 기반 Workflow 생성
- Backend 오류 코드 기반 Route
- 수정 요청 시 Confirmation 무효화 후 Prepare 재실행

### Tool

- Agent 내부 Tool 구현
- Backend Tool API Adapter 구현
- 공통 Webhook·HITL Tool 구현
- Tool Registry 갱신
- 기존 `bank_client` 직접 호출 제거
- `write_audit_log` Workflow Tool 제거

### 관측

- Step 시작과 종료 Trace
- Tool 호출 Trace
- Route 결정 Trace
- 민감정보 마스킹
- 금융 Audit와 분리된 Agent 관측 로그

### 산출물

- 갱신된 Agent State와 Schema
- Backend API Client
- Webhook Client
- 재작성된 Tool
- 재작성된 Workflow
- Agent Trace 미들웨어

### 완료 기준

- Agent 코드에서 원장 직접 호출이 없음
- Agent 코드에서 Frontend 직접 호출이 없음
- 모든 외부 금융 호출이 Backend Tool API를 사용함
- 모든 HITL이 Webhook과 resume으로 처리됨

---

## 6.8 단계 7. 계약과 통합 테스트

### 관리시트 검증

- 관리시트와 API·UI 계약의 `contract_version` 일치
- 관리시트 상태가 `approved`인지 확인
- API와 UI `contract_id` 참조 오류 없음
- Workflow ID 중복 없음
- Step ID 참조 오류 없음
- Route 출발·도착 참조 오류 없음
- Tool ID 참조 오류 없음
- Data Schema 생산자·소비자 참조 오류 없음
- 제거한 Step 잔재 없음

### Schema 검증

- Agent Tool 요청·응답 계약
- Webhook Payload 계약
- input resume 계약
- approval resume 계약
- auth resume 계약
- Backend 오류 코드 계약

### Workflow 단위 테스트

- 계좌 목록
- 잔액 조회
- 거래내역 조회
- 기간 합계
- 기본 출금 계좌 변경
- 계좌 별칭 변경
- 본인 계좌 간 이체
- 타인송금
- 전역 Guardrail

### 타인송금 핵심 시나리오

- 사용자 발화의 수취인 이름 단건 매칭
- 사용자 발화의 수취인 이름 복수 매칭
- 최근 수취인 선택
- 신규 계좌번호 검증 성공
- 신규 계좌번호 검증 실패
- 금액 재입력
- 출금 계좌 변경
- 송금 경고 확인과 취소
- 승인과 수정
- 추가 인증 성공, 실패, 취소, 만료
- Prepare 만료
- Execute 중복 호출
- 원장 변경 후 응답 유실과 같은 멱등 키 재시도

### 보안 테스트

- 전체 계좌번호가 Agent State에 저장되지 않음
- 인증 원문이 Agent에 전달되지 않음
- 다른 사용자의 계좌와 수취인 참조 차단
- 임의 `confirmation_id`와 `auth_context_id` 차단
- Webhook Chat Session 불일치 차단

### 완료 기준

- 계약 테스트 통과
- 9개 Workflow 기준 시나리오 통과
- 민감정보 유출 테스트 통과
- Backend와 Frontend를 포함한 HITL E2E 통과

---

## 7. 역할별 작업 목록

### 7.1 Agent 팀

- 책임 결정 문서 작성
- 공통 데이터 스키마와 변수명 사전 작성
- Workflow별 State Data Schema 작성
- Agent Tool API 명세 갱신
- Tool Catalog 재작성
- Workflow 관리시트 재작성
- Backend 필요 기능 전달서 작성
- Backend Tool API Client 구현
- Webhook Client 구현
- LangGraph interrupt와 resume 구현
- Workflow와 Tool 재구현
- Agent Trace 구현
- 계약 테스트와 Workflow 테스트 구현

### 7.2 Backend 팀에 전달할 필요 기능

Agent 팀은 Backend 내부 구조나 구현 방법을 지정하지 않고 다음 외부 기능과 보장을 요청한다.

- Agent 실행에 필요한 Execution Context 발급과 전달
- Frontend 일반 입력 검증 후 Agent resume 호출
- Frontend 승인·수정·취소 검증 후 Agent resume 호출
- 추가 인증 결과 검증 후 Agent resume 호출
- 신규 수취 계좌 검증과 참조 ID 발급
- 이 문서에 정의한 14개 Agent Tool API 제공
- Confirmation의 생성·승인·무효화·실행 상태 보장
- Auth Context의 생성·검증·만료 상태 보장
- 같은 멱등성 요청이 중복 금융 실행을 만들지 않는 보장
- 금융 처리 사실에 대한 Backend Audit 보장
- Agent Webhook 검증과 Frontend SSE 전달
- 공개 오류 코드와 민감정보 마스킹

Router, Service, Repository, DB Schema, Queue와 Audit 저장 방식은 Backend 팀이 결정한다.

### 7.3 Frontend 팀과 합의할 작업

- `ui_type` Enum
- `ui_contract_id`별 제출 Payload와 resume Schema
- `recipient_select`의 최근 수취인과 신규 계좌번호 검증 흐름
- `confirm_modal`의 approve, modify, cancel
- `auth_request`의 인증 시작과 취소
- `need_input`, `need_approval`, `component` 이벤트 처리
- 사용자 입력 API와 승인 API 호출 규약

### 7.4 공동 합의가 필요한 작업

- 식별자 생성 주체
- 공통 변수명
- 오류 코드
- 날짜와 금액 형식
- Confirmation 만료시간
- Auth Context 만료시간
- 멱등성 보존시간
- Webhook 중복 제거 방식
- resume 재시도 방식

---

## 8. 우선순위 Backlog

| 우선순위 | 작업 | 선행 작업 | 담당 |
| --- | --- | --- | --- |
| P0 | 책임 분리 원칙 확정 | 없음 | 공동 |
| P0 | 공통 데이터 스키마와 변수명 사전 | 책임 확정 | Agent 주도, Backend 검토 |
| P0 | Agent Tool API 명세 재작성 | 변수명 사전 | Agent·Backend |
| P0 | Tool Catalog 재작성 | API 명세 | Agent |
| P0 | Workflow 관리시트 재작성 | Schema와 Tool 확정 | Agent |
| P0 | Sheet·Markdown 계약 검증기 | 관리시트와 API·UI 계약 | Agent |
| P0 | Backend 필요 기능 전달서 | API와 관리시트 | Agent |
| P0 | Agent 실행·resume Endpoint 구현 | 내부 Agent 계약 | Agent |
| P0 | Agent 실행·resume 호출 연동 | Backend 필요 기능 전달서 | Backend |
| P0 | Agent Tool API 구현 | Backend 필요 기능 전달서 | Backend |
| P0 | Agent API Client와 Webhook Client | API 계약 | Agent |
| P0 | Workflow와 Tool 구현 | 관리시트 | Agent |
| P1 | Frontend UI Registry 확장 | UI 계약 | Frontend |
| P1 | 계약 테스트 | API와 Schema | Agent·Backend |
| P1 | HITL E2E | Agent·Backend·Frontend 구현 | 공동 |
| P2 | 운영 관측과 재처리 정책 | 기본 E2E | Agent·Backend |

---

## 9. 최종 산출물

1. Agent·Backend 책임 결정 문서
2. 공통 데이터 스키마 문서
3. 변수명 사전
4. Workflow별 State Data Schema
5. 갱신된 `agent-tools-api-spec.md`
6. Tool Catalog
7. 새 Workflow 관리시트
8. Backend 필요 기능 전달서
9. Backend Tool API Client
10. Agent Webhook Client
11. 재작성된 Workflow와 Tool
12. Agent Trace 미들웨어
13. 계약 테스트
14. Workflow 단위 테스트
15. Agent·Backend·Frontend HITL E2E 결과
16. 승인된 관리시트 Snapshot과 계약 검증 보고서

---

## 10. 전체 완료 기준

- Agent가 원장과 DB를 직접 호출하지 않는다.
- Agent가 Frontend를 직접 호출하지 않는다.
- Workflow Step 한 행만 보고 내부 처리, Backend API, Webhook, 입력 대기 여부를 판단할 수 있다.
- Backend가 검증한 사용자 입력을 Agent가 다시 검증 요청하지 않는다.
- Prepare와 Execute의 금융 최종 검증은 Backend가 담당한다.
- 송금 Workflow에 Agent가 잔액 충분 여부를 판정하는 Step이 없다.
- 구조적 요청 검사는 별도 Workflow Step이 아니라 공통 Backend Tool API Adapter에서 수행된다.
- 하나의 Workflow Step은 최대 하나의 외부 동작만 수행한다.
- Backend Tool API 호출, Webhook 전송과 금융 실행 결과 전송이 각각 별도 Step으로 구성된다.
- 모든 Workflow에서 `write_audit_log`가 제거되어 있다.
- 금융 감사 로그의 정본은 Backend에 남는다.
- Agent State에는 참조 ID와 허용된 최소 데이터만 저장된다.
- API, Webhook, resume, State의 변수명이 데이터 사전과 일치한다.
- 관리시트로 Agent 설정을 생성할 수 있다.
- 관리시트, API 명세와 UI 계약이 안정적인 `contract_id`로 연결되어 있다.
- 승인된 관리시트 Snapshot과 Markdown 계약 버전이 일치할 때만 YAML을 생성한다.
- 계약 검증 실패 시 기존 YAML을 변경하지 않는다.
- 9개 Workflow의 계약 테스트와 HITL E2E가 통과한다.

---

## 11. 권장 착수 순서

다음 순서로 작업을 시작한다.

```text
1. 책임 분리 원칙 확정
2. 공통 데이터 스키마와 변수명 사전 작성
3. Agent Tool API 명세 갱신
4. Tool Catalog 재작성
5. Workflow 관리시트 재작성
6. 관리시트 Snapshot과 Markdown 계약 교차 검증 구현
7. Backend 필요 기능 전달서 작성
8. Backend와 Agent 병렬 구현
9. 계약 테스트
10. HITL E2E
```

첫 실제 작성 대상은 공통 데이터 스키마와 변수명 사전이다. 이 항목이 확정된 후 API 명세, 관리시트와 Agent State 구현을 같은 이름으로 맞춘다.
