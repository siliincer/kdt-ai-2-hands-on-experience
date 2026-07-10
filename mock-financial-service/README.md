# Mock Financial Service

Python/FastAPI/SQLAlchemy/SQLite — double-entry ledger 계정계 백엔드 + 정보계(analytics) 읽기 접근 + 카드(Card) 이연정산.

root uv workspace(`kdt-ai-2-hands-on-experience`)의 멤버 패키지(`financial-service`)입니다. 전체 스키마/API/정보계 인계 문서는 [`docs/README.md`](docs/README.md) 참고.

## 구조

```
src/financial_service/
  app.py              # FastAPI factory, 라우터 마운트, 마이그레이션 실행
  database.py         # SQLAlchemy engine, session, Base
  models.py           # Account, Transaction(+정산 discriminator), LedgerEntry,
                       # AuditLog, BalanceSnapshot, Card, CardLedgerEntry ORM
  schemas.py           # Pydantic request/response schemas
  crud.py             # ORM-only CRUD, custom exceptions
  routers.py          # 계정계 API (계좌/송금/스냅샷갱신)
  analytics_router.py # 정보계 API (X-Analytics-Key 인증)
  card_router.py       # 카드 API (생성/결제/정산)
  migrations.py        # 감사로그 불변성 트리거 + 정보계 뷰 3개 (SQLite + Postgres DDL)
docs/
  README.md            # 정보계 인계 인덱스 + 빠른시작
  ERD.md                # Mermaid 전체 스키마 다이어그램
  ledger-schema.md      # 설계 원칙 + 근거 (워터마크, 이중기입 등)
  api-reference.md      # 정보계 API 상세 스펙
tests/
  conftest.py           # In-memory SQLite fixture (StaticPool)
  test_smoke.py, test_transfers.py, test_transactions.py,
  test_audit_log.py, test_ledger_integrity.py,
  test_snapshot.py, test_analytics_api.py, test_audit_logs_api.py,
  test_crosspath_equality.py, test_infobank_view.py,
  test_cards.py         # 137개 테스트
```

## API

### 계정계 (무인증, owner-side)

| Method | Path                                 | Description                         |
| ------ | ------------------------------------ | ----------------------------------- |
| POST   | `/api/v1/accounts`                   | 계좌 생성 (201)                     |
| GET    | `/api/v1/accounts/{id}`              | 계좌 조회 (200/404)                 |
| GET    | `/api/v1/accounts/{id}/balance`      | 잔액 조회 (200/404)                 |
| GET    | `/api/v1/accounts/{id}/transactions` | 거래내역 조회 (200/404)             |
| POST   | `/api/v1/transfers`                  | 송금 (200, Idempotency-Key 필수)    |
| POST   | `/api/v1/accounts/{id}/snapshot`     | 잔액 캐시 스냅샷 갱신 (200, 무인증) |

### 카드 (무인증, owner-side)

| Method | Path                         | Description                                           |
| ------ | ---------------------------- | ----------------------------------------------------- |
| POST   | `/api/v1/cards`              | 카드 생성 (201, 계좌당 N개)                           |
| GET    | `/api/v1/cards/{id}`         | 카드 조회 (200/404)                                   |
| POST   | `/api/v1/cards/{id}/charges` | 카드 결제 (201, Idempotency-Key 필수, 한도초과시 422) |
| POST   | `/api/v1/cards/{id}/settle`  | 정산 — 계좌로 실제 이체 + 한도 리셋 (200)             |

### 정보계 (X-Analytics-Key 헤더 필수)

| Method | Path                                         | Description                |
| ------ | -------------------------------------------- | -------------------------- |
| GET    | `/api/v1/analytics/accounts/{id}/balance`    | 실시간 잔액                |
| GET    | `/api/v1/analytics/accounts/{id}/ledger`     | 원장 항목 목록             |
| GET    | `/api/v1/analytics/accounts/{id}/snapshot`   | 캐시된 스냅샷 조회         |
| GET    | `/api/v1/analytics/accounts/{id}/reconcile`  | 스냅샷 vs 원장 정합성 검증 |
| GET    | `/api/v1/analytics/accounts/{id}/audit-logs` | 계좌 관련 감사로그         |
| GET    | `/api/v1/analytics/cards/{id}`               | 카드 상세                  |
| GET    | `/api/v1/analytics/cards/{id}/ledger`        | 카드 원장 항목 목록        |

읽기 전용 DB 뷰 3개(`v_infobank_account_balances`, `v_infobank_ledger_entries`, `v_account_snapshots`)로 직접 DB 조회도 가능 — 상세는 [`docs/ERD.md`](docs/ERD.md).

## 실행

이 프로젝트는 root uv workspace 멤버입니다. **repo root에서** 실행하거나, **이 디렉토리 안에서** `uv run` 쓰면 됩니다(둘 다 workspace 공유 lock/venv 사용).

```bash
# root에서
cd /path/to/kdt-ai-2-hands-on-experience
uv run --package financial-service uvicorn financial_service.app:app --reload --port 8002

# 또는 이 디렉토리 안에서
cd mock-financial-service
uv run uvicorn financial_service.app:app --reload --port 8002

# 또는
fastapi dev src/financial_service/app.py --port 8002
```

⚠️ SQLite 파일(`financial.db`)은 **서버 실행 시점의 현재 디렉토리 기준 상대경로**(`./financial.db`)에 생성됩니다. 위 두 실행 위치 중 어디서 띄웠는지에 따라 파일 위치가 달라지니 주의. `.gitignore` 처리되어 있어 커밋 안 됨 — 로컬 전용, 팀원 간 공유 안 됨.

## 테스트

```bash
uv run --package financial-service pytest mock-financial-service/tests/ -v   # root에서
uv run pytest tests/ -v                                                      # 디렉토리 안에서
```

137개 테스트 (계정계 핵심 + 스냅샷/정보계/카드).

## 에러 응답 스키마

모든 에러는 HTTP {detail} 사용 안 함 — 항상 다음 형식:

```json
{ "error_code": "INSUFFICIENT_BALANCE", "message": "Balance 1000 < 5000" }
```

| error_code              | HTTP | 설명                                            |
| ----------------------- | ---- | ----------------------------------------------- |
| ACCOUNT_NOT_FOUND       | 404  | 없는 계좌                                       |
| INSUFFICIENT_BALANCE    | 422  | 잔액 부족                                       |
| SELF_TRANSFER           | 422  | 자기 계좌 송금                                  |
| MISSING_IDEMPOTENCY_KEY | 422  | Idempotency-Key 헤더 없음                       |
| IDEMPOTENCY_CONFLICT    | 409  | 같은 키, 다른 payload                           |
| VALIDATION_ERROR        | 422  | Pydantic 입력 검증 실패                         |
| SNAPSHOT_NOT_FOUND      | 404  | 아직 스냅샷 갱신 안 된 계좌                     |
| CARD_NOT_FOUND          | 404  | 없는 카드                                       |
| CARD_LIMIT_EXCEEDED     | 422  | 카드 한도 초과 결제 시도                        |
| UNAUTHORIZED            | 401  | X-Analytics-Key 없거나 불일치 (정보계 API 전용) |

## 설계 원칙

### 이중기입 원장

단일 balance 컬럼 갱신 방식 사용 안 함. 모든 잔액 변동은 `ledger_entries` 테이블에 차변(DEBIT)/대변(CREDIT) 쌍으로 기록. 잔액은 `SUM(CREDIT) - SUM(DEBIT)` 계산.

### 원자적 송금

차변+대변+감사로그 INSERT가 단일 DB 트랜잭션으로 묶임. 부분성공 불가.

### 감사로그 불변성

`audit_logs` 테이블에 SQLite `CREATE TRIGGER BEFORE UPDATE/DELETE ... RAISE(ABORT)` 적용.
애플리케이션 계층 방어에만 의존하지 않고 DB 레벨에서 강제.

### Idempotency

`Idempotency-Key` 헤더 + payload SHA-256 해시 조합으로 중복 요청 감지 (`POST /transfers`, `POST /cards/{id}/charges` 둘 다 적용).

- 동일 키 + 동일 payload → 기존 트랜잭션 반환 (safe replay)
- 동일 키 + 다른 payload → 409 IDEMPOTENCY_CONFLICT

### 금액 무결성

금액 필드 전체 `BigInteger` (KRW 원 단위 정수). Float 사용 없음. 반올림 오차 없음.

### 잔액 캐시 (스냅샷) + 워터마크

`balance_snapshots`(계좌), 카드는 `Transaction`에 정산 태그 — 둘 다 계좌/카드당 매번 원장 전체 재계산 안 하도록 캐시 계층 제공. `last_entry_rowid`/`settlement_watermark_rowid`(SQLite rowid 기반 고수위표)로 "어디까지 반영됐는지" 추적, 그 이후 항목만 재계산해서 정합성 검증(reconcile) — stale(정상)과 corrupt(버그)를 구분하기 위함. 상세 근거는 [`docs/ledger-schema.md`](docs/ledger-schema.md).

### 카드 이연정산

카드는 계좌와 별개 최소 원장(`card_ledger_entries`)만 갖고, 결제 시점엔 계좌를 안 건드림. 한도 = 순수 지출상한(미정산 사용액 + 결제액 > 한도면 거부). 정산은 새 엔티티 없이 기존 `Transaction`을 discriminator 필드(`settlement_type=CARD_SETTLEMENT` 등)로 재사용 — 단일 동기 수동트리거, 배치/스케줄러 없음.

## ⚠️ Postgres 전환 시 필수 사항

1. **SERIALIZABLE isolation 명시 설정 필요**

   SQLite는 파일 레벨 락이지만 Postgres에서는 동시 송금 시 lost update / phantom read 위험 존재.

   ```python
   engine = create_engine(
       "postgresql+asyncpg://...",
       execution_options={"isolation_level": "SERIALIZABLE"},
   )
   ```

   또는 각 트랜잭션마다:

   ```python
   with engine.connect().execution_options(isolation_level="SERIALIZABLE") as conn:
       ...
   ```

   `READ COMMITTED`로 두면 동시 잔액 체크 후 출금 시 경쟁 조건 발생 가능.

2. **트리거 DDL 교체**: `migrations.py`의 `_apply_postgres_triggers()` 함수가 PL/pgSQL 함수 기반 트리거 DDL 포함. dialect 자동 감지로 적용됨.

3. **asyncpg / psycopg 드라이버 설치** 필요: `asyncpg>=0.30.0` 또는 `psycopg[binary]>=3.2`.

4. **DATABASE_URL** 환경변수를 `postgresql+asyncpg://...` 형식으로 교체.

5. **`rowid` 기반 워터마크 재설계 필요**: `last_entry_rowid`/`settlement_watermark_rowid`는 SQLite 전용 개념(`rowid`). Postgres엔 `rowid`가 없으므로 별도 auto-increment 시퀀스 컬럼으로 교체해야 함.
