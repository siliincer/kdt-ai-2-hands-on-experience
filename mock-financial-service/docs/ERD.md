# ERD — Mock Financial Service

계정계 (core-banking) + 정보계 (analytics) 전체 스키마 다이어그램.

## 엔티티 관계 다이어그램

```mermaid
erDiagram
    accounts {
        string account_id PK "UUID"
        string owner "NOT NULL"
        string currency "3-char, default KRW"
        datetime created_at "UTC"
    }

    transactions {
        string transaction_id PK "UUID"
        string idempotency_key UK "unique index"
        string payload_hash "SHA-256 hex, 64 chars"
        string sender_account_id FK "→ accounts"
        string receiver_account_id FK "→ accounts"
        bigint amount "positive integer, KRW"
        string status "success | failure"
        datetime created_at "UTC"
    }

    ledger_entries {
        string entry_id PK "UUID"
        string transaction_id FK "→ transactions"
        string account_id FK "→ accounts"
        string entry_type "DEBIT | CREDIT"
        bigint amount "always positive"
        bigint running_balance "point-in-time balance"
        datetime created_at "UTC"
    }

    audit_logs {
        string audit_log_id PK "UUID"
        string transaction_id "nullable FK hint"
        string actor "account_id or system"
        string action "ACCOUNT_CREATE | TRANSFER | TRANSFER_FAILED"
        string reason "human-readable"
        string status "success | failure"
        text payload_snapshot "JSON snapshot, nullable"
        datetime timestamp "UTC"
    }

    balance_snapshots {
        string account_id PK_FK "→ accounts, one row per account"
        bigint cached_balance "SUM(CREDIT)-SUM(DEBIT) at watermark"
        int last_entry_rowid "high-water-mark, ledger_entries.rowid"
        bigint sum_credit "stored credit sum up to watermark"
        bigint sum_debit "stored debit sum up to watermark"
        datetime refreshed_at "UTC, last refresh timestamp"
    }

    accounts ||--o{ transactions : "sender"
    accounts ||--o{ transactions : "receiver"
    accounts ||--o{ ledger_entries : "has"
    transactions ||--o{ ledger_entries : "generates"
    accounts ||--o| balance_snapshots : "cached by"
```

## 뷰 (View)

정보계 직접-DB 읽기 경로로 3개 뷰 제공 (모두 SELECT 전용, idempotent `CREATE VIEW IF NOT EXISTS`).

### `v_infobank_account_balances` — 실시간 계좌별 집계

```sql
CREATE VIEW v_infobank_account_balances AS
SELECT
    a.account_id,
    a.owner,
    a.currency,
    a.created_at,
    COALESCE(SUM(CASE WHEN le.entry_type = 'CREDIT' THEN le.amount ELSE 0 END), 0)
      - COALESCE(SUM(CASE WHEN le.entry_type = 'DEBIT'  THEN le.amount ELSE 0 END), 0)
      AS balance,
    COALESCE(SUM(CASE WHEN le.entry_type = 'CREDIT' THEN le.amount ELSE 0 END), 0) AS sum_credit,
    COALESCE(SUM(CASE WHEN le.entry_type = 'DEBIT'  THEN le.amount ELSE 0 END), 0) AS sum_debit,
    COUNT(le.entry_id) AS entry_count
FROM accounts a
LEFT JOIN ledger_entries le ON le.account_id = a.account_id
GROUP BY a.account_id, a.owner, a.currency, a.created_at;
```

### `v_infobank_ledger_entries` — 원장 항목 (계좌 메타데이터 조인)

`ledger_entries` 를 `accounts.owner`/`currency` 와 조인한 비정규화 뷰. 컬럼: `entry_id, account_id, owner, currency, transaction_id, entry_type, amount, running_balance, created_at`.

### `v_account_snapshots` — 캐시 기반 뷰 (실시간 아님)

`accounts` 를 `balance_snapshots` 와 LEFT JOIN — 스냅샷이 아직 없는 계좌는 캐시 필드가 NULL/0. `v_infobank_account_balances` 와 달리 마지막 `POST /accounts/{id}/snapshot` 호출 시점 기준.

**설계 원칙**: 뷰는 SELECT 전용. 실시간 뷰(`v_infobank_*`)의 `balance`는 항상 원장에서 즉시 집계 — `balance_snapshots.cached_balance`(캐시)와 독립적으로 존재.

## 엔티티 설명

| 엔티티 | 역할 | 계층 |
|--------|------|------|
| `accounts` | 계좌 메타데이터 | 계정계 |
| `transactions` | 송금 이벤트 헤더 + Idempotency-Key | 계정계 |
| `ledger_entries` | 이중기입 차변/대변 원장 | 계정계 |
| `audit_logs` | append-only 감사 로그 (DB 트리거 불변) | 계정계 |
| `balance_snapshots` | 잔액 캐시 (정보계용, 계좌당 1행 덮어쓰기) | 정보계 캐시 |
| `v_infobank_account_balances` | 읽기 전용 뷰, 실시간 집계 (정보계 직접-DB 읽기) | 정보계 뷰 |
| `v_infobank_ledger_entries` | 읽기 전용 뷰, 원장 항목 조인 | 정보계 뷰 |
| `v_account_snapshots` | 읽기 전용 뷰, 캐시 조인 (스냅샷 시점 기준) | 정보계 뷰 |
