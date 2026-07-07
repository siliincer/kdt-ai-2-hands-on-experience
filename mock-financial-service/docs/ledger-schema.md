# Ledger Schema — 설계 원칙 및 근거

## 1. 이중기입 원장 (Double-Entry Ledger)

### 원칙

단일 `balance` 컬럼 갱신 방식 사용 안 함. 모든 잔액 변동은 `ledger_entries` 테이블에 차변(DEBIT)/대변(CREDIT) **쌍**으로 기록된다.

```
canonical_balance = SUM(amount WHERE entry_type='CREDIT')
                  - SUM(amount WHERE entry_type='DEBIT')
```

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

## 5. 잔액 캐시 스냅샷 (balance_snapshots)

### 목적

정보계(analytics)가 매 요청마다 원장 집계 쿼리를 실행하지 않도록 **파생 캐시** 제공.

### 스키마

```sql
CREATE TABLE balance_snapshots (
    account_id          TEXT PRIMARY KEY REFERENCES accounts(account_id),
    cached_balance      INTEGER NOT NULL,
    last_entry_rowid    INTEGER,          -- 고수위표(high-water mark), ledger_entries.rowid
    sum_credit          INTEGER NOT NULL,
    sum_debit           INTEGER NOT NULL,
    refreshed_at        DATETIME NOT NULL
);
```

### 핵심 제약

1. **계좌당 1행만 존재** — 스냅샷 갱신은 UPSERT (overwrite), append-only 아님.
2. **canonical balance 아님** — `cached_balance = sum_credit - sum_debit` 이지만, `last_entry_rowid` 까지만 계산된 값. 새 원장 항목 추가 후 갱신 전까지 stale.
3. **단일 계좌 범위 갱신** — `POST /api/v1/accounts/{id}/snapshot` 으로만 갱신. 일괄 갱신 없음, 스케줄러 없음.
4. **소스 오브 트루스 아님** — 잔액의 최종 권위는 항상 `ledger_entries` SUM.

### 고수위표(High-Water Mark) 의미

`last_entry_rowid` 는 스냅샷 계산에 포함된 마지막 원장 항목의 SQLite `rowid`(정수, 자동증가) — `entry_id`(UUID)와는 다른 값이니 혼동 주의. 정합성 검증(reconciliation) 시 이 rowid까지의 원장 항목만 재집계하여 비교.

**왜 "지금까지 전체"가 아니라 "이 rowid까지만" 비교하는가:**

캐시(`cached_balance`)는 마지막 새로고침 시점 값. 그 이후 새 거래가 들어오면 원장은 늘어나지만 캐시는 그대로 — 이건 정상적인 stale 상태지, 버그 아님. 만약 reconcile이 "지금 원장 전체"와 캐시를 비교하면, 새 거래가 하나만 생겨도 항상 불일치로 뜸(오탐/false positive) — 매번 refresh 안 했다고 재검증에 걸리는 꼴.

고수위표로 비교 범위를 "캐시 계산 당시 시점"으로 고정하면, reconcile은 "그 시점까지의 계산이 맞았는가"만 검증 — 즉 stale(정상, 새 거래 때문)과 corrupt(비정상, 캐시 계산 로직 자체의 버그)를 구분해낸다. 이게 이 필드의 존재 이유.

**SQLite 기반 구현**: `rowid`는 SQLite 내장 자동증가 정수(`database.py`에서 `sqlite:///./financial.db` 사용, `crud.py`의 `refresh_snapshot()`이 `SELECT MAX(rowid) FROM ledger_entries WHERE account_id = ...` 로 조회). Postgres 전환 시 `rowid` 개념이 없으므로 별도 auto-increment 시퀀스 컬럼으로 교체 필요 — README의 Postgres 전환 체크리스트에 이 항목 추가 필요.

---

## 6. 정합성 검증 (Reconciliation)

스냅샷과 원장 간 drift 감지 순수 함수.

```python
def reconcile(account_id, db) -> ReconciliationResult:
    snapshot = get_snapshot(db, account_id)
    # 스냅샷의 고수위표까지 원장 재집계
    recomputed = recompute_balance_up_to(db, account_id, snapshot.last_entry_rowid)
    delta = snapshot.cached_balance - recomputed
    drift_detected = (delta != 0)
    return ReconciliationResult(
        account_id=account_id,
        cached_balance=snapshot.cached_balance,
        expected_balance=recomputed,
        drift_detected=drift_detected,
        delta=delta,
        reconciled_at=utcnow(),
    )
```

- 잠금 없음, blocking 없음, 쓰기 동결 없음.
- drift 감지만 — 자동 수정 없음.
- 검증 결과는 로그/응답으로 반환.

---

## 7. 읽기 전용 뷰 (v_infobank_account_balances 외)

정보계가 직접 DB 접근 시 사용하는 뷰 3개: `v_infobank_account_balances` (실시간 집계 `balance`), `v_infobank_ledger_entries` (원장 조인), `v_account_snapshots` (캐시 조인, 스냅샷 시점 기준).

- 뷰를 통한 접근은 convention 기반 read-only (SQLite mode=ro 미사용).
- 뷰는 SELECT 전용 DDL이므로 INSERT/UPDATE/DELETE 불가.

---

## 8. 계정계 vs 정보계 경계

| 구분 | 계정계 (Core Banking) | 정보계 (Analytics) |
|------|-----------------------|---------------------|
| 데이터 원천 | `ledger_entries`, `accounts`, `transactions`, `audit_logs` | `v_infobank_account_balances`/`v_infobank_ledger_entries`/`v_account_snapshots` (뷰), `balance_snapshots` (캐시) |
| 쓰기 권한 | 있음 | 없음 (읽기 전용) |
| 잔액 계산 | 실시간 SUM | 캐시 또는 뷰 집계 |
| 인증 | 없음 (데모 범위) | X-Analytics-Key 헤더 (GET 4개만; 스냅샷 갱신 POST는 계정계 쪽, 무인증) |
| 엔드포인트 수 | 5개 (기존) + 갱신 POST 1개 | GET 4개 (snapshot/reconcile/balance/ledger) |
