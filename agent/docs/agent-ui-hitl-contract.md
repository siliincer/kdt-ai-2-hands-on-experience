# Agent UI·HITL 연동 계약

> 대상: Agent / Backend / Frontend 담당자
>
> 계약 버전: `0.9.0-review`
>
> 기준 문서: `agent-management-sheet-v3.xlsx`, `agent-tools-api-spec.md`, `agent-team-integration-implementation-roadmap.md`
>
> 목적: Agent가 Backend Webhook으로 요청하는 UI와 Backend가 검증하여 Agent를 재개하는 사용자 입력 계약을 정의한다.

---

## 1. 기본 원칙

### 1.1 시스템별 책임

Agent는 Frontend를 직접 호출하거나 UI를 직접 렌더링하지 않는다. Agent는 현재 Workflow에 필요한 사용자 행동 또는 결과를 UI 계약 ID와 함께 Backend Webhook으로 전송한다.

```text
Agent
-> 사용자 의도 분류와 입력값 추출
-> 필요한 Backend Tool API 호출
-> UI 계약 ID와 표시 데이터를 Backend Webhook으로 전송
-> 입력·승인·인증이 필요하면 Workflow 중단

Backend
-> 사용자, Execution Context와 대기 상호작용 검증
-> UI 표시 데이터 구성 또는 보강
-> Agent Webhook을 Frontend SSE 이벤트로 변환
-> Frontend 제출값과 금융 참조를 검증
-> 검증된 값으로 중단된 Agent Workflow 재개

Frontend
-> UI 계약 ID와 UI 타입에 맞는 화면 렌더링
-> 사용자 입력·선택·승인·인증 결과를 Backend에 제출
```

계좌 소유권, 계좌 상태, 수취 계좌, 잔액, 한도, 승인, 인증과 금융 실행의 최종 검증은 Backend 책임이다. Agent는 Backend가 검증한 참조 ID와 결과만 사용한다.

### 1.2 통신 방향

```text
입력·승인·인증 요청
Agent -> Backend Webhook -> Frontend SSE

사용자 제출과 검증
Frontend -> Backend

Workflow 재개
Backend -> Agent Resume API

결과·오류 표시
Agent -> Backend Webhook -> Frontend SSE
```

Webhook은 UI 이벤트 전달 통로이며 금융 조회·검증·실행 API를 대신하지 않는다.

### 1.3 대기 상호작용 식별자

| 상호작용 | 식별자 | 발급 주체 | 사용 목적 |
|---|---|---|---|
| 일반 입력·선택 | `input_request_id` | Agent | 입력 요청과 Resume 매칭 |
| 사용자 승인 | `confirmation_id` | Backend | Prepare 조건, 승인과 Execute 연결 |
| 추가 인증 | `auth_context_id` | Backend | 인증 시도와 검증 결과 연결 |

세 식별자는 서로 대신 사용하지 않는다. 한 `agent_thread_id`에는 동시에 하나의 활성 대기 상호작용만 허용한다.

`prompt_for`는 Webhook, Frontend 제출값과 Agent Resume 계약에서 사용하지 않는다. Backend는 `input_request_id`에 `execution_context_id`, `agent_thread_id`, `ui_contract_id`와 대기 상태를 연결한다. 입력 결과가 저장될 Agent State 필드는 관리시트의 Step Data Mapping으로 결정한다.

### 1.4 공통 Webhook 구조

일반 입력 요청 예시는 다음과 같다.

```json
{
  "chat_session_id": "chat_789",
  "event_type": "need_input",
  "content": "송금 금액을 입력해 주세요.",
  "metadata": {
    "workflow_id": "wf_external_transfer",
    "step_id": "request_external_transfer_amount",
    "input_request_id": "input_amount_123",
    "ui_contract_id": "UI-TRANSFER-AMOUNT-INPUT",
    "ui": {
      "type": "number_input",
      "payload": {
        "currency": "KRW",
        "min": 1
      }
    }
  }
}
```

승인 요청은 `input_request_id` 대신 `confirmation_id`를 사용한다.

```json
{
  "chat_session_id": "chat_789",
  "event_type": "need_approval",
  "content": "요청 내용을 확인해 주세요.",
  "confirmation_id": "confirm_123",
  "metadata": {
    "workflow_id": "wf_external_transfer",
    "step_id": "request_external_transfer_approval",
    "ui_contract_id": "UI-EXTERNAL-TRANSFER-CONFIRMATION",
    "ui": {
      "type": "confirm_modal",
      "payload": {}
    }
  }
}
```

추가 인증 요청은 Backend가 생성한 `auth_context_id`와 `auth_request_view`를 사용한다.

```json
{
  "chat_session_id": "chat_789",
  "event_type": "authentication_required",
  "content": "송금을 계속하려면 추가 인증이 필요합니다.",
  "metadata": {
    "workflow_id": "wf_external_transfer",
    "step_id": "request_external_authentication",
    "auth_context_id": "auth_123",
    "ui_contract_id": "UI-EXTERNAL-TRANSFER-AUTH",
    "ui": {
      "type": "auth_request",
      "payload": {
        "title": "추가 인증이 필요합니다.",
        "available_methods": ["biometric", "password"],
        "expires_at": "2026-07-15T15:10:00+09:00"
      }
    }
  }
}
```

### 1.5 Frontend 제출과 Agent Resume

Frontend는 일반 입력에서 `input_request_id`와 `value`만 Backend에 제출한다.

```json
{
  "chat_session_id": "chat_789",
  "input_request_id": "input_amount_123",
  "value": {
    "amount_input_outcome": "submitted",
    "amount": 50000
  }
}
```

Backend는 다음 항목을 검증한 뒤 Agent를 재개한다.

1. 인증된 사용자와 Chat Session 소유권
2. 현재 활성 상태인 `input_request_id`인지
3. 저장된 `ui_contract_id`와 제출값 Schema가 일치하는지
4. 계좌·수취인 참조가 현재 사용자에게 허용되는지
5. 요청이 소비되거나 만료되지 않았는지

검증 실패는 Agent를 재개하지 않고 같은 UI에서 처리한다. 검증 성공 후 Agent는 Resume 값을 State에 저장하고 같은 입력을 다시 요청하거나 같은 값을 다시 검증하기 위한 Tool API를 호출하지 않는다.

---

## 2. UI Component Registry

### 2.1 입력·선택·승인·인증 UI

| UI 타입 | 용도 | 대기 식별자 |
|---|---|---|
| `text_input` | 계좌 별칭 입력 | `input_request_id` |
| `recipient_select` | 기존 수취인 선택 또는 신규 계좌 입력·검증 | `input_request_id` |
| `account_card_list` | 단일·복수 계좌 선택 | `input_request_id` |
| `number_input` | 송금 금액 입력 | `input_request_id` |
| `period_input` | 조회 기간 선택 | `input_request_id` |
| `option_select` | 합계 유형·수정 대상·재인증 선택 | `input_request_id` |
| `confirm_modal` | 금융 요청 또는 설정 변경 승인 | `confirmation_id` |
| `auth_request` | 추가 인증 진행 | `auth_context_id` |

`search_select`와 `recipient_input`은 사용하지 않는다. 수취인 선택과 신규 계좌 입력은 `recipient_select` 하나로 처리한다.

### 2.2 결과·안내 UI

| UI 타입 | 용도 |
|---|---|
| `account_list` | 계좌 목록 결과 |
| `balance_result` | 계좌별 잔액 결과 |
| `transaction_list` | 거래내역 첫 페이지 |
| `amount_summary` | 기간 거래 합계 결과 |
| `transfer_result` | 본인송금·타인송금 완료 결과 |
| `setting_result` | 기본계좌·계좌 별칭 변경 결과 |
| `blocked_message` | 정책 또는 금융 처리 차단 안내 |
| `error_message` | 사용자에게 공개 가능한 오류 안내 |
| `message` | 지원 Workflow 없음 등 일반 안내 |

결과·안내 UI는 사용자 회신을 기다리지 않으므로 `input_request_id`와 Workflow 중단을 사용하지 않는다.

---

# 3. UI 타입별 계약

## 3.1 `text_input`

계좌 별칭을 사용자에게 추가로 입력받을 때 사용한다.

### 사용 위치

- `wf_set_account_alias / request_account_alias_input`

### Agent Webhook Payload

```json
{
  "type": "text_input",
  "payload": {
    "title": "새 계좌 별칭을 입력해 주세요.",
    "description": "계좌를 구분하기 쉬운 이름을 입력해 주세요.",
    "value": null,
    "validation": {
      "required": true,
      "max_length": 30
    },
    "actions": ["submit", "cancel"]
  }
}
```

Frontend 제출값은 다음과 같다.

```json
{
  "input_request_id": "input_alias_123",
  "value": {
    "alias_input_outcome": "submitted",
    "alias": "여행 자금"
  }
}
```

Backend는 별칭 형식과 정책을 검증하고 정규화한 `alias`만 Agent에 전달한다. 검증 실패는 같은 화면에 표시하며 Agent를 재개하지 않는다. 취소 시 `alias_input_outcome=cancelled`, `alias=null`로 재개한다.

## 3.2 `recipient_select`

타인송금 수취인을 기존 거래 수취인에서 선택하거나 신규 은행·계좌번호로 입력할 때 사용한다.

### 사용 위치

- `wf_external_transfer / request_recipient_selection`
- 최종 승인에서 사용자가 수취인 수정을 선택한 뒤 다시 진입하는 경우

### 화면 진입 규칙

1. 사용자 최초 발화에 `recipient_name_hint`가 있으면 Agent는 `API-RECIPIENT-RESOLVE`를 호출한다.
2. 기존 완료 거래에서 정확히 한 명이 확인되면 Backend가 `to_recipient_id`를 반환하며 선택 화면을 생략한다.
3. 동명이인이 여러 명이면 `recipient_selection_reason=multiple_matches`로 `recipient_select`를 요청한다.
4. 일치 수취인이 없거나 이름 힌트가 없으면 `recipient_selection_reason=no_match`로 `recipient_select`를 요청한다.
5. 이름 후보, 최근 수취인과 신규 계좌 입력 데이터는 Backend와 Frontend가 구성한다. Agent는 후보 목록과 전체 계좌번호를 조회하거나 State에 저장하지 않는다.

### UI 상태

| state | 의미 | Agent 재개 여부 |
|---|---|---:|
| `name_candidates` | 이름 힌트와 일치하는 복수 기존 거래 수취인 표시 | 최종 선택 시에만 재개 |
| `initial` | 최근 수취인과 신규 계좌번호 입력 영역 표시 | 최종 선택 시에만 재개 |
| `manual_input` | 은행과 계좌번호 입력 | 재개하지 않음 |
| `verifying` | Backend 신규 계좌 검증 중 | 재개하지 않음 |
| `manual_input_verified` | 검증된 신규 수취인 확인 | 확정 시에만 재개 |
| `verification_failed` | 신규 계좌 검증 실패와 재입력 안내 | 재개하지 않음 |

### 이름 후보 화면 요청 예시

```json
{
  "type": "recipient_select",
  "payload": {
    "state": "name_candidates",
    "title": "받는 분을 선택해 주세요.",
    "recipient_name_hint": "홍길동",
    "recipient_selection_reason": "multiple_matches",
    "actions": ["select", "manual_input", "cancel"]
  }
}
```

Backend는 이름 힌트를 기준으로 완료된 기존 타인송금 거래에서 후보를 구성한다. 후보에는 `to_recipient_id`, 이름, 은행명, 마스킹 계좌번호만 포함한다.

### 초기 화면 요청 예시

```json
{
  "type": "recipient_select",
  "payload": {
    "state": "initial",
    "title": "받는 분을 선택해 주세요.",
    "recipient_selection_reason": "no_match",
    "recent_recipients": true,
    "manual_input": {
      "enabled": true,
      "fields": ["bank_code", "account_number"]
    },
    "actions": ["select", "submit_manual", "cancel"]
  }
}
```

최근 수취인은 현재 사용자의 완료된 타인송금 거래를 기준으로 Backend가 중복 제거하고 계좌번호를 마스킹하여 제공한다. 신규 수취인 검색은 이름이 아니라 은행과 계좌번호 입력을 기준으로 한다.

### 기존 수취인 선택 Resume

```json
{
  "input_request_id": "input_recipient_123",
  "value": {
    "recipient_selection_outcome": "selected",
    "to_recipient_id": "rcp_001",
    "to_recipient_candidate_id": null
  }
}
```

### 신규 계좌 검증과 Resume

Frontend가 입력한 은행 코드와 전체 계좌번호는 Backend가 검증한다. 검증 성공 시 Backend는 `to_recipient_candidate_id`로 사용할 수 있는 참조 ID를 발급한다.

```json
{
  "input_request_id": "input_recipient_123",
  "value": {
    "recipient_selection_outcome": "selected",
    "to_recipient_id": null,
    "to_recipient_candidate_id": "rcp_candidate_001"
  }
}
```

`selected`에서는 `to_recipient_id`와 `to_recipient_candidate_id` 중 정확히 하나만 존재해야 한다. 취소 시 `recipient_selection_outcome=cancelled`와 두 참조의 null 값으로 재개한다. 전체 계좌번호, 은행 코드와 예금주 검증 원문은 Agent Resume과 State에 포함하지 않는다.

## 3.3 `account_card_list`

Backend가 소유권, 상태와 업무 권한을 검증하여 반환한 계좌 후보를 표시한다.

### 사용 위치

- 잔액·거래내역·기간 합계 조회 계좌 선택
- 기본 출금 계좌와 별칭 변경 대상 계좌 선택
- 본인송금 출금·입금 계좌 선택
- 타인송금 출금 계좌 선택

### Agent Webhook Payload

```json
{
  "type": "account_card_list",
  "payload": {
    "title": "계좌를 선택해 주세요.",
    "accounts": [
      {
        "account_id": "acc_001",
        "bank_name": "신한은행",
        "account_alias": "생활비 통장",
        "account_type": "checking",
        "masked_account_number": "110-***-123456",
        "currency": "KRW",
        "is_default": true
      }
    ],
    "actions": ["select", "cancel"]
  }
}
```

단일·복수 선택 모두 동일한 `account_ids` 배열로 제출한다. `selection_mode`와 단일 `account_id` 제출 필드는 사용하지 않는다.

```json
{
  "input_request_id": "input_account_123",
  "value": {
    "account_selection_outcome": "selected",
    "account_ids": ["acc_001"]
  }
}
```

단일 계좌 Workflow는 Backend 검증을 통과한 `account_ids`의 길이가 정확히 하나일 때만 Agent가 목적에 맞는 `account_id`, `from_account_id` 또는 `to_account_id`로 저장한다. 취소 시 `account_selection_outcome=cancelled`, `account_ids=[]`로 재개한다.

계좌 후보가 없으면 Agent는 같은 UI 계약에 `accounts=[]`를 담아 결과 Webhook을 전송하고 Workflow를 종료한다. 빈 상태에서는 Resume을 기다리지 않는다.

## 3.4 `number_input`

본인송금과 타인송금 금액을 입력받을 때 사용한다.

### 사용 위치

- `wf_internal_transfer / request_internal_transfer_amount`
- `wf_external_transfer / request_external_transfer_amount`

```json
{
  "type": "number_input",
  "payload": {
    "title": "송금 금액을 입력해 주세요.",
    "currency": "KRW",
    "min": 1,
    "actions": ["submit", "cancel"]
  }
}
```

```json
{
  "input_request_id": "input_amount_123",
  "value": {
    "amount_input_outcome": "submitted",
    "amount": 50000
  }
}
```

Backend는 입력 형식과 정규화만 수행하고, 잔액·한도·정책은 송금 Prepare와 Execute에서 검증한다. 형식 오류는 같은 UI에서 처리하며 Agent를 재개하지 않는다. 취소 시 `amount_input_outcome=cancelled`, `amount=null`로 재개한다.

## 3.5 `period_input`

사용자가 말한 기간을 Agent가 안전하게 정규화하지 못한 경우 날짜 범위를 선택받는다.

### 사용 위치

- `wf_transaction_history / request_period_selection`
- `wf_period_amount_summary / request_period_selection`

```json
{
  "type": "period_input",
  "payload": {
    "title": "조회 기간을 선택해 주세요.",
    "presets": ["this_month", "last_month", "recent_1_month"],
    "manual_range": true,
    "actions": ["select", "cancel"]
  }
}
```

프리셋은 사용자 텍스트 입력이 아니다. Backend와 Frontend가 프리셋을 날짜로 변환하고 Execution Context의 `timezone`, 날짜 순서와 최대 조회 기간을 검증한다.

```json
{
  "input_request_id": "input_period_123",
  "value": {
    "period_selection_outcome": "selected",
    "start_date": "2026-06-01",
    "end_date": "2026-06-30"
  }
}
```

Agent에는 프리셋 이름이 아니라 정규화된 `start_date`, `end_date`만 전달한다. 취소 시 `period_selection_outcome=cancelled`와 null 날짜로 재개한다.

## 3.6 `option_select`

정해진 Enum 중 하나를 선택받을 때 사용한다.

### 사용 위치

| UI 계약 | 선택값 |
|---|---|
| `UI-SUMMARY-TYPE-SELECTION` | `spending`, `income` |
| `UI-INTERNAL-TRANSFER-CORRECTION` | `from_account`, `to_account`, `amount` |
| `UI-EXTERNAL-TRANSFER-CORRECTION` | `from_account`, `recipient`, `amount` |
| `UI-INTERNAL-TRANSFER-AUTH-RETRY` | `retry`, `cancelled` |
| `UI-EXTERNAL-TRANSFER-AUTH-RETRY` | `retry`, `cancelled` |

합계 유형 선택 예시는 다음과 같다.

```json
{
  "type": "option_select",
  "payload": {
    "title": "합계 유형을 선택해 주세요.",
    "options": [
      {"value": "spending", "label": "지출"},
      {"value": "income", "label": "수입"}
    ],
    "actions": ["select", "cancel"]
  }
}
```

```json
{
  "input_request_id": "input_summary_type_123",
  "value": {
    "summary_type_selection_outcome": "selected",
    "summary_type": "spending"
  }
}
```

Backend는 저장된 `ui_contract_id`에 따라 허용된 Enum을 검증한다. 취소 결과를 받은 Agent는 추가 Webhook 없이 Workflow를 종료한다.

## 3.7 `confirm_modal`

Prepare가 생성한 변경 조건을 사용자가 최종 확인하고 승인·수정·취소할 때 사용한다.

### 사용 위치

- 본인송금과 타인송금
- 기본 출금 계좌 변경
- 계좌 별칭 변경

Agent는 Backend Prepare 응답의 `confirmation_id`와 `confirmation_view`를 이름을 바꾸거나 재구성하지 않고 전달한다.

```json
{
  "type": "confirm_modal",
  "payload": {
    "purpose": "external_transfer",
    "title": "송금 내용을 확인해 주세요.",
    "from_account": {
      "bank_name": "신한은행",
      "account_alias": "생활비 통장",
      "masked_account_number": "110-***-123456"
    },
    "recipient": {
      "name": "홍*동",
      "bank_name": "국민은행",
      "masked_account_number": "123-***-456789"
    },
    "amount": 50000,
    "currency": "KRW",
    "allowed_change_targets": ["from_account", "recipient", "amount"],
    "actions": ["approve", "modify", "cancel"]
  }
}
```

Backend는 사용자와 Confirmation의 상태·만료·고정 조건을 검증하고 승인 결과를 저장한 뒤 Agent를 재개한다.

```json
{
  "confirmation_id": "confirm_123",
  "approval_outcome": "approved",
  "change_target": null
}
```

수정은 `approval_outcome=change_requested`와 허용된 `change_target`으로 전달한다. Agent는 해당 입력 State와 이전 Confirmation을 초기화하고 수정 화면으로 돌아간다. 취소 시 `approval_outcome=cancelled`로 재개하며 추가 Webhook 없이 종료한다.

## 3.8 `auth_request`

송금 승인 후 Backend가 발급한 추가 인증 Context를 Frontend에 표시한다. 본인송금과 타인송금은 모두 추가 인증이 필수다.

### 사용 위치

- `wf_internal_transfer / request_internal_authentication`
- `wf_external_transfer / request_external_authentication`

Frontend는 인증 Assertion, PIN 또는 생체인증 원문을 Agent에 전달하지 않는다. Backend가 인증을 수행하고 결과를 저장한 뒤 Agent를 재개한다.

```json
{
  "auth_context_id": "auth_123",
  "auth_status": "verified"
}
```

허용 상태는 `verified`, `failed`, `cancelled`, `expired`다. `failed` 또는 `expired`이면 Agent는 재인증 선택 UI를 요청한다. `retry`는 새 `auth_context_id`를 생성하며, `cancelled`는 추가 Webhook 없이 Workflow를 종료한다.

---

# 4. 결과 UI 계약

## 4.1 `account_list`

계좌 목록 조회 결과를 표시한다. 계좌가 없어도 `accounts=[]`인 정상 결과로 같은 UI를 사용한다.

```json
{
  "type": "account_list",
  "payload": {
    "accounts": [
      {
        "account_id": "acc_001",
        "bank_name": "신한은행",
        "account_alias": "생활비 통장",
        "account_type": "checking",
        "masked_account_number": "110-***-123456",
        "currency": "KRW",
        "is_default": true,
        "status": "active"
      }
    ]
  }
}
```

계좌 목록에는 잔액과 전체 계좌번호를 포함하지 않는다.

## 4.2 `balance_result`

단일·복수 계좌의 잔액과 출금 가능 금액을 표시한다.

```json
{
  "type": "balance_result",
  "payload": {
    "accounts": [
      {
        "account_id": "acc_001",
        "account_alias": "생활비 통장",
        "masked_account_number": "110-***-123456",
        "balance": 1200000,
        "available_amount": 1180000,
        "currency": "KRW"
      }
    ]
  }
}
```

Agent는 잔액을 계산하거나 송금 가능 여부를 판단하지 않는다.

## 4.3 `transaction_list`

거래내역 첫 페이지만 Agent가 조회하여 표시한다. 이후 페이지 조회와 필터 탐색은 Frontend와 Backend가 `transaction_query_id`를 사용하여 처리하며 Agent를 재개하지 않는다.

```json
{
  "type": "transaction_list",
  "payload": {
    "account_ids": ["acc_001"],
    "period": {
      "start_date": "2026-06-15",
      "end_date": "2026-07-15"
    },
    "transactions": [
      {
        "transaction_id": "txn_001",
        "transaction_title": "편의점",
        "amount": -5200,
        "currency": "KRW",
        "occurred_at": "2026-07-14T20:30:00+09:00"
      }
    ],
    "transaction_query_id": "txq_123",
    "pagination": {
      "next_cursor": "cursor_002"
    }
  }
}
```

표시명은 `display_name`이 아니라 `transaction_title`을 사용한다.

## 4.4 `amount_summary`

Backend가 원장 거래를 분류하고 집계한 지출 또는 수입 합계를 표시한다.

```json
{
  "type": "amount_summary",
  "payload": {
    "account_ids": ["acc_001"],
    "start_date": "2026-06-15",
    "end_date": "2026-07-15",
    "summary_type": "spending",
    "total_amount": 350000,
    "currency": "KRW"
  }
}
```

`total_amount=0`도 오류가 아닌 정상 결과다. Agent는 거래내역을 직접 합산하지 않는다.

## 4.5 `transfer_result`

본인송금과 타인송금 완료 결과를 표시한다. Agent는 Execute 응답의 `transaction_id`, `completed_at`과 Prepare의 `confirmation_view`를 조합한다.

```json
{
  "type": "transfer_result",
  "payload": {
    "transaction_id": "txn_123",
    "completed_at": "2026-07-15T15:05:00+09:00",
    "from_account": {},
    "recipient": {},
    "amount": 50000,
    "currency": "KRW"
  }
}
```

본인송금에서는 `recipient` 대신 검증된 입금 계좌 표시 데이터를 사용한다.

## 4.6 `setting_result`

기본 출금 계좌 또는 계좌 별칭 변경 완료와 변경 없음 결과를 표시한다.

```json
{
  "type": "setting_result",
  "payload": {
    "purpose": "account_alias",
    "outcome": "completed",
    "account": {
      "account_id": "acc_001",
      "masked_account_number": "110-***-123456"
    },
    "alias": "여행 자금",
    "completed_at": "2026-07-15T15:05:00+09:00"
  }
}
```

별칭 변경에는 `account_label`, `current_alias`, `new_alias`를 사용하지 않는다. 새 별칭은 `alias` 하나로 전달한다.

---

# 5. Workflow별 UI 매핑

## 5.1 `wf_global_agent_entry`

| step_id | 계약 ID | UI 타입 | 대기 여부 |
|---|---|---|---:|
| `emit_global_blocked` | `UI-GLOBAL-BLOCKED` | `blocked_message` | 아니요 |
| `emit_no_matching_workflow` | `UI-NO-MATCH` | `message` | 아니요 |
| `emit_workflow_dispatch_error` | `UI-COMMON-ERROR` | `error_message` | 아니요 |

하위 업무 Workflow가 결과나 오류 Webhook을 이미 전송한 경우 글로벌 Workflow는 중복 응답을 보내지 않는다.

## 5.2 `wf_account_list`

| step_id | 계약 ID | UI 타입 | 대기 여부 |
|---|---|---|---:|
| `emit_account_list_result` | `UI-ACCOUNT-LIST-RESULT` | `account_list` | 아니요 |
| `emit_account_list_error` | `UI-COMMON-ERROR` | `error_message` | 아니요 |

## 5.3 `wf_balance_inquiry`

| step_id | 계약 ID | UI 타입 | 대기 여부 |
|---|---|---|---:|
| `request_balance_account_selection` | `UI-BALANCE-ACCOUNT-SELECTION` | `account_card_list` | 예 |
| `emit_balance_accounts_empty` | `UI-BALANCE-ACCOUNT-SELECTION` | `account_card_list` | 아니요 |
| `emit_balance_result` | `UI-BALANCE-RESULT` | `balance_result` | 아니요 |
| `emit_balance_error` | `UI-COMMON-ERROR` | `error_message` | 아니요 |

## 5.4 `wf_transaction_history`

| step_id | 계약 ID | UI 타입 | 대기 여부 |
|---|---|---|---:|
| `request_transaction_account_selection` | `UI-TRANSACTION-ACCOUNT-SELECTION` | `account_card_list` | 예 |
| `emit_transaction_accounts_empty` | `UI-TRANSACTION-ACCOUNT-SELECTION` | `account_card_list` | 아니요 |
| `request_period_selection` | `UI-PERIOD-SELECTION` | `period_input` | 예 |
| `emit_transaction_result` | `UI-TRANSACTION-LIST` | `transaction_list` | 아니요 |
| `emit_transaction_error` | `UI-COMMON-ERROR` | `error_message` | 아니요 |

## 5.5 `wf_period_amount_summary`

| step_id | 계약 ID | UI 타입 | 대기 여부 |
|---|---|---|---:|
| `request_summary_account_selection` | `UI-SUMMARY-ACCOUNT-SELECTION` | `account_card_list` | 예 |
| `emit_summary_accounts_empty` | `UI-SUMMARY-ACCOUNT-SELECTION` | `account_card_list` | 아니요 |
| `request_period_selection` | `UI-PERIOD-SELECTION` | `period_input` | 예 |
| `request_summary_type` | `UI-SUMMARY-TYPE-SELECTION` | `option_select` | 예 |
| `emit_amount_summary` | `UI-AMOUNT-SUMMARY` | `amount_summary` | 아니요 |
| `emit_amount_summary_error` | `UI-COMMON-ERROR` | `error_message` | 아니요 |

## 5.6 `wf_set_default_account`

| step_id | 계약 ID | UI 타입 | 대기 여부 |
|---|---|---|---:|
| `request_default_account_selection` | `UI-DEFAULT-ACCOUNT-SELECTION` | `account_card_list` | 예 |
| `emit_default_account_selection_empty` | `UI-DEFAULT-ACCOUNT-SELECTION` | `account_card_list` | 아니요 |
| `request_default_account_approval` | `UI-DEFAULT-ACCOUNT-CONFIRMATION` | `confirm_modal` | 예 |
| `emit_default_account_unchanged` | `UI-DEFAULT-ACCOUNT-RESULT` | `setting_result` | 아니요 |
| `emit_default_account_result` | `UI-DEFAULT-ACCOUNT-RESULT` | `setting_result` | 아니요 |
| `emit_default_account_blocked` | `UI-SETTING-BLOCKED` | `blocked_message` | 아니요 |
| `emit_default_account_error` | `UI-COMMON-ERROR` | `error_message` | 아니요 |

## 5.7 `wf_set_account_alias`

| step_id | 계약 ID | UI 타입 | 대기 여부 |
|---|---|---|---:|
| `request_account_alias_selection` | `UI-ACCOUNT-ALIAS-SELECTION` | `account_card_list` | 예 |
| `emit_account_alias_selection_empty` | `UI-ACCOUNT-ALIAS-SELECTION` | `account_card_list` | 아니요 |
| `request_account_alias_input` | `UI-ACCOUNT-ALIAS-INPUT` | `text_input` | 예 |
| `request_account_alias_approval` | `UI-ACCOUNT-ALIAS-CONFIRMATION` | `confirm_modal` | 예 |
| `emit_account_alias_unchanged` | `UI-ACCOUNT-ALIAS-RESULT` | `setting_result` | 아니요 |
| `emit_account_alias_result` | `UI-ACCOUNT-ALIAS-RESULT` | `setting_result` | 아니요 |
| `emit_account_alias_blocked` | `UI-SETTING-BLOCKED` | `blocked_message` | 아니요 |
| `emit_account_alias_error` | `UI-COMMON-ERROR` | `error_message` | 아니요 |

## 5.8 `wf_internal_transfer`

| step_id | 계약 ID | UI 타입 | 대기 여부 |
|---|---|---|---:|
| `request_from_account_selection` | `UI-INTERNAL-TRANSFER-FROM-ACCOUNT` | `account_card_list` | 예 |
| `emit_internal_from_accounts_empty` | `UI-INTERNAL-TRANSFER-FROM-ACCOUNT` | `account_card_list` | 아니요 |
| `request_to_account_selection` | `UI-INTERNAL-TRANSFER-TO-ACCOUNT` | `account_card_list` | 예 |
| `emit_internal_to_accounts_empty` | `UI-INTERNAL-TRANSFER-TO-ACCOUNT` | `account_card_list` | 아니요 |
| `request_internal_transfer_amount` | `UI-TRANSFER-AMOUNT-INPUT` | `number_input` | 예 |
| `request_internal_transfer_approval` | `UI-INTERNAL-TRANSFER-CONFIRMATION` | `confirm_modal` | 예 |
| `request_internal_transfer_correction` | `UI-INTERNAL-TRANSFER-CORRECTION` | `option_select` | 예 |
| `request_internal_authentication` | `UI-INTERNAL-TRANSFER-AUTH` | `auth_request` | 예 |
| `request_internal_auth_retry` | `UI-INTERNAL-TRANSFER-AUTH-RETRY` | `option_select` | 예 |
| `emit_internal_transfer_result` | `UI-INTERNAL-TRANSFER-RESULT` | `transfer_result` | 아니요 |
| `emit_internal_transfer_blocked` | `UI-TRANSFER-BLOCKED` | `blocked_message` | 아니요 |
| `emit_internal_transfer_error` | `UI-COMMON-ERROR` | `error_message` | 아니요 |

## 5.9 `wf_external_transfer`

| step_id | 계약 ID | UI 타입 | 대기 여부 |
|---|---|---|---:|
| `request_recipient_selection` | `UI-RECIPIENT-SELECT` | `recipient_select` | 예 |
| `request_external_from_account_selection` | `UI-EXTERNAL-TRANSFER-FROM-ACCOUNT` | `account_card_list` | 예 |
| `emit_external_from_accounts_empty` | `UI-EXTERNAL-TRANSFER-FROM-ACCOUNT` | `account_card_list` | 아니요 |
| `request_external_transfer_amount` | `UI-TRANSFER-AMOUNT-INPUT` | `number_input` | 예 |
| `request_external_transfer_approval` | `UI-EXTERNAL-TRANSFER-CONFIRMATION` | `confirm_modal` | 예 |
| `request_external_transfer_correction` | `UI-EXTERNAL-TRANSFER-CORRECTION` | `option_select` | 예 |
| `request_external_authentication` | `UI-EXTERNAL-TRANSFER-AUTH` | `auth_request` | 예 |
| `request_external_auth_retry` | `UI-EXTERNAL-TRANSFER-AUTH-RETRY` | `option_select` | 예 |
| `emit_external_transfer_result` | `UI-EXTERNAL-TRANSFER-RESULT` | `transfer_result` | 아니요 |
| `emit_external_transfer_blocked` | `UI-TRANSFER-BLOCKED` | `blocked_message` | 아니요 |
| `emit_external_transfer_error` | `UI-COMMON-ERROR` | `error_message` | 아니요 |

---

# 6. Backend SSE와 Resume 변환 예시

Agent Webhook의 `metadata.ui_contract_id`, `metadata.ui.type`, `metadata.ui.payload`는 Backend가 Frontend SSE 계약으로 변환한다. 구체적인 SSE 이벤트명과 내부 저장 구조는 Backend가 결정할 수 있지만 의미와 필드 손실이 없어야 한다.

```text
Agent Webhook
-> Backend가 chat_session_id와 Execution Context 검증
-> Pending Input에 input_request_id와 ui_contract_id 저장
-> Frontend SSE로 UI 요청 전달
-> Frontend가 input_request_id와 value 제출
-> Backend가 UI 계약과 사용자 권한 검증
-> POST /internal/v1/executions/{agent_thread_id}/resume
```

일반 입력 Resume 요청 예시는 다음과 같다.

```json
{
  "request_id": "req_resume_123",
  "chat_session_id": "chat_789",
  "execution_context_id": "exec_123",
  "resume": {
    "type": "input",
    "input_request_id": "input_amount_123",
    "value": {
      "amount_input_outcome": "submitted",
      "amount": 50000
    }
  }
}
```

승인 Resume은 `confirmation_id`, 인증 Resume은 `auth_context_id`를 사용한다. Backend가 검증한 Resume 입력을 받은 Agent는 동일한 사용자 입력·승인·인증을 다시 요청하지 않는다.

---

# 7. 공통 안전 규칙

1. UI 표시용 계좌번호와 개인정보는 Backend가 마스킹한다.
2. 전체 계좌번호, 인증 원문과 Frontend Access Token은 Agent State와 Webhook에 포함하지 않는다.
3. Frontend 입력 검증은 사용자 편의를 위한 것이며 Backend 금융 검증을 대체하지 않는다.
4. 계좌 선택, 수취인 선택과 신규 계좌 검증은 Backend가 완료한 뒤 검증된 참조만 Agent에 전달한다.
5. 승인 화면의 데이터와 실제 Execute 조건은 Backend가 `confirmation_id`로 연결하여 재검증한다.
6. 사용자가 계좌·수취인·금액을 수정하면 기존 Confirmation을 폐기하고 Prepare와 승인을 다시 수행한다.
7. 재인증은 유효한 Confirmation을 유지하고 새 `auth_context_id`만 발급한다.
8. 입력 검증 실패는 Agent를 재개하지 않고 같은 UI에서 처리한다.
9. 사용자가 입력·승인·인증을 취소하면 Agent는 추가 취소 Webhook 없이 Workflow를 종료한다.
10. 거래내역 첫 페이지 이후 조회는 Frontend와 Backend가 처리하며 Agent를 재개하지 않는다.
11. 결과·차단·오류 Webhook은 사용자 회신을 기다리지 않는다.
12. Agent는 별도 Audit API를 호출하지 않으며 Backend가 금융 API 처리 과정에서 Audit Event를 기록한다.

---

# 8. Backend 연동에 필요한 기능

Agent 팀은 Backend의 내부 구현 방식을 지정하지 않는다. 다만 본 계약을 사용하려면 다음 기능이 필요하다.

- Agent Webhook의 `ui_contract_id`, UI 타입과 Payload를 Frontend SSE로 전달
- `input_request_id`와 Execution Context, Agent Thread, UI 계약의 연결 관리
- Frontend 일반 입력·승인·인증 제출 API
- UI 계약별 제출값 Schema와 Enum 검증
- 계좌 소유권·상태·업무 권한 검증
- 신규 수취 계좌 검증과 `to_recipient_candidate_id` 발급
- Confirmation 승인·수정·취소·만료 상태 관리
- Auth Context 생성과 인증 결과 검증
- 검증된 값으로 Agent Resume API 호출
- Webhook 중복 이벤트 방지와 사용자 공개 오류 처리

Endpoint 구성, DB 테이블과 서비스 모듈 분리는 Backend 팀 정책에 따른다.

---

# 9. 계약 정본과 변경 절차

| 영역 | 정본 |
|---|---|
| Workflow 목록과 Step·Route | `agent-management-sheet-v3.xlsx` |
| Workflow State 필드 | 관리시트 `Workflow Data Schema` 탭 |
| Step별 State 입출력 | 관리시트 `Step Data Mapping` 탭 |
| Agent Tool API 요청·응답 | `agent-tools-api-spec.md` |
| UI Payload와 Resume 값 | 이 문서 |
| Agent 팀 구현 순서와 책임 경계 | `agent-team-integration-implementation-roadmap.md` |

관리시트에는 UI JSON 전체를 복제하지 않고 `contract_id`만 기록한다. UI Payload를 변경하면 이 문서의 계약 버전을 갱신하고 관리시트 `Contract Registry`의 버전과 존재 여부를 함께 검증한다.
