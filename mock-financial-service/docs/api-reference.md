# API Reference — 정보계 (Analytics) Endpoints

정보계(downstream analytics) 전용 REST API. 읽기 전용.

> **계정계 기존 5개 엔드포인트** (`POST /accounts`, `GET /accounts/{id}`, etc.) 는 이 문서 범위 밖.
> 기존 엔드포인트에 인증 없음 — 별도 작업 범위.

---

## 인증

정보계 엔드포인트는 전용 API 키 인증 필요.

```
X-Analytics-Key: <key>
```

키 없거나 잘못된 경우:
```json
HTTP 401
{"error_code": "UNAUTHORIZED", "message": "Valid X-Analytics-Key required"}
```

키는 환경변수 `ANALYTICS_API_KEY` 로 설정 (`analytics_router.py`에서 `os.environ.get("ANALYTICS_API_KEY", "analytics-demo-key")`) — 설정 안 하면 로컬/데모용 기본값 `analytics-demo-key` 사용. 공유 환경/프로덕션에서는 반드시 환경변수로 오버라이드(또는 시크릿 매니저 연동)할 것.

---

## 엔드포인트 목록

| Method | Path | 설명 | 인증 |
|--------|------|------|------|
| GET | `/api/v1/analytics/accounts/{id}/balance` | 계좌 잔액 조회 (canonical, 계정계와 동일 값) | ✅ 필요 |
| GET | `/api/v1/analytics/accounts/{id}/ledger` | 원장 항목 목록 | ✅ 필요 |
| GET | `/api/v1/analytics/accounts/{id}/reconcile` | 저장된 잔액 vs 원장 재계산 정합성 검증 | ✅ 필요 |
| GET | `/api/v1/analytics/accounts/{id}/audit-logs` | 계좌 관련 감사로그 조회 | ✅ 필요 |

---

## 1. GET `/api/v1/analytics/accounts/{id}/balance`

`get_balance()` 재사용 — 계정계의 `GET /accounts/{id}/balance` 와 동일한 읽기 경로(저장된 `Account.balance` 컬럼을 그대로 반환), X-Analytics-Key로만 보호. 응답 스키마도 동일(`BalanceResponse`).

### Request

```
GET /api/v1/analytics/accounts/{account_id}/balance
X-Analytics-Key: <key>
```

### Response 200

```json
{
  "account_id": "550e8400-e29b-41d4-a716-446655440000",
  "balance": 150000,
  "currency": "KRW"
}
```

### Response Fields

| 필드 | 타입 | 설명 |
|------|------|------|
| `account_id` | string | 계좌 UUID |
| `balance` | integer | `Account.balance` 저장 컬럼값 그대로 (원장 기록과 같은 트랜잭션에서 갱신되는 canonical balance) |
| `currency` | string | 통화 코드 (KRW) |

### Response 404

```json
{"error_code": "ACCOUNT_NOT_FOUND", "message": "Account {id} not found"}
```

---

## 2. GET `/api/v1/analytics/accounts/{id}/ledger`

계좌의 원장 항목 목록 (페이지네이션 지원).

### Request

```
GET /api/v1/analytics/accounts/{account_id}/ledger?limit=50&offset=0
X-Analytics-Key: <key>
```

### Query Parameters

| 파라미터 | 타입 | 기본값 | 범위 | 설명 |
|----------|------|--------|------|------|
| `limit` | integer | 50 | 1–200 | 반환할 최대 항목 수 |
| `offset` | integer | 0 | ≥ 0 | 건너뛸 항목 수 |

### Response 200

```json
[
  {
    "entry_id": "a1b2c3d4-...",
    "transaction_id": "f0e1d2c3-...",
    "account_id": "550e8400-...",
    "entry_type": "CREDIT",
    "amount": 100000,
    "running_balance": 100000,
    "created_at": "2026-07-01T09:05:00Z"
  },
  {
    "entry_id": "b2c3d4e5-...",
    "transaction_id": "e1f0d2c3-...",
    "account_id": "550e8400-...",
    "entry_type": "DEBIT",
    "amount": 30000,
    "running_balance": 70000,
    "created_at": "2026-07-02T14:20:00Z"
  }
]
```

### Response Fields (per item)

| 필드 | 타입 | 설명 |
|------|------|------|
| `entry_id` | string | 원장 항목 UUID |
| `transaction_id` | string | 연결된 트랜잭션 UUID |
| `account_id` | string | 계좌 UUID |
| `entry_type` | string | `CREDIT` (입금) 또는 `DEBIT` (출금) |
| `amount` | integer | 항목 금액 (항상 양수) |
| `running_balance` | integer | 이 항목 기록 시점의 잔액 스냅샷 |
| `created_at` | datetime | 기록 시각 (UTC ISO8601) |

정렬: `created_at` 내림차순 (최신 먼저).

---

## 3. GET `/api/v1/analytics/accounts/{id}/reconcile`

저장된 `Account.balance`(canonical) vs 원장 전체 재집계 정합성 검증 실행 (DB 쓰기 없음, 잠금 없음).

### Request

```
GET /api/v1/analytics/accounts/{account_id}/reconcile
X-Analytics-Key: <key>
```

### 동작

1. `Account.balance` 저장값 조회 (`cached_balance`).
2. `ledger_entries` 전체를 다시 SUM(CREDIT)-SUM(DEBIT) 재계산 (`expected_balance`) — 워터마크나 시점 제한 없이 항상 전체 재집계.
3. `cached_balance` vs `expected_balance` 비교 → `delta`, `drift_detected`.
4. 결과 반환 — 자동 수정 없음, 탐지+응답만.

`Account.balance`는 `transfer()`/`settle_card()`/계좌 생성(초기입금) 등 원장에 쓰는 모든 경로에서 같은 DB 트랜잭션 안에서 갱신되므로, 정상 흐름이라면 이 두 값은 항상 일치한다. "아직 새로고침 안 됨"으로 인한 stale 상태는 존재하지 않음 — `drift_detected=true`는 곧 버그를 의미한다.

### Response 200 — 정상 (drift 없음)

```json
{
  "account_id": "550e8400-e29b-41d4-a716-446655440000",
  "cached_balance": 150000,
  "expected_balance": 150000,
  "sum_credit": 200000,
  "sum_debit": 50000,
  "drift_detected": false,
  "delta": 0,
  "reconciled_at": "2026-07-07T10:40:00Z"
}
```

### Response 200 — drift 감지 (버그 신호)

```json
{
  "account_id": "550e8400-e29b-41d4-a716-446655440000",
  "cached_balance": 150000,
  "expected_balance": 145000,
  "sum_credit": 200000,
  "sum_debit": 50000,
  "drift_detected": true,
  "delta": 5000,
  "reconciled_at": "2026-07-07T10:40:00Z"
}
```

### Response Fields (`ReconciliationResponse`)

| 필드 | 타입 | 설명 |
|------|------|------|
| `account_id` | string | 계좌 UUID |
| `cached_balance` | integer | `Account.balance` 저장값 |
| `expected_balance` | integer | 원장 전체 재집계값 (`sum_credit - sum_debit`) |
| `sum_credit` | integer | 원장 전체 CREDIT 합계 |
| `sum_debit` | integer | 원장 전체 DEBIT 합계 |
| `drift_detected` | boolean | `cached_balance ≠ expected_balance` 이면 `true` |
| `delta` | integer | `cached_balance - expected_balance` |
| `reconciled_at` | string | 검증 실행 시각 (UTC ISO8601) |

### Response 404

```json
{"error_code": "ACCOUNT_NOT_FOUND", "message": "Account {id} not found"}
```

---

## 4. GET `/api/v1/analytics/accounts/{id}/audit-logs`

계좌와 연관된 감사로그 목록 (페이지네이션 지원). `audit_logs` 는 DB 트리거로 UPDATE/DELETE 거부 — 이 엔드포인트는 읽기 전용, 이 경로로도 쓰기 불가.

### Request

```
GET /api/v1/analytics/accounts/{account_id}/audit-logs?limit=50&offset=0
X-Analytics-Key: <key>
```

### 연결 방식

`audit_logs.transaction_id` 를 통해 `transactions.sender_account_id`/`receiver_account_id` 가 해당 계좌인 로그만 조회. `ACCOUNT_CREATE` 는 초기 입금(`initial_balance > 0`)이 있는 계좌만 seed transaction과 연결되어 조회됨 — 초기 잔액 0으로 생성된 계좌는 연결된 transaction이 없어 `ACCOUNT_CREATE` 로그가 이 경로로 안 보임(알려진 제약).

### Response 200

```json
[
  {
    "audit_log_id": "a1b2c3d4-...",
    "transaction_id": "f0e1d2c3-...",
    "actor": "홍길동",
    "action": "ACCOUNT_CREATE",
    "reason": "New account created for 홍길동",
    "status": "success",
    "timestamp": "2026-07-01T09:00:00Z"
  },
  {
    "audit_log_id": "b2c3d4e5-...",
    "transaction_id": "e1f0d2c3-...",
    "actor": "550e8400-e29b-41d4-a716-446655440000",
    "action": "TRANSFER",
    "reason": "Transfer completed",
    "status": "success",
    "timestamp": "2026-07-02T14:20:00Z"
  }
]
```

### Response Fields (per item)

| 필드 | 타입 | 설명 |
|------|------|------|
| `audit_log_id` | string | 감사로그 UUID |
| `transaction_id` | string \| null | 연결된 트랜잭션 UUID (없으면 null) |
| `actor` | string | 행위자 — 계좌생성 시 owner 명, 송금 시 sender account_id |
| `action` | string | `ACCOUNT_CREATE` \| `TRANSFER` \| `TRANSFER_FAILED` |
| `reason` | string | 사람이 읽을 수 있는 설명 |
| `status` | string | `success` \| `failure` |
| `timestamp` | datetime | 기록 시각 (UTC ISO8601) |

정렬: `timestamp` 내림차순.

### Response 404

```json
{"error_code": "ACCOUNT_NOT_FOUND", "message": "Account {id} not found"}
```

---

## 에러 코드 전체 목록

| error_code | HTTP | 발생 상황 |
|------------|------|-----------|
| `UNAUTHORIZED` | 401 | X-Analytics-Key 없음 또는 불일치 |
| `ACCOUNT_NOT_FOUND` | 404 | 존재하지 않는 계좌 ID |
| `VALIDATION_ERROR` | 422 | 입력 파라미터 오류 |

---

## 계정계 기존 5개 엔드포인트 (참고)

이 엔드포인트들은 인증 없음. 계정계 owner-side API.

| Method | Path | 설명 |
|--------|------|------|
| POST | `/api/v1/accounts` | 계좌 생성 (201) |
| GET | `/api/v1/accounts/{id}` | 계좌 조회 (200/404) |
| GET | `/api/v1/accounts/{id}/balance` | 저장된 잔액 조회 (200/404) |
| GET | `/api/v1/accounts/{id}/transactions` | 원장 이력 조회 (200/404) |
| POST | `/api/v1/transfers` | 송금 (200, Idempotency-Key 필수) |

계정계 잔액 (`GET /accounts/{id}/balance`) 과 정보계 잔액 (`GET /analytics/accounts/{id}/balance`) 은 동일한 저장 컬럼(`Account.balance`)을 읽으므로 같은 값을 반환해야 함.
