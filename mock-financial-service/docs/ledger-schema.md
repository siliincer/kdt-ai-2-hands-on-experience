# Ledger Schema — 설계 원칙 및 근거

## 1. 이중기입 원장 (Double-Entry Ledger)

### 원칙

원장 기록 없이 `balance` 컬럼만 단독으로 갱신하는 방식은 사용 안 함. 모든 잔액 변동은 `ledger_entries` 테이블에 차변(DEBIT)/대변(CREDIT) **쌍**으로 기록된다.

```
canonical_balance = SUM(amount WHERE entry_type='CREDIT')
                  - SUM(amount WHERE entry_type='DEBIT')
```

`accounts.balance` 컬럼은 이 계산 결과를 저장한 값이며, 원장 쓰기와 같은 DB 트랜잭션 안에서 항상 함께 갱신된다(§5 참고) — "원장 따로, balance 컬럼 따로"가 아니라 원장이 유일한 진실 소스이고 `balance`는 그 소스와 원자적으로 동기화된 저장값이다.

### 근거

| 문제 | 단일 balance 컬럼 | 이중기입 원장 |
|------|-------------------|---------------|
| 감사 추적 | 최종값만 존재, 이력 없음 | 모든 변동 entry로 재현 가능 |
| 동시성 | UPDATE balance 경쟁 조건 | INSERT-only, 잠금 범위 최소 |
| 무결성 검증 | 이력 재계산 불가 | SUM 재계산으로 언제든 검증 |
| 롤백 | 이전 값 알 수 없음 | 특정 시점 이전 항목만 SUM |

### 핵심 제약

- `ledger_entries.amount` 는 **항상 양수**. 방향은 `entry_type` 으로만 구분.
- 금액은 전부 `BigInteger` (KRW 원 단위 정수). Float 없음.
- `running_balance` 컬럼은 INSERT 시점 스냅샷 — 참고값이며 canonical balance 계산에 사용 안 함.

---

## 2. 원자적 송금 (Atomic Transfer)

단일 DB 트랜잭션 내에서 다음이 묶임:

```
BEGIN
  INSERT INTO transactions (...)
  INSERT INTO ledger_entries (entry_type='DEBIT',  account=sender,   ...)
  INSERT INTO ledger_entries (entry_type='CREDIT', account=receiver, ...)
  INSERT INTO audit_logs (action='TRANSFER', ...)
COMMIT
```

부분 성공 불가. 커밋 후 잔액 합계 보존 검증 실행 (`assert pre_total == post_total`).

---

## 3. 감사로그 불변성 (AuditLog Immutability)

`audit_logs` 테이블은 DB 레벨 트리거로 UPDATE/DELETE 차단.

### SQLite 트리거

```sql
CREATE TRIGGER IF NOT EXISTS audit_logs_no_update
BEFORE UPDATE ON audit_logs
BEGIN
    SELECT RAISE(ABORT, 'audit_logs is append-only: UPDATE forbidden');
END;

CREATE TRIGGER IF NOT EXISTS audit_logs_no_delete
BEFORE DELETE ON audit_logs
BEGIN
    SELECT RAISE(ABORT, 'audit_logs is append-only: DELETE forbidden');
END;
```

애플리케이션 계층 방어만으로는 불충분 — DB 레벨에서 강제해야 신뢰 가능.

---

## 4. Idempotency-Key 패턴

| 시나리오 | 처리 |
|----------|------|
| 동일 키 + 동일 payload | 기존 Transaction 반환 (safe replay) |
| 동일 키 + 다른 payload | 409 IDEMPOTENCY_CONFLICT |
| 키 없음 | 422 MISSING_IDEMPOTENCY_KEY |

`payload_hash` = SHA-256(`json.dumps(payload, sort_keys=True)`). `transactions.idempotency_key` 에 unique index.

---

## 5. 잔액 컬럼의 원자적 갱신 (Account.balance)

### 배경

과거 설계는 `accounts`에 balance 컬럼이 없었고, 정보계가 매 요청마다 원장 집계 쿼리를 실행하지 않도록 `balance_snapshots`라는 별도 캐시 테이블(계좌당 1행, 수동 새로고침, 고수위표 `last_entry_rowid`로 커버 범위 추적)을 뒀다. 이 캐시는 새로고침 시점 이후의 거래를 반영하지 못해 stale 가능성이 항상 존재했고, "지금 stale한 것"과 "계산 로직 자체가 틀린 것"을 구분하기 위해 정합성 검증도 고수위표 범위로 스코프를 좁혀야 했다.

### 현재 설계

`accounts` 테이블에 `balance` 컬럼(canonical, `BigInteger`)이 존재하며, 원장에 쓰는 모든 경로 — `transfer()`, `settle_card()`, `create_account()`의 초기입금 — 가 `LedgerEntry` INSERT와 **같은 DB 트랜잭션/커밋 안에서** `Account.balance`를 함께 갱신한다.

```
BEGIN
  INSERT INTO ledger_entries (entry_type='DEBIT',  account=sender,   ...)
  INSERT INTO ledger_entries (entry_type='CREDIT', account=receiver, ...)
  UPDATE accounts SET balance = balance - amount WHERE account_id = sender
  UPDATE accounts SET balance = balance + amount WHERE account_id = receiver
COMMIT
```

별도의 갱신/새로고침 단계가 없으므로 캐시 무효화 문제 자체가 발생하지 않는다 — "아직 새로고침 안 된 상태"라는 개념이 존재하지 않는다. `GET /accounts/{id}/balance`, `GET /analytics/accounts/{id}/balance` 둘 다 이 저장된 컬럼을 그대로 읽는다(`crud.get_balance()`, O(1)).

원장 전체를 SUM(CREDIT)-SUM(DEBIT)로 재계산하는 `_get_balance()`는 더 이상 읽기 경로에서 쓰이지 않는다 — 저장된 `Account.balance`가 legit한지 검증하는 용도로만 남아 있다(§6 참고).

---

## 6. 정합성 검증 (Reconciliation)

저장된 `Account.balance`(canonical) vs 원장 전체 재집계 간 drift 감지 순수 함수. 워터마크나 시점 스코프 없이 항상 원장 전체를 재집계한다 — 캐시가 없으므로 "이 시점까지만 비교"할 이유가 없어졌기 때문이다.

```python
def reconcile_balance(db, account_id) -> dict:
    acct = get_account(db, account_id)
    stored_balance = acct.balance  # canonical, 저장된 컬럼

    sum_credit = ...  # ledger_entries 전체 CREDIT 합계
    sum_debit = ...   # ledger_entries 전체 DEBIT 합계
    expected_balance = sum_credit - sum_debit
    delta = stored_balance - expected_balance

    return {
        "cached_balance": stored_balance,
        "expected_balance": expected_balance,
        "drift_detected": delta != 0,
        "delta": delta,
        ...
    }
```

- 잠금 없음, blocking 없음, 쓰기 동결 없음.
- drift 감지만 — 자동 수정 없음.
- **정상 흐름에서 drift는 항상 0**이다. `Account.balance`는 원장 쓰기와 원자적으로 갱신되므로 "아직 반영 안 된 최근 거래" 같은 정상적 불일치 경로가 없다 — `drift_detected=true`는 곧 저장값과 원장이 실제로 어긋난 버그를 의미하며, 예전처럼 "새로고침 지연"으로 해석해서는 안 된다.

---

## 7. 읽기 전용 뷰 (v_infobank_account_balances 외)

정보계가 직접 DB 접근 시 사용하는 뷰 2개: `v_infobank_account_balances` (원장에서 실시간 집계한 `balance`), `v_infobank_ledger_entries` (원장 조인). 두 뷰 모두 `accounts.balance` 저장 컬럼과 독립적으로 원장에서 즉시 계산하며, 정상 흐름에서는 항상 같은 값을 낸다.

- 뷰를 통한 접근은 convention 기반 read-only (SQLite mode=ro 미사용).
- 뷰는 SELECT 전용 DDL이므로 INSERT/UPDATE/DELETE 불가.

---

## 8. 계정계 vs 정보계 경계

| 구분 | 계정계 (Core Banking) | 정보계 (Analytics) |
|------|-----------------------|---------------------|
| 데이터 원천 | `ledger_entries`, `accounts`(`balance` 포함), `transactions`, `audit_logs` | `v_infobank_account_balances`/`v_infobank_ledger_entries` (뷰) |
| 쓰기 권한 | 있음 | 없음 (읽기 전용) |
| 잔액 계산 | 저장된 `accounts.balance` 컬럼 (원장 쓰기와 원자적으로 동기화) | 뷰 집계 (저장된 컬럼과 항상 동일한 값) |
| 인증 | 없음 (데모 범위) | X-Analytics-Key 헤더 (GET 5개) |
| 엔드포인트 수 | 7개 (계좌번호 조회·별칭 변경 추가) | GET 5개 (reconcile/balance/ledger/audit-logs/daily-total) |
