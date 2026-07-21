# Agent UI Payload 계약 변경 및 관리시트 반영 안내

> 대상: Agent, Backend, Frontend 담당자
>
> 기준일: 2026-07-20

## 1. 변경 목적

관리시트와 UI·HITL 계약 사이에 다음과 같은 Payload 경로 차이가 있었다.

- 기간 합계 결과: 관리시트는 `payload.summary` 객체를 사용했지만 UI 계약은 합계 필드를 `payload` 바로 아래에 정의했다.
- 설정 변경 결과: 관리시트는 `payload.account_id`를 사용했지만 UI 계약은 계좌 식별 정보를 `payload.account` 객체로 정의했다.

이번 변경은 다음 기준으로 계약을 통일한다.

- 화면의 핵심 결과값은 불필요한 중간 객체 없이 `payload`에 바로 전달한다.
- 계좌처럼 하나의 업무 대상을 나타내는 식별 정보는 `account` 객체로 묶는다.
- Agent 내부 State와 Backend Agent Tool API 응답 구조는 변경하지 않는다.

## 2. 최종 변경 내용

### 2.1 기간 합계 결과

변경 전:

```json
{
  "type": "amount_summary",
  "payload": {
    "account_ids": ["acc_001"],
    "keyword": "배민",
    "summary": {
      "start_date": "2026-07-01",
      "end_date": "2026-07-20",
      "summary_type": "spending",
      "total_amount": 350000,
      "transaction_count": 18,
      "currency": "KRW"
    }
  }
}
```

변경 후:

```json
{
  "type": "amount_summary",
  "payload": {
    "account_ids": ["acc_001"],
    "keyword": "배민",
    "start_date": "2026-07-01",
    "end_date": "2026-07-20",
    "summary_type": "spending",
    "total_amount": 350000,
    "transaction_count": 18,
    "currency": "KRW"
  }
}
```

- 검색어가 없으면 `keyword`는 `null`이다.
- `total_amount=0`, `transaction_count=0`도 정상 결과다.
- Backend의 `POST /api/v1/agent-tools/transactions:summary` 응답은 기존처럼 `data.summary_result`를 사용한다.
- Agent가 `summary_result`를 State에 저장한 뒤 Webhook을 만들 때 각 필드를 평탄화한다.

### 2.2 설정 변경 결과

변경 전:

```json
{
  "type": "setting_result",
  "payload": {
    "purpose": "account_alias",
    "outcome": "completed",
    "account_id": "acc_001",
    "alias": "여행 자금",
    "completed_at": "2026-07-20T15:05:00+09:00"
  }
}
```

변경 후:

```json
{
  "type": "setting_result",
  "payload": {
    "purpose": "account_alias",
    "outcome": "completed",
    "account": {
      "account_id": "acc_001"
    },
    "alias": "여행 자금",
    "completed_at": "2026-07-20T15:05:00+09:00"
  }
}
```

- `account.account_id`는 필수다.
- `alias`는 계좌 별칭 변경 결과에서 사용한다.
- 마스킹 계좌번호는 Backend 응답에 이미 포함된 경우에만 `account` 객체의 선택 필드로 전달한다.
- 결과 화면을 만들기 위해 Agent가 계좌 정보를 추가 조회하지 않는다.

## 3. 구글 관리시트에서 직접 수정할 위치

수정 대상 탭은 `Step Data Mapping`이다. 행 번호는 정렬이나 필터에 따라 달라질 수 있으므로 `workflow_id`, `step_id`, `state_key` 조합으로 행을 찾는다.

### 3.1 `wf_period_amount_summary`

다음 기존 행을 삭제한다.

| workflow_id | step_id | direction | state_key | contract_field_path |
| --- | --- | --- | --- | --- |
| `wf_period_amount_summary` | `emit_amount_summary` | `input` | `summary_result` | `webhook.metadata.ui.payload.summary` |

삭제한 행 대신 다음 6개 행을 추가한다.

| workflow_id | step_id | direction | state_key | contract_field_path | required_at_step | mapping_description | notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `wf_period_amount_summary` | `emit_amount_summary` | `input` | `summary_result` | `webhook.metadata.ui.payload.start_date` | `true` | Backend 합계 결과의 시작일을 결과 UI 최상위 필드에 전달한다. |  |
| `wf_period_amount_summary` | `emit_amount_summary` | `input` | `summary_result` | `webhook.metadata.ui.payload.end_date` | `true` | Backend 합계 결과의 종료일을 결과 UI 최상위 필드에 전달한다. |  |
| `wf_period_amount_summary` | `emit_amount_summary` | `input` | `summary_result` | `webhook.metadata.ui.payload.summary_type` | `true` | Backend 합계 결과의 유형을 결과 UI 최상위 필드에 전달한다. | `spending`, `income` |
| `wf_period_amount_summary` | `emit_amount_summary` | `input` | `summary_result` | `webhook.metadata.ui.payload.total_amount` | `true` | Backend 합계 결과의 금액을 결과 UI 최상위 필드에 전달한다. | 금액 원문은 일반 로그에서 제외 |
| `wf_period_amount_summary` | `emit_amount_summary` | `input` | `summary_result` | `webhook.metadata.ui.payload.transaction_count` | `true` | Backend 합계 결과의 거래 건수를 결과 UI 최상위 필드에 전달한다. | 0도 정상 결과 |
| `wf_period_amount_summary` | `emit_amount_summary` | `input` | `summary_result` | `webhook.metadata.ui.payload.currency` | `true` | Backend 합계 결과의 통화를 결과 UI 최상위 필드에 전달한다. |  |

다음 기존 행은 변경하지 않는다.

- `account_ids` → `webhook.metadata.ui.payload.account_ids`
- `keyword` → `webhook.metadata.ui.payload.keyword`

### 3.2 `wf_set_default_account`

`contract_field_path`만 다음과 같이 변경한다.

| step_id | state_key | 변경 전 | 변경 후 |
| --- | --- | --- | --- |
| `emit_default_account_unchanged` | `account_id` | `webhook.metadata.ui.payload.account_id` | `webhook.metadata.ui.payload.account.account_id` |
| `emit_default_account_result` | `account_id` | `webhook.metadata.ui.payload.account_id` | `webhook.metadata.ui.payload.account.account_id` |

### 3.3 `wf_set_account_alias`

`contract_field_path`만 다음과 같이 변경한다.

| step_id | state_key | 변경 전 | 변경 후 |
| --- | --- | --- | --- |
| `emit_account_alias_unchanged` | `account_id` | `webhook.metadata.ui.payload.account_id` | `webhook.metadata.ui.payload.account.account_id` |
| `emit_account_alias_result` | `account_id` | `webhook.metadata.ui.payload.account_id` | `webhook.metadata.ui.payload.account.account_id` |

다음 항목은 변경하지 않는다.

- Workflow Data Schema의 `summary_result`, `account_id`
- Workflow Steps의 `input_state_keys`, `output_state_keys`
- Contract Mapping의 계약 ID
- `alias`, `completed_at`의 기존 Payload 경로

## 4. 문서별 변경 사항

### `agent-tools-api-spec.md`

- 12장 거래 합계 조회 API의 요청과 응답 Schema는 변경하지 않았다.
- Backend가 반환한 `data.summary_result`를 Agent가 `amount_summary` Webhook의 평탄한 Payload로 변환한다는 설명을 추가했다.
- 따라서 Backend Agent Tool API 구현 변경은 필요하지 않다.

### `agent-ui-hitl-contract.md`

- 4.4 `amount_summary`에 `keyword`, `transaction_count`를 명시했다.
- `amount_summary`의 합계 결과는 `payload` 바로 아래에 두도록 확정했다.
- 4.6 `setting_result`의 계좌 ID를 `payload.account.account_id`로 확정했다.
- 마스킹 계좌번호는 필수가 아니며, 표시 정보가 이미 있는 경우에만 사용할 수 있도록 정리했다.

### `agent-team-integration-implementation-roadmap.md`

- 위 변경에 맞춰 Workflow별 Step Data Mapping 경로를 수정했다.

## 5. 담당자별 확인 사항

### Backend

- Agent Tool API 요청과 응답에는 변경이 없다.
- Agent Webhook을 받아 저장하거나 Frontend로 전달하는 과정에서 `payload.summary`를 전제로 한 처리가 있는지 확인이 필요하다.
- 설정 결과에서 `payload.account_id`를 직접 참조하고 있다면 `payload.account.account_id` 기준으로 확인이 필요하다.

### Frontend

- `amount_summary`는 `payload.total_amount`, `payload.start_date`처럼 평탄한 경로를 사용한다.
- `setting_result`의 계좌 ID는 `payload.account.account_id`를 사용한다.
- `keyword=null`과 금액·거래 건수 0을 정상 결과로 처리해야 한다.

### Agent

- Backend의 `summary_result` 응답은 기존 구조로 State에 저장한다.
- Webhook 생성 시에만 기간 합계 필드를 평탄화한다.
- 설정 결과는 계좌 ID를 `account` 객체로 구성한다.

## 6. 반영 순서

1. 구글 관리시트의 `Step Data Mapping`을 3장 기준으로 수정한다.
2. Backend와 Frontend 담당자가 5장의 영향 경로를 확인한다.
3. 구글 관리시트를 저장소의 `agent-management-sheet-v3.xlsx`와 동기화한다.
4. `workflow-contracts.json`을 다시 생성하고 계약 일치 검사를 실행한다.
5. Agent Mock E2E와 Backend·Frontend 연동 테스트에서 두 UI Payload를 확인한다.

이번 변경에서 API Endpoint, 계약 ID, Agent 내부 State 필드명은 변경하지 않는다.
