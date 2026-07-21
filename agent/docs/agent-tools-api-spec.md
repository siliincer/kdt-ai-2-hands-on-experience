# Agent Tool API 명세

> 상태: Backend 검토 요청안
>
> 계약 버전: `0.9.0`
>
> 최종 수정일: `2026-07-14`
>
> 대상: Agent, Backend 개발자
>
> 목적: Agent가 금융 원장과 Mock Financial Service에 직접 접근하지 않고 Backend에 금융 조회, 검증, Prepare, Execute를 요청하기 위한 API를 정의한다.
>
> 전체 통신 구조: `agent/docs/agent-backend-integration-contract.md`
>
> 타인송금 실행 예시: `agent/docs/external-transfer-integration-flow.md`
>
> HTTP 요청·응답 계약 정본: 이 문서
>
> Workflow와 API 연결 정본: 프로젝트 Google 스프레드시트의 Workflow Step·계약 매핑 탭

`1.0.0`은 Agent·Backend·Frontend 담당자 검토로 요청·응답 필드와 HITL 경계가 확정된 뒤 부여한다.

---

## 1. 적용 범위

이 문서는 다음 방향의 내부 API만 정의한다.

```text
Agent -> Backend
GET 또는 POST /api/v1/agent-tools/*
```

이 API의 목적은 Agent Workflow가 다음 Step과 Route를 결정하는 데 필요한 금융 처리 결과를 Backend에서 받는 것이다.

다음 API는 이 문서의 본문 범위가 아니다.

```text
Agent -> Backend Webhook
  진행 상태와 UI 이벤트 전달

Backend -> Agent
  Workflow 시작과 재개

Frontend -> Backend
  사용자 메시지, 입력, 승인, 인증
```

Frontend가 호출하는 보조 API는 부록에서 경계만 설명한다.

---

## 2. 설계 원칙

1. Agent는 DB나 Mock Financial Service를 직접 호출하지 않는다.
2. Agent는 금융 Tool 요청에 `user_id`를 전달하지 않는다.
3. Backend는 `X-Execution-Context-Id`에서 사용자를 결정한다.
4. Backend는 모든 계좌 조회와 실행에서 소유권을 검증한다.
5. Agent는 전체 계좌번호와 인증 원문을 받거나 저장하지 않는다.
6. 변경 작업은 Prepare, 사용자 승인과 Execute 순서를 따르며 타인송금과 본인송금은 승인 후 추가 인증을 항상 수행한다.
7. Execute 요청은 Backend가 고정한 `confirmation_id`를 사용한다.
8. 상태 변경 API에는 `Idempotency-Key`를 적용한다.
9. Backend는 Execute 직전에 승인, 인증, 잔액, 한도, 정책을 다시 검증한다.
10. 금융 감사 로그의 정본은 Backend가 기록한다.

---

## 3. Base URL과 Prefix

개발 환경 예시:

```text
http://backend-gateway:8000
```

공통 Prefix:

```text
/api/v1/agent-tools
```

Agent는 설정된 Backend Base URL과 명세에 정의된 Path만 호출한다. 동적으로 URL이나 HTTP Method를 생성하지 않는다.

### 3.1 계약 정본과 필드 이름 규칙

이 문서는 Agent Tool API의 HTTP Method, Path, Header, 요청·응답 필드, 오류와 멱등성 규칙의 정본이다. Google 스프레드시트는 Workflow Step과 이 문서의 `contract_id`를 연결하고 동기화된 Method와 Path를 검토하는 용도로 사용하며, HTTP 필드 정의를 독립적으로 편집하지 않는다.

문서별 담당 영역은 다음과 같다.

| 문서 | 정본으로 관리하는 내용 |
| --- | --- |
| `agent-tools-api-spec.md` | Agent Tool API 요청·응답과 오류 계약 |
| Workflow Data Schema | Agent Workflow State 필드 정의 |
| UI·HITL 계약 | Webhook UI Payload와 Frontend 제출값 |
| Google 스프레드시트 | Workflow Step, Route, State Mapping과 `contract_id` 연결 |

요청 필드 이름에는 다음 규칙을 적용한다.

1. Agent는 `user_id`를 보내지 않고 Backend는 `X-Execution-Context-Id`에서 인증된 사용자를 결정한다.
2. 잔액, 거래내역과 기간 합계처럼 복수 계좌를 한 번에 조회하는 API는 `account_ids` 배열을 사용한다.
3. 설정 변경처럼 단일 계좌만 대상으로 하는 API는 `account_id`를 사용한다.
4. 이체에서 역할이 다른 계좌는 `from_account_id`, `to_account_id`로 구분한다.
5. 타인송금 수취인은 `to_recipient_id` 또는 `to_recipient_candidate_id`를 사용한다.
6. 기간 필드는 `start_date`, `end_date`를 사용한다.
7. 현재 송금 요구사항에 없는 `memo`는 요청과 응답에 사용하지 않는다.
8. `confirmation_id`, `auth_context_id`, `to_recipient_candidate_id`는 Backend가 발급한 참조 ID만 사용한다.

---

## 4. 서비스 인증과 공통 Header

### 4.1 조회 API

```http
Authorization: Bearer <agent-service-token>
X-Execution-Context-Id: exec_123
X-Request-Id: req_123
Accept: application/json
```

Body가 있는 조회 요청은 `Content-Type: application/json`을 함께 전송한다. HTTP Method가 POST이더라도 원장과 Backend 상태를 변경하지 않는 조회 API에는 `Idempotency-Key`를 사용하지 않는다.

### 4.2 상태 변경 API

```http
Authorization: Bearer <agent-service-token>
X-Execution-Context-Id: exec_123
X-Request-Id: req_123
Idempotency-Key: idem_123
Content-Type: application/json
```

### 4.3 Header 정의

| Header | 필수 | 설명 |
| --- | --- | --- |
| `Authorization` | 필수 | Agent 서비스 인증 Token |
| `X-Execution-Context-Id` | 필수 | Backend가 발급한 실행 Context |
| `X-Request-Id` | 필수 | 단일 HTTP 요청 추적 ID |
| `Idempotency-Key` | 상태 변경 API 필수 | 중복 Context 생성과 금융 실행 방지 |
| `Content-Type` | Body가 있으면 필수 | `application/json` |

`Idempotency-Key`는 Prepare, Auth Context 생성, Execute와 설정 변경처럼 Backend 상태를 변경하는 API에만 필수다. 잔액, 거래내역과 기간 합계를 조회하는 POST API에는 적용하지 않는다.

### 4.4 Execution Context 검증

Backend는 모든 Agent Tool 요청에서 다음을 확인한다.

- Context 존재 여부
- Context 활성 상태와 만료
- 요청 Agent 서비스와 Context 연결
- 사용자, `chat_session_id`, `agent_thread_id` 연결
- API에 필요한 Scope
- 종료 또는 취소된 실행인지

Agent Tool 요청 Body에는 다음 실행 Context 필드를 받지 않는다.

```text
user_id
chat_session_id
agent_thread_id
workflow_id
workflow_version
```

Backend는 해당 값을 Agent가 보낸 업무 데이터가 아니라 `X-Execution-Context-Id`에 연결된 서버 측 Execution Context에서 확인한다.

---

## 5. 공통 응답

`success`는 Backend가 요청을 정상적으로 처리하여 계약된 응답을 반환했는지를 나타낸다. 송금 가능, 승인 완료 또는 금융 실행 완료 여부를 직접 나타내지 않는다.

```text
success=true
- Backend가 요청을 정상적으로 처리하고 업무 결과를 반환함

success=false
- 요청 검증, 서비스 인증, 권한 또는 시스템 처리 자체에 오류가 발생함
```

Agent는 `success=true`인 Prepare와 Execute 응답의 `data.outcome`으로 업무 Route를 결정한다. `success=false`이면 `error.category`와 `error.code`로 오류 Route를 결정한다.

### 5.1 성공 응답

```json
{
  "success": true,
  "message": "처리 결과 메시지",
  "data": {}
}
```

### 5.2 금융 업무 결과 응답

Prepare가 현재 요청으로 승인 화면을 만들 수 있으면 `ready_for_confirmation`을 반환한다.

```json
{
  "success": true,
  "message": "송금 내용을 확인했습니다.",
  "data": {
    "outcome": "ready_for_confirmation",
    "confirmation_id": "confirm_123",
    "confirmation_view": {}
  }
}
```

사용자가 계좌, 수취인 또는 금액을 수정하면 진행할 수 있는 경우 `correction_required`를 반환한다.

```json
{
  "success": true,
  "message": "송금 정보를 수정해 주세요.",
  "data": {
    "outcome": "correction_required",
    "reason": "insufficient_balance",
    "correction_view": {
      "allowed_change_targets": [
        "from_account",
        "amount"
      ]
    }
  }
}
```

업무 판단은 정상적으로 완료했지만 현재 Workflow에서 수정으로 해결할 수 없으면 `blocked`를 반환한다.

```json
{
  "success": true,
  "message": "현재 이 송금을 진행할 수 없습니다.",
  "data": {
    "outcome": "blocked",
    "reason": "policy_blocked",
    "blocked_view": {
      "title": "요청을 진행할 수 없습니다."
    }
  }
}
```

`correction_required`와 `blocked`는 기술 오류가 아니라 Backend의 정상적인 금융 업무 판단이므로 `success=true`와 `200 OK`를 사용한다.

### 5.3 오류 응답

```json
{
  "success": false,
  "error": {
    "category": "technical_error",
    "code": "BACKEND_TEMPORARY_ERROR",
    "message": "일시적으로 요청을 처리할 수 없습니다.",
    "retryable": true,
    "details": {}
  }
}
```

오류 응답은 Execution Context, 서비스 인증, 요청 Schema, 권한, 멱등성 충돌 또는 시스템 처리 자체에 문제가 있어 계약된 금융 업무 결과를 반환하지 못한 경우에 사용한다.

### 5.4 HTTP 상태

| 상태 | 의미 |
| --- | --- |
| `200 OK` | 조회, Prepare 업무 판단 또는 Execute 업무 결과 반환 |
| `201 Created` | Auth Context처럼 독립된 Context 리소스 생성 성공 |
| `400 Bad Request` | 요청 형식이나 값 오류 |
| `401 Unauthorized` | Agent 서비스 인증 실패 |
| `403 Forbidden` | Scope 또는 금융 리소스 접근 권한 없음 |
| `404 Not Found` | 참조 ID에 해당하는 리소스 없음 |
| `409 Conflict` | 상태 충돌, Confirmation 불일치, 멱등성 키 충돌 |
| `410 Gone` | Context 또는 Confirmation 만료 |
| `422 Unprocessable Entity` | 형식은 맞지만 계약에 정의되지 않은 값 조합 등으로 요청을 해석할 수 없음 |
| `429 Too Many Requests` | 호출 제한 초과 |
| `500 Internal Server Error` | Backend 내부 오류 |
| `502 Bad Gateway` | 하위 금융서비스 응답 오류 |
| `503 Service Unavailable` | 일시적으로 처리 불가 |
| `504 Gateway Timeout` | 하위 금융서비스 timeout |

Prepare는 `ready_for_confirmation`에서 Confirmation을 생성하더라도 별도 Confirmation 리소스 생성 API가 아니라 금융 조건 평가 명령이므로 모든 업무 Outcome에 `200 OK`를 사용한다.

---

## 6. 공통 오류 코드와 업무 사유 코드

`success=false`의 오류 코드와 `success=true`의 업무 사유 코드를 구분한다. 개별 Endpoint가 `outcome`으로 정의한 금융 판단은 요청 처리 실패가 아니므로 같은 의미를 다시 HTTP 오류로 반환하지 않는다.

### 6.1 요청·인증·상태·기술 오류 코드

| 코드 | 권장 HTTP 상태 | Agent 처리 |
| --- | --- | --- |
| `INVALID_EXECUTION_CONTEXT` | 401 | 실행 중단 |
| `EXECUTION_CONTEXT_EXPIRED` | 410 | 실행 중단 또는 새 실행 요청 |
| `INSUFFICIENT_SCOPE` | 403 | 실행 중단 |
| `ACCOUNT_NOT_FOUND` | 404 | 계좌 선택 단계부터 다시 진행 |
| `ACCOUNT_ACCESS_DENIED` | 403 | 실행 중단 또는 계좌 재선택 |
| `RECIPIENT_NOT_FOUND` | 404 | 수취인 선택 단계부터 다시 진행 |
| `RECIPIENT_CANDIDATE_EXPIRED` | 410 | 신규 계좌 재검증 |
| `CONFIRMATION_REQUIRED` | 409 | Prepare부터 다시 진행 |
| `CONFIRMATION_EXPIRED` | 410 | Prepare부터 다시 진행 |
| `CONFIRMATION_MISMATCH` | 409 | 기존 Confirmation 폐기 후 재생성 |
| `AUTH_REQUIRED` | 409 | Auth Context 생성 단계로 이동 |
| `IDEMPOTENCY_REQUEST_IN_PROGRESS` | 409 | `Retry-After` 이후 같은 요청 재호출 |
| `IDEMPOTENCY_KEY_CONFLICT` | 409 | 실행 중단 후 같은 키의 요청 비교 |
| `BACKEND_TEMPORARY_ERROR` | 503 | 정책에 따라 제한적으로 같은 요청 재시도 |

### 6.2 정상 업무 Outcome의 사유 코드

다음 값은 `error.code`가 아니라 `data.reason`에 사용한다. Endpoint가 허용한 `outcome`과 `correction_view` 또는 `blocked_view`를 함께 반환한다.

| 사유 코드 예시 | 대표 Outcome | Agent 처리 |
| --- | --- | --- |
| `account_inactive` | `correction_required` 또는 `blocked` | 계좌 재선택 또는 차단 안내 |
| `invalid_amount` | `correction_required` | 금액 재입력 |
| `limit_exceeded` | `correction_required` 또는 `blocked` | 금액 수정 또는 차단 안내 |
| `insufficient_balance` | `correction_required` | 출금 계좌 또는 금액 수정 |
| `recipient_not_verified` | `correction_required` | 수취 계좌 재입력 |
| `policy_blocked` | `blocked` | 차단 안내 후 종료 |
| `auth_context_expired` | `reauthentication_required` | 새 Auth Context 생성 |
| `transfer_failed` | `failed` | 실패 안내와 Backend 결과 표시 |

예를 들어 Prepare가 잔액 부족을 정상적으로 판정했다면 `200 OK`, `success=true`, `outcome=correction_required`, `reason=insufficient_balance`를 반환한다. 요청 Schema를 해석할 수 없거나 서비스 장애로 판정 자체를 완료하지 못한 경우에만 `success=false`를 사용한다.

오류 메시지는 사용자에게 공개 가능한 문장만 포함한다. DB 오류, Stack Trace, 내부 URL과 Secret은 응답하지 않는다.

---

## 7. timeout과 재시도

`X-Request-Id`는 단일 논리 HTTP 요청을 추적한다. Timeout이나 응답 유실로 동일한 요청을 통신 계층에서 재시도할 때는 기존 `X-Request-Id`를 유지한다. 사용자 수정이나 새로운 Workflow Step으로 별도 요청을 시작할 때는 새로운 값을 생성한다.

상태 변경 API의 동일 요청 재시도에서는 `X-Request-Id`와 `Idempotency-Key`를 모두 유지한다. 사용자가 계좌, 수취인 또는 금액을 수정하여 새로운 Prepare를 시작하면 두 값 모두 새로 생성한다.

Agent의 공통 Backend Tool API Adapter는 연결·응답 Timeout 또는 HTTP `502`, `503`, `504`에 한해 자동으로 최대 1회 재시도한다. 따라서 최초 호출을 포함한 최대 호출 횟수는 2회다. `429`, 입력·권한·인증 오류와 `correction_required`, `blocked` 같은 업무 결과는 자동 재시도하지 않는다. 재시도 후에도 실패하면 해당 Workflow의 오류 Webhook Step으로 이동한다.

### 7.1 조회 API

- 연결 timeout 권장값: 3초
- 전체 요청 timeout 권장값: 10초
- 연결·응답 Timeout 또는 `502`, `503`, `504`만 재시도
- 짧은 Backoff와 Jitter 적용
- 최대 재시도 횟수는 1회

### 7.2 Prepare API

- 같은 `Idempotency-Key`로만 재시도
- 동일한 논리 요청의 재시도에서는 같은 `X-Request-Id` 유지
- 연결·응답 Timeout 또는 `502`, `503`, `504`에 한해 최대 1회 재시도
- 성공 여부가 불명확하면 새 Confirmation을 무조건 만들지 않음
- Backend는 동일한 키와 동일한 요청에 동일한 결과 반환

### 7.3 Execute API

- timeout 후 새로운 `Idempotency-Key` 생성 금지
- 동일한 논리 요청의 재시도에서는 같은 `X-Request-Id` 유지
- 연결·응답 Timeout 또는 `502`, `503`, `504`에 한해 최대 1회 재시도
- 결과가 불명확하면 동일한 키와 동일한 Body로 재호출
- Backend는 원장 변경과 멱등성 결과를 하나의 Transaction 경계로 처리
- 같은 키와 다른 Body는 `IDEMPOTENCY_KEY_CONFLICT` 반환

### 7.4 Auth Context 생성 API

- 연결·응답 Timeout 또는 `502`, `503`, `504`에 한해 최대 1회 재시도
- 동일한 논리 요청에는 같은 `X-Request-Id`, `Idempotency-Key`와 Body 유지
- 통신 재시도에서는 `auth_attempt`를 증가시키지 않음
- 인증 실패·만료 후 사용자가 재인증을 선택한 경우에만 새로운 논리 요청과 키 생성

---

## 8. API 목록

| 번호 | contract_id | 메서드 | Path | 역할 | 멱등성 |
| ---: | --- | --- | --- | --- | --- |
| 1 | `API-ACCOUNT-LIST` | GET | `/accounts` | 계좌 후보 조회 | 불필요 |
| 2 | `API-BALANCE-QUERY` | POST | `/accounts/balances:query` | 복수 계좌 잔액 조회 | 불필요 |
| 3 | `API-TRANSACTION-QUERY` | POST | `/transactions:query` | 거래내역 첫 페이지 조회 | 불필요 |
| 4 | `API-TRANSACTION-SUMMARY` | POST | `/transactions:summary` | 기간 거래 합계 조회 | 불필요 |
| 5 | `API-RECIPIENT-RESOLVE` | POST | `/recipients:resolve` | 이름 힌트의 기존 거래 수취인 자동 확정 | 불필요 |
| 6 | `API-EXTERNAL-TRANSFER-PREPARE` | POST | `/transfers/external:prepare` | 타인송금 조건 사전 평가 | 필수 |
| 7 | `API-AUTH-CONTEXT-CREATE` | POST | `/auth-contexts` | 송금 추가 인증 Context 생성 | 필수 |
| 8 | `API-EXTERNAL-TRANSFER-EXECUTE` | POST | `/transfers/external` | 타인송금 실행 | 필수 |
| 9 | `API-INTERNAL-TRANSFER-PREPARE` | POST | `/transfers/internal:prepare` | 본인 이체 조건 사전 평가 | 필수 |
| 10 | `API-INTERNAL-TRANSFER-EXECUTE` | POST | `/transfers/internal` | 본인 이체 실행 | 필수 |
| 11 | `API-DEFAULT-ACCOUNT-PREPARE` | POST | `/settings/default-account:prepare` | 기본계좌 변경 조건 평가 | 필수 |
| 12 | `API-DEFAULT-ACCOUNT-EXECUTE` | POST | `/settings/default-account` | 기본계좌 변경 실행 | 필수 |
| 13 | `API-ACCOUNT-ALIAS-PREPARE` | POST | `/settings/account-alias:prepare` | 계좌 별칭 변경 조건 평가 | 필수 |
| 14 | `API-ACCOUNT-ALIAS-EXECUTE` | POST | `/settings/account-alias` | 계좌 별칭 변경 실행 | 필수 |

표의 Path에는 공통 Prefix `/api/v1/agent-tools`가 생략되어 있다.

---

## 9. 계좌 목록 조회

### 9.1 기본 정보

```http
GET /api/v1/agent-tools/accounts
```

- 호출자: Agent
- 상태 변경: 없음
- 계약 ID: `API-ACCOUNT-LIST`
- 사용 Workflow: 계좌 목록, 잔액 조회, 거래내역, 본인 이체, 타인 송금, 계좌 설정
- 사용 Tool: `fetch_accounts`

### 9.2 Query Parameter

| 필드 | 타입 | 필수 | 제한 |
| --- | --- | --- | --- |
| `account_hint` | string | 선택 | 은행명, 계좌 별칭 또는 계좌 유형, 최대 100자 |
| `account_capability` | string | 선택 | `inquiry`, `withdraw`, `deposit`, `settings` |
| `resolve_selection` | boolean | 선택 | 기본 `false`. Backend의 계좌 자동 확정 결과가 필요한 경우 `true` |
| `all_accounts_requested` | boolean | 선택 | 기본 `false`. `resolve_selection=true`일 때만 사용 |
| `exclude_account_ids` | `list[string]` | 선택 | 후보에서 제외할 현재 사용자 소유 계좌 ID, 최대 20개, 중복 불가 |
| `limit` | integer | 선택 | 기본 20, 최대 100 |

### 9.3 요청 예시

```http
GET /api/v1/agent-tools/accounts?account_hint=생활비&account_capability=withdraw&limit=20
```

본인송금의 입금 계좌를 확인하면서 확정된 출금 계좌를 제외하는 경우:

```http
GET /api/v1/agent-tools/accounts?account_hint=저축&account_capability=deposit&resolve_selection=true&exclude_account_ids=acc_001&limit=20
```

여러 계좌를 제외할 때는 `exclude_account_ids` Query Parameter를 반복해서 전달한다.

잔액 조회에서 검증된 계좌 자동 확정 결과가 필요한 경우:

```http
GET /api/v1/agent-tools/accounts?account_hint=생활비&account_capability=inquiry&resolve_selection=true&all_accounts_requested=false&limit=20
```

### 9.4 성공 응답

```json
{
  "success": true,
  "message": "계좌 목록을 조회했습니다.",
  "data": {
    "accounts": [
      {
        "account_id": "acc_001",
        "bank_name": "카카오뱅크",
        "account_alias": "생활비 통장",
        "account_type": "checking",
        "masked_account_number": "3333-**-1234567",
        "currency": "KRW",
        "is_default": true,
        "status": "active"
      }
    ]
  }
}
```

### 9.5 계좌 자동 확정 응답

`resolve_selection=true`이면 Backend는 후보 목록과 함께 자동 확정 결과를 반환한다. Agent는 후보 개수로 자동 확정 여부를 다시 판단하지 않는다.

```json
{
  "success": true,
  "message": "조회할 계좌를 확인했습니다.",
  "data": {
    "account_resolution_outcome": "resolved",
    "account_ids": [
      "acc_001"
    ],
    "accounts": [
      {
        "account_id": "acc_001",
        "bank_name": "카카오뱅크",
        "account_alias": "생활비 통장",
        "account_type": "checking",
        "masked_account_number": "3333-**-1234567",
        "currency": "KRW",
        "is_default": true,
        "status": "active"
      }
    ]
  }
}
```

`account_resolution_outcome` Enum:

```text
resolved
selection_required
no_accounts
```

- `resolved`: Backend 검증을 통과한 계좌가 자동 확정되었으며 `account_ids`를 반환한다.
- `selection_required`: 검증된 후보가 여러 개이고 사용자 선택이 필요하며 `accounts`에 후보를 반환한다.
- `no_accounts`: 조건에 맞는 검증된 계좌가 없으며 `account_ids=[]`, `accounts=[]`를 반환한다.

`all_accounts_requested=true`이면 Backend는 조회 가능한 전체 계좌를 검증하여 `resolved`와 전체 `account_ids`를 반환한다. `all_accounts_requested=false`이고 후보가 여러 개이면 `selection_required`를 반환한다.

### 9.6 Backend 검증

- Execution Context 사용자
- 사용자가 소유한 계좌만 반환
- `account_capability`에 필요한 활성 상태와 거래 가능 여부
- `account_hint` 검색 범위를 은행명, 계좌 별칭과 계좌 유형으로 제한
- `exclude_account_ids`의 모든 값이 현재 사용자 소유 계좌인지와 중복·개수 제한 검증
- 검증된 제외 계좌를 후보 목록과 자동 확정 대상에서 제거
- 조회 개수 제한
- 계좌번호 마스킹

잔액은 이 응답에 기본 포함하지 않는다. 잔액이 필요한 Workflow는 잔액 조회 API를 호출한다.

`account_hint`가 없으면 검색어 필터를 적용하지 않는다. 검색 결과가 없으면 오류가 아니라 `accounts=[]`인 정상 응답을 반환한다. Agent가 `status`를 직접 지정하지 않으며 Backend가 요청된 `account_capability`에 맞는 계좌 상태를 판단한다.

`resolve_selection=true`인 경우 Backend가 계좌 소유권, 활성 상태와 `account_capability`를 검증한 후 자동 확정 여부를 결정한다. 선택 UI의 사용자 회신도 Backend가 같은 기준으로 검증한 뒤 검증된 `account_ids`만 Agent resume 입력으로 전달한다. Agent는 resume된 계좌를 다시 검증하기 위해 계좌 목록 API를 재호출하지 않는다.

`account_capability`는 Workflow State가 아니라 호출 Step에 고정된 API 요청값이다. 타인송금과 본인송금의 출금 계좌 조회는 모두 `from_account_hint`를 `account_hint`에 매핑하고 `account_capability=withdraw`를 사용한다. 본인송금에서 입금 계좌가 이미 확정된 상태로 출금 계좌를 다시 조회하면 `to_account_id`를 `exclude_account_ids`에 전달한다. 본인송금 입금 계좌 조회는 `to_account_hint`를 `account_hint`에 매핑하고 `account_capability=deposit`을 사용하며, 확정된 `from_account_id`를 `exclude_account_ids` 배열에 넣어 전달한다.

---

## 10. 잔액 조회

### 10.1 기본 정보

```http
POST /api/v1/agent-tools/accounts/balances:query
```

- 호출자: Agent
- 상태 변경: 없음
- 계약 ID: `API-BALANCE-QUERY`
- 사용 Workflow: `wf_balance_inquiry`
- 사용 Tool: `query_balances`

타인송금과 본인송금의 잔액, 한도와 거래 가능 여부는 각 Prepare와 Execute가 검증하므로 이 API를 호출하지 않는다.

### 10.2 요청

```json
{
  "account_ids": [
    "acc_001",
    "acc_002"
  ]
}
```

| 필드 | 타입 | 필수 | 제한 |
| --- | --- | --- | --- |
| `account_ids` | `list[string]` | 필수 | 최소 1개, 최대 20개, 중복 불가 |

### 10.3 성공 응답

```json
{
  "success": true,
  "message": "잔액을 조회했습니다.",
  "data": {
    "balance_results": [
      {
        "account_id": "acc_001",
        "bank_name": "카카오뱅크",
        "account_alias": "생활비 통장",
        "masked_account_number": "3333-**-1234567",
        "balance": 1250000,
        "available_balance": 1200000,
        "currency": "KRW",
        "as_of": "2026-07-14T10:00:00+09:00"
      },
      {
        "account_id": "acc_002",
        "bank_name": "신한은행",
        "account_alias": "저축 통장",
        "masked_account_number": "110-***-123456",
        "balance": 500000,
        "available_balance": 500000,
        "currency": "KRW",
        "as_of": "2026-07-14T10:00:00+09:00"
      }
    ]
  }
}
```

### 10.4 Backend 검증

- 요청한 모든 계좌의 사용자 소유권
- 모든 계좌의 잔액 조회 가능 상태
- 잔액 조회 Scope
- 최소·최대 계좌 개수
- 중복 계좌 ID

한 계좌라도 소유권이나 접근 권한 검증에 실패하면 부분 결과를 반환하지 않고 요청 전체를 거절한다. 다른 사용자 계좌의 존재 여부가 부분 응답으로 노출되지 않도록 한다. 단일 계좌 조회도 `account_ids` 배열을 사용하며 Agent는 계좌별 반복 호출을 수행하지 않는다.

`balance_results`는 Agent의 같은 이름 State에 저장한다. 잔액 원문은 Agent Trace와 일반 로그에 기록하지 않는다.

---

## 11. 거래내역 조회

### 11.1 기본 정보

```http
POST /api/v1/agent-tools/transactions:query
```

- 호출자: Agent
- 상태 변경: 없음
- 계약 ID: `API-TRANSACTION-QUERY`
- 사용 Workflow: `wf_transaction_history`
- 사용 Tool: `query_transactions`

### 11.2 요청

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

| 필드 | 타입 | 필수 | 제한 |
| --- | --- | --- | --- |
| `account_ids` | `list[string]` | 필수 | 최소 1개, 최대 20개, 중복 불가 |
| `start_date` | date | 필수 | Backend 최대 조회 기간 적용 |
| `end_date` | date | 필수 | `start_date` 이상 |
| `keyword` | string 또는 null | 선택 | 최대 100자 |
| `transaction_type` | string 또는 null | 선택 | 아래 `TransactionType` Enum |
| `limit` | integer | 선택 | 기본 10, 최대 100 |

`TransactionType` Enum:

```text
deposit
withdrawal
transfer
card_payment
atm_withdrawal
fee
interest
```

요청 필터와 응답의 `transaction_type`은 같은 Enum을 사용한다. 카드 결제, ATM 출금, 수수료와 이자처럼 구체적인 유형에 해당하면 일반 `withdrawal` 또는 `deposit`보다 구체적인 값을 우선한다. `transfer`는 본인 계좌 이체와 타인 계좌 송수신을 포함하는 계좌이체 거래에 사용하며, Backend가 `transaction_title`에 거래 상대 또는 대상 계좌 정보를 마스킹하여 표시한다.

사용자가 기간을 말하지 않으면 Agent는 Execution Context의 `requested_at`, `timezone`을 기준으로 최근 1개월을 `start_date`, `end_date`에 적용한다. Agent는 첫 페이지의 최신순 10건만 조회하므로 이 요청에 `cursor`를 보내지 않는다. 이후 페이지는 Frontend가 `transaction_query_id`와 `next_cursor`로 Backend 일반 API를 호출한다.

### 11.3 성공 응답

```json
{
  "success": true,
  "message": "거래내역을 조회했습니다.",
  "data": {
    "transaction_results": [
      {
        "transaction_id": "txn_001",
        "account_id": "acc_001",
        "account_alias": "생활비 통장",
        "occurred_at": "2026-07-10T12:30:00+09:00",
        "transaction_type": "withdrawal",
        "amount": 15000,
        "currency": "KRW",
        "transaction_title": "카페 결제",
        "category": "식비"
      }
    ],
    "transaction_query_id": "txq_123",
    "next_cursor": "cursor_002"
  }
}
```

### 11.4 Backend 검증

- 모든 계좌의 사용자 소유권
- 중복 계좌 ID와 최대 계좌 개수
- 최대 조회 기간
- 검색어 길이와 정규화
- 거래 유형 Enum
- 페이지 크기
- 여러 계좌 결과의 `occurred_at` 기준 전역 정렬
- 거래 상대방 정보 마스킹

한 계좌라도 소유권이나 접근 권한 검증에 실패하면 부분 결과를 반환하지 않고 요청 전체를 거절한다. 조회 결과가 없으면 `transaction_results=[]`, `next_cursor=null`인 정상 응답을 반환한다. 최근 1개월에 거래가 없더라도 Backend와 Agent는 조회 기간을 더 과거로 자동 확장하지 않는다.

Agent는 첫 페이지와 `transaction_query_id`, `next_cursor`를 결과 Webhook으로 보낸 뒤 Workflow를 종료한다. Backend는 Query Context에 사용자, `account_ids`, 기간, 검색 조건, 페이지 크기와 만료시각을 저장한다. 이후 페이지는 다음 Frontend용 API가 담당한다.

```http
GET /api/v1/transactions/queries/{transaction_query_id}?cursor={next_cursor}
```

거래내역 응답에는 `total_amount`를 포함하지 않는다. 기간 합계는 `API-TRANSACTION-SUMMARY`가 담당한다. 거래 금액과 `transaction_title` 원문은 Agent Trace와 일반 로그에 기록하지 않는다.

---

## 12. 거래 합계 조회

### 12.1 기본 정보

```http
POST /api/v1/agent-tools/transactions:summary
```

- 호출자: Agent
- 상태 변경: 없음
- 계약 ID: `API-TRANSACTION-SUMMARY`
- 사용 Workflow: `wf_period_amount_summary`
- 사용 Tool: `query_transaction_summary`

### 12.2 요청

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

| 필드 | 타입 | 필수 | 제한 |
| --- | --- | --- | --- |
| `account_ids` | `list[string]` | 필수 | 최소 1개, 최대 20개, 중복 불가 |
| `start_date` | date | 필수 | Backend 최대 조회 기간 적용 |
| `end_date` | date | 필수 | `start_date` 이상 |
| `summary_type` | string | 필수 | `spending`, `income` |
| `keyword` | string 또는 null | 선택 | 최대 100자 |

사용자가 기간을 말하지 않으면 Agent는 `wf_transaction_history`와 동일하게 Execution Context의 `requested_at`, `timezone`을 기준으로 최근 1개월을 `start_date`, `end_date`에 적용한다. `이번 달`, `지난달`, `최근 한 달`처럼 명시된 기간은 해당 의미대로 정규화한다. 기간 선택 UI를 사용한 경우 Backend가 프리셋 또는 직접 입력 날짜를 검증·정규화하여 Agent를 resume하며, 별도의 Agent Tool API는 추가하지 않는다.

### 12.3 성공 응답

```json
{
  "success": true,
  "message": "거래 합계를 조회했습니다.",
  "data": {
    "summary_result": {
      "summary_type": "spending",
      "total_amount": 375000,
      "transaction_count": 18,
      "currency": "KRW",
      "start_date": "2026-07-01",
      "end_date": "2026-07-14"
    }
  }
}
```

사용자 기준 `start_date`와 `end_date`는 양쪽 날짜를 모두 포함한다. Backend는 Execution Context의 `timezone`을 기준으로 종료일 다음 날 00시 미만인 반열림 시각 범위로 변환한다.

Backend는 모든 계좌의 소유권, 중복 계좌 ID, 최대 계좌 수, 조회 기간, `summary_type`, 검색어와 통화 일치 여부를 검증한다. 원장 거래를 지출과 수입으로 분류하고 본인 계좌 간 이체, 취소와 정정 거래를 집계 정책에 맞게 처리한다. 전체 거래내역은 Agent로 전달하지 않는다.

조건에 맞는 거래가 없으면 오류가 아니라 `total_amount=0`, `transaction_count=0`인 `summary_result`를 반환한다. `summary_result`의 금액 원문은 Agent Trace와 일반 로그에 기록하지 않는다.

---

## 13. 기존 거래 수취인 자동 확정

### 13.1 기본 정보

```http
POST /api/v1/agent-tools/recipients:resolve
```

- 호출자: Agent
- 상태 변경: 없음
- 계약 ID: `API-RECIPIENT-RESOLVE`
- 사용 Workflow: `wf_external_transfer / resolve_recipient_hint`
- 사용 조건: `recipient_name_hint`가 있고 검증된 수취인 참조가 없는 경우

이 API는 최근 수취인이나 이름 후보 목록을 Agent에 반환하지 않는다. 최초 발화에서 추출한 이름 힌트를 현재 사용자의 기존 타인송금 거래내역에서 정확히 하나의 수취인 참조로 확정할 수 있는지만 판단한다.

### 13.2 요청

```json
{
  "recipient_name_hint": "홍길동"
}
```

| 필드 | 타입 | 필수 | 제한 |
| --- | --- | --- | --- |
| `recipient_name_hint` | string | 필수 | 공백 제거 후 1자 이상, 최대 100자 |

### 13.3 단일 수취인 확정 응답

```json
{
  "success": true,
  "message": "기존 거래 수취인을 확인했습니다.",
  "data": {
    "outcome": "resolved",
    "to_recipient_id": "rcp_001"
  }
}
```

Agent는 `to_recipient_id`를 State에 저장하고 다음 Slot으로 진행한다. 이 응답은 Backend의 내부 자동 확정 결과이므로 Agent는 수취인 선택 UI나 별도의 수취인 확인 UI를 표시하지 않는다. 실제 수취인 표시 정보는 이후 Backend Prepare가 생성한 최종 송금 확인 화면에서 출금 계좌와 금액 등 다른 송금 정보와 함께 보여준다.

Agent는 `outcome=resolved`를 `recipient_resolution_outcome`에 저장하고, `to_recipient_id`가 존재하는지 확인한 뒤 다음 Step으로 이동한다.

### 13.4 사용자 선택 필요 응답

동명이인 또는 서로 다른 계좌의 수취인이 여러 명이면 다음 응답을 반환한다.

```json
{
  "success": true,
  "message": "동일한 이름의 수취인이 여러 명입니다.",
  "data": {
    "outcome": "selection_required",
    "selection_reason": "multiple_matches"
  }
}
```

기존 거래에서 일치하는 수취인을 찾지 못하면 다음 응답을 반환한다.

```json
{
  "success": true,
  "message": "기존 거래에서 수취인을 찾지 못했습니다.",
  "data": {
    "outcome": "selection_required",
    "selection_reason": "no_match"
  }
}
```

`selection_required`에서는 Agent가 후보 목록을 받지 않고 `UI-RECIPIENT-SELECT` Webhook만 전송한다. Backend는 Execution Context와 `recipient_name_hint`를 이용해 이름 후보 또는 최근 수취인 데이터를 구성하고 Frontend로 전달한다.

Agent는 `outcome=selection_required`를 `recipient_resolution_outcome`, `selection_reason`을 `recipient_selection_reason`에 저장한다. `multiple_matches`이면 이름 후보 상태, `no_match` 또는 이름 힌트가 없으면 최근 수취인과 계좌번호 입력이 가능한 초기 상태를 요청한다.

Backend가 Agent를 재개하는 최종 수취인 선택 결과는 다음 규칙을 따른다.

```json
{
  "recipient_selection_outcome": "selected",
  "to_recipient_id": "rcp_001"
}
```

신규 검증 수취인은 `to_recipient_id` 대신 `to_recipient_candidate_id`를 전달한다. `selected`에서는 두 참조 중 정확히 하나만 존재해야 한다. 취소는 두 참조 없이 `recipient_selection_outcome=cancelled`로 재개하며 Agent는 추가 Webhook 없이 종료한다. 검색·계좌 검증 같은 UI 내부 상태에서는 Agent를 중간 재개하지 않는다.

정상 흐름에서 수취인 선택 UI는 최대 한 번만 표시한다. `resolved` 이후 최종 송금 확인 화면에서 사용자가 수취인 수정을 명시적으로 선택한 경우에만 기존 수취인 참조를 폐기하고 `UI-RECIPIENT-SELECT`로 돌아간다.

### 13.5 자동 확정 규칙

- 현재 사용자가 완료한 타인송금 거래만 사용
- 본인 계좌 간 이체, 실패, 취소와 정정 거래 제외
- 이름 정규화 후 정확히 일치하는 결과만 자동 확정
- 부분 일치와 유사 검색 결과는 자동 확정하지 않음
- 동일한 `recipient_id`의 반복 거래는 하나로 중복 제거
- 사용할 수 없거나 제한된 수취인 제외
- 남은 고유 `recipient_id`가 정확히 하나일 때만 `resolved`
- 결과가 없거나 두 개 이상이면 `selection_required`

`recipient_name_hint`가 없으면 Agent는 이 API를 호출하지 않고 바로 `UI-RECIPIENT-SELECT`를 요청한다. Frontend의 수취인 선택 화면에 표시할 최근 수취인, 이름 후보와 신규 계좌번호 검증은 Frontend와 Backend가 직접 처리한다.

---

## 14. 타인송금 Prepare

### 14.1 기본 정보

```http
POST /api/v1/agent-tools/transfers/external:prepare
Idempotency-Key: idem_prepare_123
```

- 호출자: Agent
- 상태 변경: Confirmation 생성
- 계약 ID: `API-EXTERNAL-TRANSFER-PREPARE`
- 사용 Workflow: `wf_external_transfer / prepare_external_transfer`
- 멱등성: 필수

### 14.2 기존 수취인 요청

```json
{
  "from_account_id": "acc_001",
  "to_recipient_id": "rcp_001",
  "amount": 50000,
  "currency": "KRW"
}
```

### 14.3 신규 수취인 요청

```json
{
  "from_account_id": "acc_001",
  "to_recipient_candidate_id": "rcp_candidate_001",
  "amount": 50000,
  "currency": "KRW"
}
```

`to_recipient_id`와 `to_recipient_candidate_id` 중 정확히 하나만 전달한다. `to_recipient_candidate_id`는 Frontend와 Backend의 신규 계좌 검증 흐름에서 발급한 참조 ID다.

| 필드 | 타입 | 필수 | 제한 |
| --- | --- | --- | --- |
| `from_account_id` | string | 필수 | 현재 사용자가 소유한 출금 가능 계좌 ID |
| `to_recipient_id` | string | 조건부 필수 | 기존 수취인 송금 시 사용 |
| `to_recipient_candidate_id` | string | 조건부 필수 | 신규 검증 수취인 송금 시 사용 |
| `amount` | integer | 필수 | 0보다 큰 정수, 실제 허용 금액은 Backend가 판정 |
| `currency` | string | 필수 | 현재 범위에서는 `KRW` |

Agent는 `user_id`, 수취인 이름, 은행 코드, 계좌번호 원문과 `memo`를 전달하지 않는다.

### 14.4 승인 준비 완료 응답

```json
{
  "success": true,
  "message": "송금 요청을 확인했습니다.",
  "data": {
    "outcome": "ready_for_confirmation",
    "confirmation_id": "confirm_123",
    "confirmation_view": {
      "from_account": {
        "account_id": "acc_001",
        "account_alias": "생활비",
        "bank_name": "신한은행",
        "masked_account_number": "3333-**-1234567"
      },
      "recipient": {
        "name": "홍*동",
        "bank_name": "국민은행",
        "masked_account_number": "110-***-123456"
      },
      "amount": 50000,
      "fee": 0,
      "total_debit": 50000,
      "currency": "KRW",
      "variant": "warning",
      "warning_codes": [
        "NEW_RECIPIENT"
      ],
      "expires_at": "2026-07-13T10:05:00+09:00"
    }
  }
}
```

`ready_for_confirmation`은 실제 송금, 사용자 승인 또는 추가 인증 완료를 의미하지 않는다. Backend가 현재 송금 조건을 Confirmation에 고정하고 최종 송금 확인 화면을 표시할 수 있다는 뜻이다. 모든 타인송금은 사용자 승인 후 별도의 추가 인증 단계를 거친다.

### 14.5 수정 필요 응답

사용자가 출금 계좌, 수취인 또는 금액을 수정하면 진행할 수 있는 경우에는 HTTP `200`과 `correction_required`를 반환한다.

```json
{
  "success": true,
  "message": "송금 조건을 수정해야 합니다.",
  "data": {
    "outcome": "correction_required",
    "reason": "insufficient_balance",
    "correction_view": {
      "title": "출금 계좌 또는 금액을 변경해 주세요.",
      "allowed_change_targets": [
        "from_account",
        "amount"
      ]
    }
  }
}
```

Agent는 `reason`만 보고 수정 Route를 추측하지 않는다. Backend가 반환한 `correction_view.allowed_change_targets`에 포함된 항목만 수정 UI에 제공한다. 허용 값은 다음과 같다.

```text
from_account
recipient
amount
```

### 14.6 진행 차단 응답

현재 Workflow의 입력 수정으로 해결할 수 없는 정책 또는 계좌 제한은 HTTP `200`과 `blocked`를 반환한다.

```json
{
  "success": true,
  "message": "현재 송금을 진행할 수 없습니다.",
  "data": {
    "outcome": "blocked",
    "reason": "financial_transaction_restricted",
    "blocked_view": {
      "title": "송금을 진행할 수 없습니다.",
      "description": "금융거래 제한 상태를 확인해 주세요."
    }
  }
}
```

`blocked`에서는 Confirmation을 생성하지 않으며 Agent는 수정 화면을 표시하지 않고 차단 안내 후 Workflow를 종료한다.

### 14.7 Backend 검증

- 출금 계좌 소유권과 상태
- 수취인 또는 수취인 후보 검증 상태
- 금액 형식과 최소, 최대 금액
- 현재 출금 가능 잔액
- 1회 및 일일 한도
- 수수료
- 신규 수취인과 고액 송금 위험 정보
- 정책과 차단 조건

Backend는 승인 대상 계좌, 수취인, 금액과 수수료를 Confirmation에 고정한다.

Prepare는 실제 원장을 변경하지 않는다. Backend 또는 원장 시스템 장애는 업무 `outcome`으로 반환하지 않고 `success=false`, `error.category=technical_error`인 공통 오류 응답으로 반환한다.

### 14.8 Agent Route 매핑

| Backend 결과 | Agent Route |
| --- | --- |
| `ready_for_confirmation` | `request_external_transfer_approval` |
| `correction_required` | `request_external_transfer_correction` |
| `blocked` | `emit_external_transfer_blocked` |
| `success=false / technical_error` | 공통 조건에 해당하면 동일한 논리 요청을 최대 1회 재시도하고, 실패하면 `emit_external_transfer_error` |

---

## 15. 추가 인증 Context 생성

### 15.1 기본 정보

```http
POST /api/v1/agent-tools/auth-contexts
Idempotency-Key: idem_auth_123
```

- 호출자: Agent
- 상태 변경: Auth Context 생성
- 계약 ID: `API-AUTH-CONTEXT-CREATE`
- 사용 Workflow: `wf_external_transfer / create_external_auth_context`, `wf_internal_transfer / create_internal_auth_context`
- 멱등성: 필수

### 15.2 요청

```json
{
  "confirmation_id": "confirm_123"
}
```

송금 유형, 사용자와 송금 조건은 Confirmation에 이미 고정되어 있으므로 `purpose`, `user_id`와 송금 업무 필드를 중복해서 전달하지 않는다.

### 15.3 성공 응답

```json
{
  "success": true,
  "message": "추가 인증을 준비했습니다.",
  "data": {
    "outcome": "authentication_required",
    "auth_context_id": "auth_123",
    "auth_request_view": {
      "title": "추가 인증이 필요합니다.",
      "description": "송금을 계속하려면 본인 인증을 완료해 주세요.",
      "available_methods": [
        "biometric",
        "password"
      ],
      "expires_at": "2026-07-13T10:08:00+09:00"
    }
  }
}
```

### 15.4 Backend 검증

- Confirmation 사용자와 상태
- Confirmation 승인 완료 여부
- Confirmation 만료
- 같은 Confirmation의 활성 Auth Context 존재 여부

Agent에는 인증 Assertion, PIN, 생체인증 결과 원문을 반환하지 않는다.

Agent는 `auth_context_id`와 `auth_request_view`를 State에 저장한 다음 별도의 `authentication_required` Webhook을 전송하고 Workflow를 중단한다. Backend는 Frontend의 추가 인증 결과를 검증하고 저장한 뒤 다음 값으로 Agent의 Workflow를 재개한다.

```json
{
  "auth_context_id": "auth_123",
  "auth_status": "verified"
}
```

`auth_status` Enum은 `verified`, `failed`, `cancelled`, `expired`다. Agent는 인증 상태를 조회하거나 폴링하지 않으며 `verified`인 경우에만 Execute로 이동한다. `failed` 또는 `expired`이면 해당 송금 Workflow의 재인증 선택 UI가 `auth_retry_outcome=retry|cancelled`를 입력받는다. `retry`이면 새 Auth Context를 생성하고, 재인증 선택 또는 최초 인증 화면에서 `cancelled`이면 추가 취소 Webhook 없이 Workflow를 종료한다.

---

## 16. 타인송금 Execute

### 16.1 기본 정보

```http
POST /api/v1/agent-tools/transfers/external
Idempotency-Key: idem_transfer_123
```

- 호출자: Agent
- 상태 변경: 금융 원장 변경
- 계약 ID: `API-EXTERNAL-TRANSFER-EXECUTE`
- 사용 Workflow: `wf_external_transfer / execute_external_transfer`
- 멱등성: 필수

### 16.2 요청

```json
{
  "confirmation_id": "confirm_123",
  "auth_context_id": "auth_123"
}
```

모든 타인송금은 추가 인증이 필수이므로 `confirmation_id`와 `auth_context_id`를 모두 전달한다. Agent는 Confirmation에 고정된 출금 계좌, 수취인, 금액과 통화를 Execute 요청에 다시 전달하지 않는다.

### 16.3 송금 완료 응답

```json
{
  "success": true,
  "message": "송금이 완료되었습니다.",
  "data": {
    "outcome": "completed",
    "transaction_id": "txn_123",
    "completed_at": "2026-07-13T10:04:00+09:00"
  }
}
```

`amount`와 `currency`는 Workflow State와 Confirmation에 이미 존재하므로 Execute 응답에 중복해서 반환하지 않는다. Agent는 완료 Webhook에서 Execute 응답의 `transaction_id`, `completed_at`과 Prepare 응답으로 보관한 `confirmation_view`의 `from_account`, `recipient`, `amount`, `currency`를 조합한다. 완료 화면을 위해 계좌나 수취인을 다시 조회하거나 Execute 응답에 같은 표시 데이터를 중복해서 요구하지 않는다.

### 16.4 수정 필요 응답

Prepare 이후 잔액, 한도 또는 계좌 상태가 바뀌어 사용자 입력 수정이 필요한 경우 `correction_required`를 반환한다.

```json
{
  "success": true,
  "message": "송금 조건을 수정해야 합니다.",
  "data": {
    "outcome": "correction_required",
    "reason": "insufficient_balance",
    "correction_view": {
      "title": "출금 계좌 또는 금액을 변경해 주세요.",
      "allowed_change_targets": [
        "from_account",
        "amount"
      ]
    }
  }
}
```

Backend는 기존 Confirmation과 Auth Context를 재사용할 수 없게 처리한다. Agent는 Backend가 허용한 항목을 수정한 뒤 Prepare, 사용자 승인과 추가 인증을 다시 수행한다.

### 16.5 재인증 필요 응답

Confirmation은 승인된 유효 상태지만 Auth Context만 만료된 경우 `reauthentication_required`를 반환한다.

```json
{
  "success": true,
  "message": "추가 인증을 다시 진행해야 합니다.",
  "data": {
    "outcome": "reauthentication_required",
    "reason": "auth_context_expired"
  }
}
```

Backend는 만료된 Auth Context를 재사용할 수 없게 처리한다. Agent는 유효한 `confirmation_id`를 유지하고 새로운 Auth Context 생성 단계로 이동한다. Confirmation도 만료되었거나 무효화되었다면 재인증이 아니라 새로운 Prepare와 사용자 승인이 필요하다.

### 16.6 진행 차단 응답

정책 또는 금융거래 제한으로 실행할 수 없는 경우 `blocked`를 반환한다. Backend는 Confirmation과 Auth Context를 재사용할 수 없게 처리하며 Agent는 차단 안내 후 Workflow를 종료한다.

```json
{
  "success": true,
  "message": "송금을 실행할 수 없습니다.",
  "data": {
    "outcome": "blocked",
    "reason": "financial_transaction_restricted",
    "blocked_view": {
      "title": "송금을 진행할 수 없습니다.",
      "description": "금융거래 제한 상태를 확인해 주세요."
    }
  }
}
```

`blocked`는 자동 재시도하지 않는다. Agent는 `blocked_view`를 `emit_external_transfer_blocked` Webhook에 그대로 전달한다. 시스템 장애와 Timeout은 `blocked`가 아니라 `success=false`, `error.category=technical_error`로 구분하며 공통 조건에 해당할 때만 동일 요청을 최대 1회 재시도한다.

### 16.7 실행 직전 Backend 검증

- Execution Context 사용자
- Confirmation 대상 사용자와 목적
- Confirmation 승인 여부와 만료
- Confirmation 미실행 상태
- Auth Context 소유자, `verified` 상태와 만료
- 승인 당시 계좌, 수취인, 금액과 고정 데이터
- 출금 계좌 현재 소유권과 상태
- 수취인 현재 상태
- 현재 잔액과 이체 한도
- 실행 직전 정책
- `Idempotency-Key` 중복과 Body 일치

### 16.8 Transaction

Backend는 다음 작업을 하나의 일관된 실행 경계에서 처리한다.

```text
멱등성 키 선점
-> 최종 검증
-> 원장 변경
-> Transaction 생성
-> Confirmation executed 처리
-> 금융 감사 로그 기록
-> 멱등성 결과 저장
```

통신 Timeout처럼 실행 결과를 확인할 수 없는 기술 오류에는 새로운 멱등성 키를 생성하지 않는다. Agent는 같은 논리 Execute 요청에 같은 `Idempotency-Key`를 사용하며 Backend는 이미 완료된 요청이면 최초 결과를 다시 반환한다.

### 16.9 Agent Route 매핑

| Backend 결과 | Agent Route |
| --- | --- |
| `completed` | `emit_external_transfer_result` |
| `correction_required` | `route_external_transfer_correction` 이후 단일 자동 Route 또는 복수 대상 선택 |
| `reauthentication_required` | `start_external_auth` |
| `blocked` | `emit_external_transfer_blocked` |
| `success=false / technical_error` | 공통 조건에 해당하면 동일한 논리 요청을 최대 1회 재시도하고, 실패하면 `emit_external_transfer_error` |

---

## 17. 본인 계좌 간 이체 Prepare

### 17.1 기본 정보

```http
POST /api/v1/agent-tools/transfers/internal:prepare
Idempotency-Key: idem_internal_prepare_123
```

- 호출자: Agent
- 상태 변경: Confirmation 생성
- 계약 ID: `API-INTERNAL-TRANSFER-PREPARE`
- 사용 Workflow: `wf_internal_transfer / prepare_internal_transfer`
- 멱등성: 필수

### 17.2 요청

```json
{
  "from_account_id": "acc_001",
  "to_account_id": "acc_002",
  "amount": 100000,
  "currency": "KRW"
}
```

| 필드 | 타입 | 필수 | 제한 |
| --- | --- | --- | --- |
| `from_account_id` | string | 필수 | 현재 사용자가 소유한 출금 가능 계좌 ID |
| `to_account_id` | string | 필수 | 현재 사용자가 소유한 입금 가능 계좌 ID |
| `amount` | integer | 필수 | 0보다 큰 정수, 실제 허용 금액은 Backend가 판정 |
| `currency` | string | 필수 | 현재 범위에서는 `KRW` |

`from_account_id`와 `to_account_id`는 서로 달라야 한다. Agent는 `user_id`, 계좌번호 원문과 `memo`를 전달하지 않는다.

### 17.3 승인 준비 완료 응답

```json
{
  "success": true,
  "message": "이체 요청을 확인했습니다.",
  "data": {
    "outcome": "ready_for_confirmation",
    "confirmation_id": "confirm_internal_123",
    "confirmation_view": {
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
      "fee": 0,
      "total_debit": 100000,
      "currency": "KRW",
      "expires_at": "2026-07-13T10:05:00+09:00"
    }
  }
}
```

본인 계좌 간 이체도 사용자 승인 후 추가 인증을 필수로 수행한다. 추가 인증 여부는 고정 정책이므로 Prepare 응답에 `additional_auth_required` 같은 선택 플래그를 반환하지 않는다.

### 17.4 수정 필요 응답

```json
{
  "success": true,
  "message": "이체 조건을 수정해야 합니다.",
  "data": {
    "outcome": "correction_required",
    "reason": "insufficient_balance",
    "correction_view": {
      "title": "출금 계좌 또는 금액을 변경해 주세요.",
      "allowed_change_targets": [
        "from_account",
        "amount"
      ]
    }
  }
}
```

Agent는 `correction_view.allowed_change_targets`에 포함된 항목만 수정 UI에 제공한다. 허용 값은 `from_account`, `to_account`, `amount`다.

Agent는 `allowed_change_targets`가 하나면 해당 수정 Route로 바로 이동하고, 두 개 이상이면 `request_internal_transfer_correction`에서 사용자 선택을 받는다. 배열이 비었거나 허용되지 않은 값이 있으면 계약 오류로 처리한다. 사용자 선택은 Backend가 허용 목록과 대조한 뒤 `correction_selection_outcome=selected`, `change_target`으로 Agent를 재개하고, 취소는 `correction_selection_outcome=cancelled`, `change_target=null`로 재개한다.

### 17.5 진행 차단 응답

현재 Workflow의 입력 수정으로 해결할 수 없는 정책 또는 금융거래 제한은 `outcome=blocked`로 반환한다. 이 경우 Confirmation을 생성하지 않고 Agent는 차단 안내 후 Workflow를 종료한다.

```json
{
  "success": true,
  "message": "현재 이체를 진행할 수 없습니다.",
  "data": {
    "outcome": "blocked",
    "reason": "transfer_restricted",
    "blocked_view": {
      "title": "이체를 진행할 수 없습니다.",
      "description": "현재 계좌 상태에서는 이체를 진행할 수 없습니다. 자세한 내용은 고객센터에 문의해 주세요."
    }
  }
}
```

`blocked_view`는 사용자에게 표시할 수 있도록 Backend가 제공하는 안내 데이터다. Agent는 내부 정책 코드나 `reason`을 사용자 문장으로 변환하지 않고 `blocked_view`를 차단 Webhook에 그대로 전달한다.

### 17.6 Backend 검증

- 두 계좌가 모두 인증된 현재 사용자 소유인지
- 두 계좌가 서로 다른지
- 출금 계좌가 활성 상태이고 출금 가능한지
- 입금 계좌가 활성 상태이고 입금 가능한지
- 이체 금액과 통화가 유효한지
- 현재 출금 가능 잔액이 충분한지
- 회당·일일 이체 한도를 넘지 않는지
- 계좌와 사용자에게 거래 제한이 없는지

Backend는 승인 대상 계좌, 금액과 수수료를 Confirmation에 고정한다. Prepare는 실제 원장을 변경하지 않는다. 시스템 장애는 업무 `outcome`이 아니라 `success=false`, `error.category=technical_error`인 공통 오류로 반환한다.

### 17.7 Agent Route 매핑

| Backend 결과 | Agent Route |
| --- | --- |
| `ready_for_confirmation` | `request_internal_transfer_approval` |
| `correction_required` | `route_internal_transfer_correction` 이후 단일 자동 Route 또는 복수 대상 선택 |
| `blocked` | `emit_internal_transfer_blocked` |
| `success=false / technical_error` | 공통 조건에 해당하면 동일한 논리 요청을 최대 1회 재시도하고, 실패하면 `emit_internal_transfer_error` |

---

## 18. 본인 계좌 간 이체 Execute

### 18.1 기본 정보

```http
POST /api/v1/agent-tools/transfers/internal
Idempotency-Key: idem_internal_123
```

- 호출자: Agent
- 상태 변경: 금융 원장 변경
- 계약 ID: `API-INTERNAL-TRANSFER-EXECUTE`
- 사용 Workflow: `wf_internal_transfer / execute_internal_transfer`
- 멱등성: 필수

### 18.2 요청

```json
{
  "confirmation_id": "confirm_internal_123",
  "auth_context_id": "auth_internal_123"
}
```

본인 계좌 간 이체도 추가 인증이 필수이므로 두 필드를 모두 전달한다. Confirmation에 고정된 출금 계좌, 입금 계좌, 금액과 통화는 다시 전달하지 않는다.

### 18.3 이체 완료 응답

```json
{
  "success": true,
  "message": "계좌 이체가 완료되었습니다.",
  "data": {
    "outcome": "completed",
    "transaction_id": "txn_internal_123",
    "completed_at": "2026-07-13T10:04:00+09:00"
  }
}
```

Execute API는 금융 실행 결과인 `transaction_id`와 `completed_at`만 반환한다. Agent는 완료 Webhook에서 이 두 값과 Prepare 응답으로 보관한 `confirmation_view`의 `from_account`, `to_account`, `amount`, `currency`를 조합한다. 완료 화면을 위해 계좌를 다시 조회하거나 Execute 응답에 같은 표시 데이터를 중복해서 요구하지 않는다.

### 18.4 수정 필요 응답

Prepare 이후 잔액, 한도 또는 계좌 상태가 바뀌어 입력 수정이 필요한 경우 `correction_required`를 반환하고 기존 Confirmation과 Auth Context를 재사용할 수 없게 처리한다.

```json
{
  "success": true,
  "message": "이체 조건을 수정해야 합니다.",
  "data": {
    "outcome": "correction_required",
    "reason": "insufficient_balance",
    "correction_view": {
      "allowed_change_targets": [
        "from_account",
        "amount"
      ]
    }
  }
}
```

### 18.5 재인증 필요 응답

Confirmation은 승인된 유효 상태지만 Auth Context만 만료된 경우 `reauthentication_required`를 반환한다. Agent는 `confirmation_id`와 Confirmation에 고정된 송금 조건을 유지하고 기존 인증 State만 제거한다. 이후 `auth_attempt`를 증가시켜 새로운 Auth Context를 생성하고, 인증 성공 후 Prepare와 사용자 승인을 반복하지 않고 Execute를 다시 호출한다. Confirmation도 만료되었거나 무효화된 경우에는 재인증만으로 실행하지 않고 새로운 Prepare와 사용자 승인을 수행한다.

```json
{
  "success": true,
  "message": "추가 인증을 다시 진행해야 합니다.",
  "data": {
    "outcome": "reauthentication_required",
    "reason": "auth_context_expired"
  }
}
```

### 18.6 진행 차단 응답

정책 또는 금융거래 제한으로 실행할 수 없는 경우 `blocked`를 반환하고 Agent는 차단 안내 후 Workflow를 종료한다.

```json
{
  "success": true,
  "message": "현재 이체를 진행할 수 없습니다.",
  "data": {
    "outcome": "blocked",
    "reason": "transfer_restricted",
    "blocked_view": {
      "title": "이체를 진행할 수 없습니다.",
      "description": "현재 계좌 상태에서는 이체를 진행할 수 없습니다. 자세한 내용은 고객센터에 문의해 주세요."
    }
  }
}
```

`blocked`는 자동 재시도하지 않는다. Agent는 `blocked_view`를 `emit_internal_transfer_blocked` Webhook에 그대로 전달한다. 시스템 장애와 Timeout은 `blocked`가 아니라 `success=false`, `error.category=technical_error`로 구분하며 공통 조건에 해당할 때만 동일 요청을 최대 1회 재시도한다.

### 18.7 실행 직전 Backend 검증과 Transaction

Backend는 Confirmation 승인·만료·미실행 상태, Auth Context의 `verified` 상태와 만료, 계좌 소유권과 상태, 현재 잔액·한도·정책을 다시 검증한다. 출금, 입금, Transaction 생성, Confirmation 실행 처리, 금융 Audit과 멱등성 결과 저장은 하나의 일관된 실행 경계에서 처리한다.

기술 오류와 Timeout에는 새로운 멱등성 키를 생성하지 않는다. 같은 논리 요청에는 같은 키를 사용하며 이미 실행된 요청이면 Backend가 최초 결과를 반환한다.

### 18.8 Agent Route 매핑

| Backend 결과 | Agent Route |
| --- | --- |
| `completed` | `emit_internal_transfer_result` |
| `correction_required` | `route_internal_transfer_correction` 이후 단일 자동 Route 또는 복수 대상 선택 |
| `reauthentication_required` | `start_internal_auth` |
| `blocked` | `emit_internal_transfer_blocked` |
| `success=false / technical_error` | 공통 조건에 해당하면 동일한 논리 요청을 최대 1회 재시도하고, 실패하면 `emit_internal_transfer_error` |

---

## 19. 기본 출금 계좌 변경 Prepare

### 19.1 기본 정보

```http
POST /api/v1/agent-tools/settings/default-account:prepare
Idempotency-Key: idem_default_prepare_123
```

- 호출자: Agent
- 상태 변경: Confirmation 생성
- 계약 ID: `API-DEFAULT-ACCOUNT-PREPARE`
- 사용 Workflow: `wf_set_default_account / prepare_default_account_change`
- 멱등성: 필수

### 19.2 요청

```json
{
  "account_id": "acc_002"
}
```

- `account_id`: 새롭게 기본 출금 계좌로 설정할 계좌의 식별자
- 사용자는 `X-Execution-Context-Id`를 통해 식별한다.
- 현재 기본 출금 계좌는 Backend가 확인하므로 Agent가 전달하지 않는다.

### 19.3 승인 준비 완료 응답

```json
{
  "success": true,
  "message": "기본 출금 계좌 변경 내용을 확인했습니다.",
  "data": {
    "outcome": "ready_for_confirmation",
    "confirmation_id": "confirm_default_123",
    "confirmation_view": {
      "current_default_account": {
        "account_id": "acc_001",
        "bank_name": "카카오뱅크",
        "account_alias": "생활비",
        "masked_account_number": "3333-**-1234567"
      },
      "new_default_account": {
        "account_id": "acc_002",
        "bank_name": "카카오뱅크",
        "account_alias": "급여",
        "masked_account_number": "3333-**-7654321"
      },
      "expires_at": "2026-07-13T10:05:00+09:00"
    }
  }
}
```

`current_default_account`와 `new_default_account`는 변경 전후를 확인하기 위한 승인 화면용 데이터이며 별도 Agent State로 분리하지 않는다. 설정 변경에는 추가 인증을 요구하지 않는다.

### 19.4 변경 없음 응답

대상 계좌가 이미 기본 출금 계좌라면 오류가 아니라 `unchanged`를 반환하며 Confirmation을 생성하지 않는다. Agent는 변경 완료와 동일한 `setting_result` UI 계약을 사용하되 `outcome=unchanged`로 결과를 전송한다.

```json
{
  "success": true,
  "message": "이미 기본 출금 계좌로 설정되어 있습니다.",
  "data": {
    "outcome": "unchanged",
    "account_id": "acc_002"
  }
}
```

### 19.5 수정 필요 응답

다른 계좌를 선택하면 진행할 수 있는 경우 `correction_required`를 반환한다.

```json
{
  "success": true,
  "message": "다른 계좌를 선택해 주세요.",
  "data": {
    "outcome": "correction_required",
    "reason": "account_not_eligible",
    "correction_view": {
      "allowed_change_targets": [
        "account"
      ]
    }
  }
}
```

### 19.6 Backend 검증

Backend는 다음 항목을 검증한다.

- 대상 계좌가 현재 사용자 소유인지
- 대상 계좌가 활성 상태인지
- 대상 계좌가 출금 가능한 계좌인지
- 대상 계좌가 이미 기본 출금 계좌인지
- 현재 기본 출금 계좌와 대상 계좌가 다른지

Backend는 변경 전후 계좌를 Confirmation에 고정한다. 설정 변경 자체가 제한된 경우 `blocked`, 시스템 장애는 `success=false / technical_error`로 반환한다.

### 19.7 Agent Route 매핑

| Backend 결과 | Agent Route |
| --- | --- |
| `ready_for_confirmation` | `request_default_account_approval` |
| `unchanged` | `emit_default_account_unchanged` |
| `correction_required` | `reset_default_account_target` 이후 `resolve_default_account` |
| `blocked` | `emit_default_account_blocked` |
| `success=false / technical_error` | 공통 조건에 해당하면 동일한 논리 요청을 최대 1회 재시도하고, 실패하면 `emit_default_account_error` |

---

## 20. 기본 출금 계좌 변경 Execute

### 20.1 기본 정보

```http
POST /api/v1/agent-tools/settings/default-account
Idempotency-Key: idem_default_123
```

- 호출자: Agent
- 상태 변경: 기본 출금 계좌 변경
- 계약 ID: `API-DEFAULT-ACCOUNT-EXECUTE`
- 사용 Workflow: `wf_set_default_account / execute_default_account_change`
- 멱등성: 필수

### 20.2 요청

```json
{
  "confirmation_id": "confirm_default_123"
}
```

### 20.3 성공 응답

```json
{
  "success": true,
  "message": "기본 출금 계좌를 변경했습니다.",
  "data": {
    "outcome": "completed",
    "account_id": "acc_002",
    "completed_at": "2026-07-13T10:04:00+09:00"
  }
}
```

Backend는 Confirmation에서 변경 대상 계좌를 확인하므로 Agent가 `account_id`를 다시 전달하지 않는다. 응답의 `account_id`는 Backend가 실제로 반영한 최종 계좌를 의미한다.

### 20.4 수정 필요 응답

Execute 시점에 대상 계좌가 비활성화되는 등 다른 계좌를 선택해야 하는 경우 `correction_required`를 반환하고 기존 Confirmation을 재사용할 수 없게 처리한다.

```json
{
  "success": true,
  "message": "다른 계좌를 선택해 주세요.",
  "data": {
    "outcome": "correction_required",
    "reason": "account_not_eligible",
    "correction_view": {
      "allowed_change_targets": [
        "account"
      ]
    }
  }
}
```

### 20.5 Backend Transaction

Backend는 Confirmation 승인·만료·미실행 상태와 대상 계좌의 현재 소유권·활성·출금 가능 상태를 확인한다. 기존 기본 출금 계좌 해제, 새 기본 출금 계좌 설정, Confirmation 실행 처리, 설정 변경 Audit과 멱등성 결과 저장을 하나의 트랜잭션으로 처리한다.

Backend는 구현 방식과 관계없이 사용자별 기본 출금 계좌가 동시에 하나만 존재한다는 결과를 보장해야 한다. 설정 변경 자체가 제한된 경우 `blocked`, 시스템 장애는 `success=false / technical_error`로 반환한다.

### 20.6 Agent Route 매핑

| Backend 결과 | Agent Route |
| --- | --- |
| `completed` | `emit_default_account_result` |
| `correction_required` | `reset_default_account_target` 이후 `resolve_default_account` |
| `blocked` | `emit_default_account_blocked` |
| `success=false / technical_error` | 공통 조건에 해당하면 동일한 논리 요청을 최대 1회 재시도하고, 실패하면 `emit_default_account_error` |

---

## 21. 계좌 별칭 변경 Prepare

### 21.1 기본 정보

```http
POST /api/v1/agent-tools/settings/account-alias:prepare
Idempotency-Key: idem_alias_prepare_123
```

- 호출자: Agent
- 상태 변경: Confirmation 생성
- 계약 ID: `API-ACCOUNT-ALIAS-PREPARE`
- 사용 Workflow: `wf_set_account_alias / prepare_account_alias_change`
- 멱등성: 필수

### 21.2 요청

```json
{
  "account_id": "acc_001",
  "alias": "여행 자금"
}
```

### 21.3 Backend 검증

- 계좌 소유권
- 별칭 길이와 허용 문자
- 금지 표현
- 사용자 내 별칭 중복 정책

### 21.4 승인 준비 완료 응답

```json
{
  "success": true,
  "message": "계좌 별칭 변경 내용을 확인했습니다.",
  "data": {
    "outcome": "ready_for_confirmation",
    "confirmation_id": "confirm_alias_123",
    "confirmation_view": {
      "account": {
        "account_id": "acc_001",
        "bank_name": "신한은행",
        "masked_account_number": "110-***-123456"
      },
      "alias": "여행 자금",
      "expires_at": "2026-07-13T10:05:00+09:00"
    }
  }
}
```

`account_label`과 `current_alias`는 요청, Workflow State와 승인 화면에 포함하지 않는다. 계좌 객체는 별칭의 기존 값을 보여주기 위한 것이 아니라 변경 대상 계좌를 식별하기 위한 마스킹 정보다.

### 21.5 변경 없음 응답

현재 별칭과 정규화된 `alias`가 같으면 오류가 아니라 `unchanged`를 반환하며 Confirmation을 생성하지 않는다. Agent는 변경 완료와 동일한 `setting_result` UI 계약을 사용하되 `outcome=unchanged`로 결과를 전송한다.

```json
{
  "success": true,
  "message": "이미 같은 별칭으로 설정되어 있습니다.",
  "data": {
    "outcome": "unchanged",
    "account_id": "acc_001",
    "alias": "여행 자금"
  }
}
```

### 21.6 수정 필요 응답

```json
{
  "success": true,
  "message": "다른 별칭을 입력해 주세요.",
  "data": {
    "outcome": "correction_required",
    "reason": "alias_not_allowed",
    "correction_view": {
      "allowed_change_targets": [
        "alias"
      ]
    }
  }
}
```

대상 계좌를 변경해야 하는 경우 `allowed_change_targets`에 `account`를 반환한다. 허용 값은 `account`, `alias`다. 이 Endpoint의 `correction_required`는 배열에 정확히 하나의 값만 반환한다. 여러 수정 사유가 있으면 Backend가 먼저 수정할 대상 하나를 반환하고, 수정 후 새로운 Prepare에서 나머지 조건을 다시 평가한다. 배열이 비어 있거나 두 개 이상이면 Agent는 수정 대상을 임의로 선택하지 않고 계약 오류로 처리한다.

### 21.7 Agent Route 매핑

| Backend 결과 | Agent Route |
| --- | --- |
| `ready_for_confirmation` | `request_account_alias_approval` |
| `unchanged` | `emit_account_alias_unchanged` |
| `correction_required / account` | `reset_account_alias_target` 이후 `resolve_account_alias_target` |
| `correction_required / alias` | `reset_account_alias_value` 이후 `request_account_alias_input` |
| `blocked` | `emit_account_alias_blocked` |
| `success=false / technical_error` | 공통 조건에 해당하면 동일한 논리 요청을 최대 1회 재시도하고, 실패하면 `emit_account_alias_error` |

---

## 22. 계좌 별칭 변경 Execute

### 22.1 기본 정보

```http
POST /api/v1/agent-tools/settings/account-alias
Idempotency-Key: idem_alias_123
```

- 호출자: Agent
- 상태 변경: 계좌 별칭 변경
- 계약 ID: `API-ACCOUNT-ALIAS-EXECUTE`
- 사용 Workflow: `wf_set_account_alias / execute_account_alias_change`
- 멱등성: 필수

### 22.2 요청

```json
{
  "confirmation_id": "confirm_alias_123"
}
```

### 22.3 성공 응답

```json
{
  "success": true,
  "message": "계좌 별칭을 변경했습니다.",
  "data": {
    "outcome": "completed",
    "account_id": "acc_001",
    "alias": "여행 자금",
    "completed_at": "2026-07-13T10:04:00+09:00"
  }
}
```

Backend는 Confirmation에 고정된 별칭을 적용한다. Agent가 Execute 요청에서 별칭을 다시 전달하지 않는다.

### 22.4 수정 필요 응답

Execute 시점에 별칭 정책이나 계좌 상태가 바뀌면 `correction_required`를 반환하고 기존 Confirmation을 재사용할 수 없게 처리한다.

```json
{
  "success": true,
  "message": "다른 별칭을 입력해 주세요.",
  "data": {
    "outcome": "correction_required",
    "reason": "alias_not_allowed",
    "correction_view": {
      "allowed_change_targets": [
        "alias"
      ]
    }
  }
}
```

대상 계좌를 변경해야 하면 `allowed_change_targets`에 `account`를 반환한다. 이 Endpoint도 `correction_required`마다 정확히 하나의 수정 대상만 반환한다. 배열이 비어 있거나 두 개 이상이면 Agent는 계약 오류로 처리한다.

### 22.5 Backend Transaction

Backend는 Confirmation 승인·만료·미실행 상태, 계좌 소유권과 활성 상태, 현재 별칭 정책을 다시 검증한다. 별칭 변경, Confirmation 실행 처리, 설정 변경 Audit과 멱등성 결과 저장을 하나의 트랜잭션으로 처리한다.

설정 변경 자체가 제한된 경우 `blocked`, 시스템 장애는 `success=false / technical_error`로 반환한다. 기술 오류와 Timeout 재시도에는 동일한 멱등성 키를 사용한다.

### 22.6 Agent Route 매핑

| Backend 결과 | Agent Route |
| --- | --- |
| `completed` | `emit_account_alias_result` |
| `correction_required / account` | `reset_account_alias_target` 이후 `resolve_account_alias_target` |
| `correction_required / alias` | `reset_account_alias_value` 이후 `request_account_alias_input` |
| `blocked` | `emit_account_alias_blocked` |
| `success=false / technical_error` | 공통 조건에 해당하면 동일한 논리 요청을 최대 1회 재시도하고, 실패하면 `emit_account_alias_error` |

---

## 23. 사용자 승인과 수정 처리

Agent는 Prepare 응답의 `confirmation_id`를 이름을 바꾸지 않고 승인 Webhook에 전달한다.

```json
{
  "event_type": "need_approval",
  "confirmation_id": "confirm_123",
  "metadata": {
    "ui": {
      "type": "confirm_modal",
      "payload": {
        "title": "요청 내용을 확인해 주세요."
      }
    }
  }
}
```

`metadata.ui.payload`에는 Prepare 응답의 `confirmation_view`를 사용한다. Agent는 전체 계좌번호와 인증 원문을 추가하지 않는다.

Frontend는 기존 Backend API로 결정을 제출한다.

```http
POST /api/v1/agent/approve
```

승인:

```json
{
  "confirmation_id": "confirm_123",
  "decision": "approve"
}
```

수정:

```json
{
  "confirmation_id": "confirm_123",
  "decision": "modify",
  "change_target": "amount"
}
```

취소:

```json
{
  "confirmation_id": "confirm_123",
  "decision": "cancel"
}
```

`decision` Enum은 `approve`, `modify`, `cancel`이다. 수정 요청에는 변경된 금융 값을 함께 보내지 않고 `change_target`만 전달한다.

Backend 처리 원칙:

1. 사용자와 Chat Session 소유권 확인
2. 요청의 `confirmation_id`와 Pending Approval 일치 확인
3. Confirmation 사용자, 목적, 상태와 만료 검증
4. `approve`이면 승인 상태 저장 후 Agent 재개
5. `modify`이면 기존 Confirmation을 `invalidated` 처리하고 Agent 재개
6. `cancel`이면 Confirmation을 취소하고 Agent 재개
7. 수정된 값은 별도 입력 UI와 Backend 검증을 거쳐 Agent에 전달
8. 수정값으로 새로운 Prepare와 Confirmation 생성

Backend가 Agent를 재개하는 값은 다음과 같다.

```json
{
  "confirmation_id": "confirm_123",
  "approval_outcome": "change_requested",
  "change_target": "amount"
}
```

Frontend가 Backend에 보내는 `decision`과 Backend가 Agent에 전달하는 `approval_outcome`은 역할이 다르다.

| Frontend `decision` | Agent `approval_outcome` | 의미 |
| --- | --- | --- |
| `approve` | `approved` | 승인 검증과 저장이 완료됨 |
| `modify` | `change_requested` | 기존 Confirmation이 무효화되고 수정 단계로 이동해야 함 |
| `cancel` | `cancelled` | Confirmation이 취소되고 Workflow를 종료해야 함 |

Agent Tool API에는 사용자가 승인했다고 Agent가 임의로 등록하는 Endpoint를 제공하지 않는다. Agent는 승인 상태를 조회하거나 폴링하지 않고 Backend가 검증한 재개 값으로만 Route를 결정한다.

---

## 24. 멱등성 상세 규약

### 24.1 적용 대상

Backend 상태를 변경하는 Prepare, Auth Context 생성과 Execute API에만 `Idempotency-Key`를 적용한다. 계좌·잔액·거래 조회와 수취인 자동 확정에는 사용하지 않는다.

| API 유형 | 멱등성 키 |
| --- | --- |
| 계좌·잔액·거래 조회 | 사용하지 않음 |
| 수취인 자동 확정 | 사용하지 않음 |
| Prepare | 필수 |
| Auth Context 생성 | 필수 |
| Execute | 필수 |
| 설정 변경 Prepare·Execute | 필수 |

### 24.2 키 생성 규칙

```text
external_transfer_prepare:{execution_context_id}:{prepare_attempt}
internal_transfer_prepare:{execution_context_id}:{prepare_attempt}
default_account_prepare:{execution_context_id}:{prepare_attempt}
account_alias_prepare:{execution_context_id}:{prepare_attempt}

external_transfer_auth:{confirmation_id}:{auth_attempt}
internal_transfer_auth:{confirmation_id}:{auth_attempt}

external_transfer_execute:{confirmation_id}:{auth_attempt}
internal_transfer_execute:{confirmation_id}:{auth_attempt}
default_account_execute:{confirmation_id}
account_alias_execute:{confirmation_id}
```

통신 Timeout과 응답 유실 재시도에서는 `prepare_attempt`와 `auth_attempt`를 증가시키지 않는다. 사용자가 업무 값을 수정해 새로운 Prepare를 시작하거나 인증 실패·만료 후 새 Auth Context를 생성할 때만 해당 시도 번호를 증가시킨다.

Execute에는 별도 `execute_attempt`를 만들지 않는다. 추가 인증이 필요한 송금 Execute는 `confirmation_id`와 `auth_attempt`로 키를 생성한다. 동일 인증 시도의 통신 재시도는 같은 키와 Body를 유지하고, 재인증으로 `auth_context_id`가 바뀌면 증가한 `auth_attempt`로 새 키를 생성한다. Backend는 키가 달라져도 Confirmation 상태와 고유 제약으로 동일 Confirmation의 중복 실행을 차단한다. 추가 인증을 사용하지 않는 설정 변경 Execute는 `confirmation_id`로 키를 고정한다.

### 24.3 결과 복원에 필요한 기록 정보

Agent 팀은 Backend가 아래 정보를 기준으로 동일 요청의 최초 결과를 복원할 수 있기를 요구한다. 실제 저장 Schema, 저장소와 보존 방식은 Backend 팀이 결정한다.

```json
{
  "idempotency_key": "external_transfer_execute:confirm_123:1",
  "execution_context_id": "exec_123",
  "operation": "external_transfer_execute",
  "request_hash": "sha256:...",
  "status": "completed",
  "response_status": 200,
  "response_body": {
    "success": true,
    "data": {
      "outcome": "completed",
      "transaction_id": "txn_123",
      "completed_at": "2026-07-13T10:04:00+09:00"
    }
  },
  "created_at": "2026-07-13T10:04:00+09:00",
  "expires_at": "2026-07-14T10:04:00+09:00"
}
```

고유성 기준은 `execution_context_id`, `operation`, `idempotency_key`의 조합이다. `request_hash`는 정규화한 요청 Body를 기준으로 계산한다.

### 24.4 처리 규칙

- 같은 Context, Operation, Key와 같은 Body면 최초 HTTP 상태와 응답 Body 반환
- 같은 Key에 다른 Body면 `IDEMPOTENCY_KEY_CONFLICT` 반환
- 처리 중인 Key면 `409 Conflict`, `Retry-After`와 `IDEMPOTENCY_REQUEST_IN_PROGRESS` 반환
- Agent는 `Retry-After` 이후 같은 Key와 같은 Body로 재호출
- 상태 변경 전 실패는 같은 Key로 재시도 가능
- 상태 변경 후 응답이 유실되면 같은 Key로 기존 결과 복원
- Timeout이 발생해도 새로운 Key 생성 금지

같은 Key에 다른 Body를 사용한 요청 예시는 다음과 같다.

```json
{
  "success": false,
  "error": {
    "category": "request_error",
    "code": "IDEMPOTENCY_KEY_CONFLICT",
    "message": "같은 멱등성 키에 다른 요청을 사용할 수 없습니다."
  }
}
```

처리 중인 요청은 다음처럼 반환한다.

```http
HTTP/1.1 409 Conflict
Retry-After: 1
```

```json
{
  "success": false,
  "error": {
    "category": "request_error",
    "code": "IDEMPOTENCY_REQUEST_IN_PROGRESS",
    "message": "같은 요청을 처리하고 있습니다."
  }
}
```

### 24.5 실행 트랜잭션 경계

Execute는 다음 처리를 하나의 일관된 실행 경계로 관리한다.

```text
멱등성 키 선점
-> 실행 직전 검증
-> 원장 또는 설정 변경
-> 결과 리소스 생성
-> Confirmation executed 처리
-> Audit 기록
-> 멱등성 응답 저장
```

원장 또는 설정 변경 후 응답 저장 여부가 불분명하더라도 Agent는 새 Key를 만들지 않는다. 같은 Key로 재호출하면 Backend가 원장, Confirmation과 멱등성 저장소를 대조하여 최초 결과를 복원한다. 별도의 멱등성 상태 조회 API는 제공하지 않는다.

---

## 25. Audit Log

금융 Audit Log의 정본은 Backend가 관리한다. Agent가 금융 API 결과를 받은 후 `write_audit_log`를 별도로 호출하는 구조는 사용하지 않는다.

```text
Agent
-> 금융 API 요청

Backend
-> 인증과 요청 검증
-> 정책 판정
-> 원장 또는 설정 처리
-> Financial Audit 생성
```

로그의 책임은 다음과 같이 분리한다.

| 로그 | 정본 주체 | 역할 |
| --- | --- | --- |
| Agent Execution Trace | Agent | Step 실행, Route, API 호출 시간과 오류 추적 |
| Financial Audit Log | Backend | 금융 조회, 승인, 인증, 정책 판정과 실행 사실의 정본 |

### 25.1 Audit Event Schema

```json
{
  "audit_event_id": "audit_123",
  "occurred_at": "2026-07-13T10:04:00+09:00",
  "request_id": "req_123",
  "execution_context_id": "exec_123",
  "chat_session_id": "chat_123",
  "agent_thread_id": "thread_123",
  "user_id": "user_001",
  "actor_type": "agent_service",
  "operation": "external_transfer_execute",
  "contract_id": "API-EXTERNAL-TRANSFER-EXECUTE",
  "confirmation_id": "confirm_123",
  "auth_context_id": "auth_123",
  "transaction_id": "txn_123",
  "idempotency_key": "external_transfer_execute:confirm_123:1",
  "outcome": "completed",
  "reason": null,
  "policy_codes": []
}
```

Backend 금융 감사 로그에는 최소한 다음을 기록한다.

- `request_id`
- `execution_context_id`
- `chat_session_id`, `agent_thread_id`
- 인증된 `user_id`와 `actor_type`
- Operation, `contract_id`와 대상 리소스 참조 ID
- `confirmation_id`, `auth_context_id`
- `Idempotency-Key`
- 정책 판정과 업무 `outcome`
- 실행 전 검증 결과
- 금융 실행 결과와 `transaction_id`
- 실패·차단 사유 코드
- `occurred_at`

### 25.2 주요 Event Type

```text
financial_data_accessed
confirmation_created
confirmation_approved
confirmation_invalidated
confirmation_cancelled
auth_context_created
authentication_verified
authentication_failed
financial_execution_completed
financial_execution_blocked
setting_change_completed
idempotency_conflict
```

조회 API도 민감한 금융정보 접근이므로 사용자, 조회 유형, 대상 계좌 수, 성공·거부 여부와 요청 시각을 기록한다. 잔액과 거래내역 원문은 기록하지 않는다.

### 25.3 민감정보 제외

다음 값은 로그에 원문으로 기록하지 않는다.

- 전체 계좌번호
- 잔액과 거래내역 원문
- Frontend Access Token
- Agent 서비스 Token
- PIN과 생체인증 Assertion
- 비밀번호

계좌와 수취인 식별이 필요하면 내부 참조 ID 또는 마스킹된 값만 사용한다.

```text
account_id
recipient_id
to_recipient_candidate_id
masked_account_number
```

### 25.4 실행 일관성

Backend는 Execute 결과와 Financial Audit 사이에 불일치나 이벤트 유실이 발생하지 않도록 보장해야 한다. 구체적인 DB Transaction, Outbox, Message Broker와 저장 구조는 Backend 팀이 결정한다.

```text
Agent 팀이 요구하는 외부 보장
- 완료된 금융 실행은 대응 Audit Event를 가짐
- 실패하거나 차단된 요청도 사유를 추적할 수 있음
- 동일 멱등성 요청이 중복 Audit 사실을 만들지 않음
- API 성공 응답과 실제 금융 처리 결과가 일치함
```

Audit Log는 append-only로 관리하고 일반 업무 API에서 수정·삭제하지 않는다. Agent Webhook의 `status`, `tool_call`과 `done` 이벤트는 실행 관찰 정보일 뿐 금융 처리 사실의 정본으로 사용하지 않는다.

Agent의 Workflow Step Log는 금융 감사 로그의 정본을 대신하지 않는다. 기존 `write_audit_log`는 Agent Workflow, `tools.yaml`과 Tool Registry에서 제거하고 각 Backend 금융 API가 내부적으로 Audit Event를 생성한다.

---

## 26. Backend에 요청할 제공 계약

이 문서는 Backend의 파일 구조, Router 분리 방식, Service·Repository 계층, DB Schema, Message Broker와 배포 구조를 규정하지 않는다. Agent 팀은 Workflow를 구현하는 데 필요한 외부 계약과 보장만 Backend 팀에 요청한다.

### 26.1 Agent 팀이 전달할 내용

- Agent가 호출할 Method와 Path
- Agent 서비스 인증과 Execution Context Header
- 요청·응답 필드와 Enum
- Workflow별 호출 시점과 `contract_id`
- `outcome`에 따른 Agent Route
- 멱등성 재호출 규칙
- 전체 계좌번호와 인증 원문을 Agent에 반환하지 않는 보안 요구
- Frontend 입력·승인·인증을 Backend가 검증한 후 Agent를 재개하는 계약
- 금융 처리와 Audit 결과의 일관성 요구

### 26.2 Backend 팀이 결정할 내용

- API Router와 파일 분리 방식
- Service, Repository와 Domain 계층 구조
- Confirmation, Auth Context와 멱등성 저장 Schema
- DB Transaction과 동시성 제어 방식
- Audit Log 저장, Outbox와 Message Broker 사용 여부
- Redis, Queue와 SSE 내부 연동 방식
- 재시도, Timeout과 장애 복구의 내부 구현
- 운영 배포와 모니터링 구조

### 26.3 통신 방향별 필요 기능

| 통신 방향 | Agent 팀이 필요로 하는 기능 |
| --- | --- |
| Agent → Backend Webhook | 상태, UI와 완료 이벤트 수신 |
| Agent → Backend Tool API | 이 문서의 14개 금융 조회·Prepare·Execute 계약 제공 |
| Frontend → Backend | 일반 입력, 승인, 인증과 신규 수취 계좌 검증 |
| Backend → Agent | 검증된 사용자 결과로 중단된 Workflow 재개 |

Backend가 위 기능을 하나의 Router에 구현할지 여러 모듈로 나눌지는 Backend 팀의 책임이다. Agent 팀은 `POST /internal/v1/executions/{agent_thread_id}/resume`의 수신 계약을 제공하고 Backend가 승인·인증·입력 검증 후 이를 호출해 줄 것을 요청한다.

---

## 27. Workflow와 API 매핑

이 절은 관리시트 재작성에 사용할 초기 매핑안이다. 표의 `workflow_id`와 `step_id`는 Backend API 계약의 일부가 아니며, 최종 이름과 연결 관계는 Google 스프레드시트의 Workflow Step·계약 매핑 탭에서 확정한다. 관리시트가 확정된 뒤에는 이 표를 관리시트와 동기화된 요약으로 유지한다.

정본은 다음과 같이 분리한다.

| 대상 | 정본 |
| --- | --- |
| `contract_id`, HTTP Method·Path, 요청·응답 필드 | 이 API 명세서 |
| `workflow_id`, `step_id`, Step 실행 순서와 `contract_id` 연결 | Google 스프레드시트 관리시트 |
| Webhook UI Payload와 사용자 회신 Schema | UI·HITL 계약서 |

### 27.1 Agent Tool API 호출 Step

| workflow_id | step_id | contract_id | Method·Path |
| --- | --- | --- | --- |
| `wf_account_list` | `fetch_account_list` | `API-ACCOUNT-LIST` | `GET /accounts` |
| `wf_balance_inquiry` | `resolve_balance_accounts` | `API-ACCOUNT-LIST` | `GET /accounts` |
| `wf_balance_inquiry` | `query_balances` | `API-BALANCE-QUERY` | `POST /accounts/balances:query` |
| `wf_transaction_history` | `resolve_transaction_accounts` | `API-ACCOUNT-LIST` | `GET /accounts` |
| `wf_transaction_history` | `query_transactions` | `API-TRANSACTION-QUERY` | `POST /transactions:query` |
| `wf_period_amount_summary` | `resolve_summary_accounts` | `API-ACCOUNT-LIST` | `GET /accounts` |
| `wf_period_amount_summary` | `query_transaction_summary` | `API-TRANSACTION-SUMMARY` | `POST /transactions:summary` |
| `wf_set_default_account` | `resolve_default_account` | `API-ACCOUNT-LIST` | `GET /accounts` |
| `wf_set_default_account` | `prepare_default_account_change` | `API-DEFAULT-ACCOUNT-PREPARE` | `POST /settings/default-account:prepare` |
| `wf_set_default_account` | `execute_default_account_change` | `API-DEFAULT-ACCOUNT-EXECUTE` | `POST /settings/default-account` |
| `wf_set_account_alias` | `resolve_account_alias_target` | `API-ACCOUNT-LIST` | `GET /accounts` |
| `wf_set_account_alias` | `prepare_account_alias_change` | `API-ACCOUNT-ALIAS-PREPARE` | `POST /settings/account-alias:prepare` |
| `wf_set_account_alias` | `execute_account_alias_change` | `API-ACCOUNT-ALIAS-EXECUTE` | `POST /settings/account-alias` |
| `wf_internal_transfer` | `resolve_internal_from_account` | `API-ACCOUNT-LIST` | `GET /accounts` |
| `wf_internal_transfer` | `resolve_internal_to_account` | `API-ACCOUNT-LIST` | `GET /accounts` |
| `wf_internal_transfer` | `prepare_internal_transfer` | `API-INTERNAL-TRANSFER-PREPARE` | `POST /transfers/internal:prepare` |
| `wf_internal_transfer` | `create_internal_auth_context` | `API-AUTH-CONTEXT-CREATE` | `POST /auth-contexts` |
| `wf_internal_transfer` | `execute_internal_transfer` | `API-INTERNAL-TRANSFER-EXECUTE` | `POST /transfers/internal` |
| `wf_external_transfer` | `resolve_recipient_hint` | `API-RECIPIENT-RESOLVE` | `POST /recipients:resolve` |
| `wf_external_transfer` | `resolve_external_from_account` | `API-ACCOUNT-LIST` | `GET /accounts` |
| `wf_external_transfer` | `prepare_external_transfer` | `API-EXTERNAL-TRANSFER-PREPARE` | `POST /transfers/external:prepare` |
| `wf_external_transfer` | `create_external_auth_context` | `API-AUTH-CONTEXT-CREATE` | `POST /auth-contexts` |
| `wf_external_transfer` | `execute_external_transfer` | `API-EXTERNAL-TRANSFER-EXECUTE` | `POST /transfers/external` |

표의 Path에는 공통 Prefix `/api/v1/agent-tools`가 생략되어 있다. `contract_id`는 이 문서의 API 계약을 참조한다. 관리시트에서는 요청·응답 필드를 중복 정의하지 않고 `contract_id`로 연결하며, 표의 Step ID는 관리시트 재작성 과정에서 변경될 수 있다.

### 27.2 Webhook·HITL Step

다음 Step은 Agent Tool API를 호출하지 않는다. Agent가 UI 요청 Webhook을 보낸 뒤 Backend가 Frontend 제출값을 검증하고 중단된 Agent Workflow를 재개한다. 각 Step은 관리시트에서 API `contract_id`가 아니라 UI·HITL 계약 ID에 연결한다.

| workflow_id | 입력·승인·인증 대기 Step | 결과·안내 Webhook Step |
| --- | --- | --- |
| `wf_account_list` | 없음 | `emit_account_list_result`, `emit_account_list_error` |
| `wf_balance_inquiry` | `request_balance_account_selection` | `emit_balance_result`, `emit_balance_accounts_empty`, `emit_balance_error` |
| `wf_transaction_history` | `request_transaction_account_selection`, `request_period_selection` | `emit_transaction_accounts_empty`, `emit_transaction_result`, `emit_transaction_error` |
| `wf_period_amount_summary` | `request_period_selection`, `request_summary_account_selection`, `request_summary_type` | `emit_summary_accounts_empty`, `emit_amount_summary`, `emit_amount_summary_error` |
| `wf_set_default_account` | `request_default_account_selection`, `request_default_account_approval` | `emit_default_account_selection_empty`, `emit_default_account_unchanged`, `emit_default_account_result`, `emit_default_account_blocked`, `emit_default_account_error` |
| `wf_set_account_alias` | `request_account_alias_selection`, `request_account_alias_input`, `request_account_alias_approval` | `emit_account_alias_selection_empty`, `emit_account_alias_unchanged`, `emit_account_alias_result`, `emit_account_alias_blocked`, `emit_account_alias_error` |
| `wf_internal_transfer` | `request_from_account_selection`, `request_to_account_selection`, `request_internal_transfer_amount`, `request_internal_transfer_approval`, `request_internal_transfer_correction`, `request_internal_authentication`, `request_internal_auth_retry` | `emit_internal_from_accounts_empty`, `emit_internal_to_accounts_empty`, `emit_internal_transfer_result`, `emit_internal_transfer_blocked`, `emit_internal_transfer_error` |
| `wf_external_transfer` | `request_recipient_selection`, `request_external_from_account_selection`, `request_external_transfer_amount`, `request_external_transfer_approval`, `request_external_transfer_correction`, `request_external_authentication`, `request_external_auth_retry` | `emit_external_from_accounts_empty`, `emit_external_transfer_result`, `emit_external_transfer_blocked`, `emit_external_transfer_error` |

일반 입력 대기 Step은 `input_request_id`, 승인 대기 Step은 `confirmation_id`, 인증 대기 Step은 `auth_context_id`로 재개 결과를 연결한다. 세 유형 모두 Webhook 전송 후 Workflow를 중단하지만 서로의 식별자를 대신 사용하지 않는다. 결과·안내용 `emit_*` Step은 사용자 회신을 기다리지 않는다. 단일 기존 거래 수취인이 자동 확정된 경우에는 별도 수취인 확인 Step을 만들지 않고 최종 송금 승인 화면에서 출금 계좌·수취인·금액을 함께 확인한다.

본인송금의 추가 인증이 `failed` 또는 `expired`이면 `request_internal_auth_retry`가 `auth_retry_outcome=retry|cancelled`를 입력받는다. `retry`이면 새 Auth Context를 생성하고, 재인증 선택 또는 최초 인증 화면에서 `cancelled`이면 추가 취소 Webhook 없이 Workflow를 종료한다.

`request_account_alias_input`은 Backend가 별칭 형식과 정책을 검증한 경우에만 `alias_input_outcome=submitted`와 정규화된 `alias`로 Agent를 재개한다. 검증 실패는 Agent를 재개하지 않고 같은 UI에서 처리하며, 사용자가 취소하면 `alias_input_outcome=cancelled`, `alias=null`로 재개한다.

`request_internal_transfer_amount`와 `request_external_transfer_amount`는 Backend가 금액 형식을 검증한 경우에만 `amount_input_outcome=submitted`와 정규화된 `amount`로 Agent를 재개한다. 형식 검증 실패는 Agent를 재개하지 않고 같은 UI에서 처리하며, 사용자가 취소하면 `amount_input_outcome=cancelled`, `amount=null`로 재개한다.

### 27.3 기존 Workflow에서 제거하거나 흡수할 Step

| 기존 Step | 반영 방식 |
| --- | --- |
| `check_balance` | Agent 내부 검사를 제거하고 Prepare와 Execute의 Backend 검증으로 흡수 |
| `run_transfer_guardrail` | `prepare_external_transfer`의 Backend 업무 판단으로 흡수 |
| `run_pre_execution_guardrail` | 각 Execute API의 실행 직전 Backend 검증으로 흡수 |
| `verify_recipient_account` | Frontend 입력을 받은 Backend의 신규 수취 계좌 검증으로 이동 |
| `write_audit_log` | Agent Workflow와 Tool 목록에서 제거하고 Backend 금융 Audit 책임으로 전환 |

---

## 28. 스프레드시트 중 현재 범위 외 API

기존 스프레드시트 `API Spec` 탭에는 아래 기능도 포함되어 있었다. 현재 `workflows.yaml`에 대응 Workflow가 없고 이번 Agent·Backend 연동 범위에도 포함되지 않으므로 본 문서의 계약 ID를 부여하지 않는다.

| 기존 Tool | 현재 판단 |
| --- | --- |
| `deposit_money` | 대응 Workflow가 없어 이번 계약 범위에서 제외 |
| `withdraw_money` | 대응 Workflow가 없어 이번 계약 범위에서 제외 |
| `create_auto_savings_rule` | 대응 Workflow가 없어 이번 계약 범위에서 제외 |
| `write_audit_log` | 보류 기능이 아니라 Agent Tool과 Workflow에서 제거 |

입금, 출금 또는 자동저축 Workflow를 향후 추가할 때는 기존 Endpoint와 필드명을 그대로 승계하지 않는다. Workflow State, 위험등급, 승인·인증 필요 여부와 Backend 제공 가능 범위를 다시 검토한 뒤 새 `contract_id`와 요청·응답 계약을 확정한다.

`write_audit_log`는 향후 구현할 Agent API 후보가 아니다. Agent는 실행 추적 로그만 관리하고 금융 감사의 정본은 각 Backend 금융 API 처리 과정에서 생성한다.

---

## 29. 부록: Frontend·Backend 처리와 Agent 재개 경계

이 절은 Frontend API의 Path와 요청 Body를 정의하지 않는다. Frontend가 어떤 Endpoint와 인증 방식을 사용할지는 Backend·Frontend 통신 계약에서 정한다. 이 문서에서는 사용자 입력·승인·인증이 Backend에서 검증된 뒤 Agent가 어떤 값으로 재개되어야 하는지만 정의한다.

### 29.1 최근 수취인 표시

`recipient_select`의 초기 목록은 Backend와 Frontend가 구성한다. 현재 사용자의 완료된 타인송금 거래를 기준으로 동일 수취인을 중복 제거하고 계좌번호를 마스킹해야 한다.

Agent는 최근 수취인 목록을 조회하거나 Workflow State에 저장하지 않는다. Agent는 수취인 정보가 없거나 기존 거래에서 하나로 확정되지 않을 때 `UI-RECIPIENT-SELECT` Webhook만 전송한다.

### 29.2 신규 수취 계좌 검증

Frontend에서 입력한 은행 코드와 전체 계좌번호는 Backend가 검증한다. Backend는 검증에 성공한 신규 계좌에 `to_recipient_candidate_id`로 사용할 수 있는 참조 ID를 발급한다.

Backend가 Agent를 재개할 때는 다음 중 하나의 검증된 참조만 전달한다.

```text
to_recipient_id
to_recipient_candidate_id
```

전체 계좌번호, 은행 코드와 예금주 검증 원문은 Agent 재개 Payload와 Workflow State에 포함하지 않는다. 검증에 실패하면 Agent를 재개하지 않고 Backend와 Frontend가 같은 입력 화면에서 오류를 표시하고 재입력받는다.

### 29.3 일반 입력 검증과 재개

Backend는 일반 입력을 Agent에 전달하기 전에 다음을 검증한다.

1. 인증된 사용자와 Chat Session 소유권
2. `input_request_id`가 현재 대기 중인 요청인지
3. 대기 요청에 연결된 `ui_contract_id`와 제출값 Schema
4. 계좌·수취인처럼 참조 ID가 현재 사용자에게 허용되는지
5. 입력 요청이 이미 소비되거나 만료되지 않았는지

검증이 끝난 재개 값에는 `input_request_id`와 해당 UI 계약이 정의한 `value`만 포함한다. `prompt_for`는 사용하지 않는다.

수취인 선택 재개 값 예시는 다음과 같다.

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

신규 수취 계좌 선택은 다음처럼 전달한다.

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

잔액 조회 계좌 선택 완료는 다음처럼 전달한다.

```json
{
  "input_request_id": "input_balance_account_123",
  "value": {
    "account_selection_outcome": "selected",
    "account_ids": [
      "acc_001"
    ]
  }
}
```

사용자가 계좌 선택을 취소한 경우에는 다음처럼 전달한다.

```json
{
  "input_request_id": "input_balance_account_123",
  "value": {
    "account_selection_outcome": "cancelled",
    "account_ids": []
  }
}
```

Backend는 `selected`일 때만 계좌 소유권, 상태와 조회 권한을 검증하여 `account_ids`를 전달한다. Agent는 `cancelled`를 받으면 추가 Tool API와 UI Webhook을 호출하지 않고 Workflow를 종료한다.

기간 선택 UI의 프리셋과 직접 입력 날짜는 Backend가 Execution Context의 `timezone`, 날짜 순서와 최대 조회 기간을 기준으로 정규화·검증한다. Agent에는 프리셋 원문이 아니라 다음 값을 전달한다.

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

사용자가 기간 선택을 취소하면 다음처럼 전달한다.

```json
{
  "input_request_id": "input_period_123",
  "value": {
    "period_selection_outcome": "cancelled",
    "start_date": null,
    "end_date": null
  }
}
```

기간 선택 처리로 새로운 Agent Tool API를 추가하지 않는다. `selected`이면 Agent가 기존 `API-TRANSACTION-QUERY` 또는 `API-TRANSACTION-SUMMARY`를 호출하고, `cancelled`이면 Workflow를 종료한다.

합계 유형이 사용자 발화에서 명확하지 않으면 Agent는 `option_select`로 `spending`, `income` 중 하나를 요청한다. Backend는 일반 입력 API에서 `input_request_id`와 Enum을 검증한 뒤 다음처럼 Agent를 재개한다.

```json
{
  "input_request_id": "input_summary_type_123",
  "value": {
    "summary_type_selection_outcome": "selected",
    "summary_type": "spending"
  }
}
```

사용자가 취소하면 `summary_type_selection_outcome=cancelled`, `summary_type=null`로 재개한다. 이 입력 처리로 새로운 Agent Tool API를 추가하지 않으며 `selected`일 때만 기존 `API-TRANSACTION-SUMMARY`를 호출한다.

Agent는 Backend가 검증한 값을 해당 Workflow State에 저장하고 같은 입력을 다시 요청하지 않는다.

### 29.4 사용자 승인 검증과 재개

Backend는 `confirmation_id`, 사용자, Chat Session, 승인 대기 상태와 만료를 검증하고 승인 결과를 저장한 뒤 Agent를 재개한다. Agent에 필요한 재개 필드는 다음과 같다.

| 필드 | 조건 | 설명 |
| --- | --- | --- |
| `confirmation_id` | 필수 | 현재 대기 중인 Confirmation 식별자 |
| `approval_outcome` | 필수 | `approved`, `change_requested`, `cancelled` 중 하나 |
| `change_target` | `change_requested`일 때 필수 | Backend가 허용한 수정 대상. 수정 대상이 하나로 고정된 Workflow는 생략 가능 |

`change_requested`와 `cancelled`이면 Backend가 기존 Confirmation을 다시 실행할 수 없게 처리한 후 Agent를 재개한다. Agent는 Confirmation 상태를 조회하거나 승인 결과를 다시 등록하지 않는다. `cancelled`는 중단된 Workflow 상태를 정리하기 위한 재개 결과이며 Agent는 별도 취소 Webhook을 다시 보내지 않고 종료할 수 있다.

### 29.5 추가 인증 검증과 재개

Backend는 `auth_context_id`, 사용자, Confirmation, 인증 상태와 만료를 검증하고 결과를 저장한 뒤 Agent를 재개한다. Agent에 필요한 재개 필드는 다음과 같다.

| 필드 | 필수 | 설명 |
| --- | --- | --- |
| `auth_context_id` | 필수 | 현재 대기 중인 Auth Context 식별자 |
| `auth_status` | 필수 | `verified`, `failed`, `cancelled`, `expired` 중 하나 |

Agent는 `verified`인 경우에만 Execute로 이동한다. 실패·취소·만료이면 해당 Workflow Route에 따라 재인증 또는 종료 안내를 수행한다. PIN, 생체인증 Assertion, Access Token과 인증 원문은 Agent 재개 Payload에 포함하지 않는다. Agent는 인증 상태 조회 API를 폴링하거나 인증 결과를 다시 검증하지 않는다.

---

## 30. 공동 계약 검증 항목

이 절은 각 팀의 내부 테스트 도구, 코드 구조와 자동화 방식을 지정하지 않는다. Agent·Backend 통합 시 이 문서의 외부 계약이 동일하게 해석되고 동작하는지를 확인하기 위한 공통 체크리스트다.

### 30.1 Agent 구간

- Agent가 14개 API에 명세된 Header와 업무 필드만 전달한다.
- Agent Tool 요청 Body에 `user_id`와 전체 계좌번호를 포함하지 않는다.
- `success=true`이면 `data.outcome`, `success=false`이면 `error.category`와 `error.code`로 Route를 결정한다.
- 동일한 상태 변경 요청을 재시도할 때 같은 `Idempotency-Key`와 Body를 사용한다.
- Backend가 검증하여 재개한 입력·승인·인증 결과를 같은 목적으로 다시 요청하지 않는다.
- 타인송금과 본인송금은 승인과 추가 인증을 모두 완료한 뒤 Execute를 호출한다.

### 30.2 Backend 제공 계약 구간

- Execution Context를 기준으로 사용자와 리소스 접근 범위를 검증한다.
- 다른 사용자의 계좌·수취인·Confirmation·Auth Context 접근을 거부한다.
- 업무 판단은 `success=true`와 `data.outcome`, 요청·인증·기술 오류는 `success=false`와 `error`로 구분한다.
- Prepare는 승인 대상 계좌·수취인·금액·통화를 Confirmation에 고정한다.
- 수정·취소·만료로 무효화된 Confirmation을 Execute에 사용할 수 없다.
- 송금 Execute는 승인된 Confirmation과 검증된 Auth Context를 모두 요구하고 현재 잔액·한도·정책을 다시 확인한다.
- 같은 멱등성 키와 같은 Body에는 최초 결과를 반환하고, 다른 Body에는 `IDEMPOTENCY_KEY_CONFLICT`를 반환한다.
- 금융 실행과 Financial Audit 결과의 일관성을 외부적으로 확인할 수 있다.

### 30.3 Frontend·HITL 통합 구간

- Backend가 사용자, Chat Session과 현재 대기 요청을 검증한 뒤 Agent를 재개한다.
- 일반 입력은 `input_request_id`, 승인은 `confirmation_id`, 인증은 `auth_context_id`로 대기 상태와 연결된다.
- 신규 계좌 원문은 Backend에서 검증하고 Agent에는 `to_recipient_candidate_id`만 전달한다.
- 입력 검증 실패 시 Agent를 재개하지 않고 동일 UI에서 재입력받는다.
- 승인·수정·취소와 인증 성공·실패·취소·만료가 각각 정해진 Agent Route로 연결된다.
- 서비스 Token, 전체 계좌번호와 인증 원문이 Frontend 이벤트, Agent State와 일반 로그에 노출되지 않는다.

---

## 31. 계약 버전 확정 기준

### 31.1 `0.9.0` Backend 검토 요청안

현재 문서는 구현 확정 요청이 아니라 다음 항목의 제공 가능 여부와 계약 적합성을 검토하는 단계다.

- 14개 Agent Tool API의 범위
- Method, Path, Header와 요청·응답 필드
- 업무 `outcome`, 사유 코드와 오류 구분
- Confirmation과 Auth Context 생명주기
- 멱등성 재호출과 결과 복원 보장
- Backend에서 검증한 입력·승인·인증 결과로 Agent를 재개하는 경계
- 금융 실행과 Backend Financial Audit의 일관성 보장

Workflow Step ID와 실행 순서는 이 버전의 Backend API 계약에 포함하지 않는다. 27장의 Step 이름은 관리시트 재작성에 사용할 초기 매핑안이다.

### 31.2 `1.0.0` 계약 확정

다음 조건이 충족되면 검토 결과를 반영하고 계약 버전을 `1.0.0`으로 변경한다.

- Agent·Backend·Frontend 담당자가 각 통신 방향과 책임 경계에 합의한다.
- 14개 API의 요청·응답 필드, Enum과 상태 전이가 확정된다.
- `success`, `outcome`, 업무 사유 코드와 오류 코드의 구분이 확정된다.
- `input_request_id`, `confirmation_id`, `auth_context_id`의 연결과 재개 필드가 확정된다.
- 관리시트의 Workflow Step·계약 매핑이 재작성되고 이 문서의 `contract_id`와 일치한다.

각 팀의 내부 구현 완료 기준, 테스트 도구와 개발 일정은 이 API 명세가 아니라 해당 팀의 구현 계획에서 관리한다.
