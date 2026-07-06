# Mock Financial Service

Python/FastAPI/SQLAlchemy/SQLite — double-entry ledger 계정계 백엔드

## 구조

```
src/financial_service/
  app.py          # FastAPI factory, error handlers
  database.py     # SQLAlchemy engine, session, Base
  models.py       # Account, Transaction, LedgerEntry, AuditLog ORM
  schemas.py      # Pydantic request/response schemas
  crud.py         # ORM-only CRUD, custom exceptions
  routers.py      # 5 API endpoints
  migrations.py   # Audit log immutability triggers (SQLite + Postgres DDL)
tests/
  conftest.py     # In-memory SQLite fixture (StaticPool)
  test_smoke.py   # 12 smoke tests (9 required + 3 bonus)
```

## 5개 API

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/accounts` | 계좌 생성 (201) |
| GET | `/api/v1/accounts/{id}` | 계좌 조회 (200/404) |
| GET | `/api/v1/accounts/{id}/balance` | 잔액 조회 (200/404) |
| GET | `/api/v1/accounts/{id}/transactions` | 거래내역 조회 (200/404) |
| POST | `/api/v1/transfers` | 송금 (201, Idempotency-Key 필수) |

## 실행

```bash
uv pip install -e .
uvicorn financial_service.app:app --reload
```

## 테스트

```bash
uv run --with pytest pytest tests/ -v
```

## 에러 응답 스키마 (임시)

모든 에러는 HTTP {detail} 사용 안 함 — 항상 다음 형식:

```json
{"error_code": "INSUFFICIENT_BALANCE", "message": "Balance 1000 < 5000"}
```

| error_code | HTTP | 설명 |
|------------|------|------|
| ACCOUNT_NOT_FOUND | 404 | 없는 계좌 |
| INSUFFICIENT_BALANCE | 422 | 잔액 부족 |
| SELF_TRANSFER | 422 | 자기 계좌 송금 |
| MISSING_IDEMPOTENCY_KEY | 422 | Idempotency-Key 헤더 없음 |
| IDEMPOTENCY_CONFLICT | 409 | 같은 키, 다른 payload |
| VALIDATION_ERROR | 422 | Pydantic 입력 검증 실패 |

## 설계 원칙

### 이중기입 원장

단일 balance 컬럼 갱신 방식 사용 안 함. 모든 잔액 변동은 `ledger_entries` 테이블에 차변(DEBIT)/대변(CREDIT) 쌍으로 기록. 잔액은 `SUM(CREDIT) - SUM(DEBIT)` 계산.

### 원자적 송금

차변+대변+감사로그 INSERT가 단일 DB 트랜잭션으로 묶임. 부분성공 불가.

### 감사로그 불변성

`audit_logs` 테이블에 SQLite `CREATE TRIGGER BEFORE UPDATE/DELETE ... RAISE(ABORT)` 적용.
애플리케이션 계층 방어에만 의존하지 않고 DB 레벨에서 강제.

### Idempotency

`Idempotency-Key` 헤더 + payload SHA-256 해시 조합으로 중복 요청 감지.
- 동일 키 + 동일 payload → 기존 트랜잭션 반환 (safe replay)
- 동일 키 + 다른 payload → 409 IDEMPOTENCY_CONFLICT

### 금액 무결성

금액 필드 전체 `BigInteger` (KRW 원 단위 정수). Float 사용 없음. 반올림 오차 없음.

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
