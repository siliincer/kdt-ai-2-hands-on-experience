# Mock Financial Service

Python/FastAPI/SQLAlchemy/SQLite — double-entry ledger 계정계 백엔드 + 정보계(analytics) 읽기 접근 + 카드(Card) 이연정산.

root uv workspace(`kdt-ai-2-hands-on-experience`)의 멤버 패키지(`financial-service`)입니다. 전체 스키마/API/정보계 인계 문서는 [`docs/README.md`](docs/README.md) 참고.

## 구조

```
src/financial_service/
  app.py              # FastAPI factory, 라우터 마운트, 시작 시 alembic upgrade
  database.py         # SQLAlchemy engine, session, Base, 고정 DATABASE_URL
  migration_runtime.py # alembic upgrade head 프로그래매틱 실행 (app.py/seed_dev_db.py 공용)
  models.py           # Account(balance/bank_name/account_number/alias 포함),
                       # Transaction(+정산 discriminator), LedgerEntry,
                       # AuditLog, Card, CardLedgerEntry(merchant_name), CardProduct ORM
  mock_data.py         # canonical mock 데이터셋 (Account~4개월 거래내역)
  demo_fixtures.py     # mock_data 데이터셋을 dict/JSON 데모 fixture로 노출
  schemas.py           # Pydantic request/response schemas
  crud.py             # ORM-only CRUD, custom exceptions
  routers.py          # 계정계 API (계좌/송금)
  analytics_router.py # 정보계 API (X-Analytics-Key 인증)
  card_router.py       # 카드 API (생성/결제/정산)
  migrations.py        # 감사로그 불변성 트리거 + 정보계 뷰 2개 (SQLite + Postgres DDL)
                        # ── DB 스키마 마이그레이션(Alembic)과는 다른 파일, 이름 유사 주의 ──
alembic.ini             # Alembic 설정 (script_location → alembic_migrations/)
alembic_migrations/
  env.py                 # models.py의 Base.metadata + DATABASE_URL 연결
  versions/               # 마이그레이션 파일들 (autogenerate로 생성, 손대지 않음)
docs/
  README.md            # 정보계 인계 인덱스 + 빠른시작
  ERD.md                # Mermaid 전체 스키마 다이어그램
  ledger-schema.md      # 설계 원칙 + 근거 (이중기입, 잔액 정합성 등)
  api-reference.md      # 정보계 API 상세 스펙
scripts/
  seed_dev_db.py        # canonical mock 데이터셋을 dev DB에 insert하는 CLI
tests/
  conftest.py           # In-memory SQLite fixture (StaticPool)
  test_smoke.py, test_transfers.py, test_transactions.py,
  test_audit_log.py, test_ledger_integrity.py,
  test_snapshot.py, test_analytics_api.py, test_audit_logs_api.py,
  test_crosspath_equality.py, test_infobank_view.py,
  test_cards.py, (+ mock 데이터/거래내역 테스트 다수) # 248개 테스트
```

## API

### 계정계 (무인증, owner-side)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/accounts` | 계좌 생성 (201) |
| GET | `/api/v1/accounts/{id}` | 계좌 조회 (200/404) |
| GET | `/api/v1/accounts/{id}/balance` | 잔액 조회 (200/404) |
| GET | `/api/v1/accounts/{id}/transactions` | 거래내역 조회 (200/404) |
| POST | `/api/v1/transfers` | 송금 (200, Idempotency-Key 필수) |

`balance`는 `Account` 테이블의 실 컬럼 — 원장(ledger_entries) 기록마다 같은 DB 트랜잭션 안에서 즉시 갱신됨(별도 갱신/refresh API 없음). 원장 합계 재계산은 검증(`/analytics/.../reconcile`)에만 쓰임 — 상세는 [설계 원칙 §잔액 정합성](#잔액-정합성-canonical-balance).

**계좌번호 / 은행명 (신규):** `Account`는 `bank_name`(고정값 `"KDT은행"` — 이 mock 서비스는 단일 은행만 표현), `account_number`(계좌 생성 시 자동 발급, `xxx-xxx-xxxxxx` 포맷, unique) 필드를 가짐. `POST/GET /accounts` 응답에 항상 포함 — 사용자가 본인 계좌 확인 시 은행명/계좌번호를 볼 수 있어야 한다는 요구사항 반영.

`POST /transfers`는 내부 `account_id`(UUID)가 아니라 **계좌번호 + 은행명**으로 송금 대상을 식별한다(실제 은행 송금 UX와 동일):
```json
{
  "sender_account_number": "110-123-456789",
  "receiver_bank_name": "KDT은행",
  "receiver_account_number": "110-987-654321",
  "amount": 10000
}
```
서버가 `account_number`로 내부 계좌를 조회해 `account_id`로 변환한 뒤 처리 — `ledger_entries`/`transactions` 등 원장 스키마는 여전히 `account_id`를 canonical FK로 사용(변경 없음). `receiver_bank_name`이 `"KDT은행"`이 아니면 422 `BANK_NOT_SUPPORTED`로 거절(다은행 송금은 미지원, 이 mock 서비스가 표현하는 은행이 하나뿐이라 검증 목적).

### 카드 (무인증, owner-side)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/cards` | 카드 생성 (201, 계좌당 N개) |
| GET | `/api/v1/cards/{id}` | 카드 조회 (200/404) |
| POST | `/api/v1/cards/{id}/charges` | 카드 결제 (201, Idempotency-Key 필수, 한도초과시 422) |
| POST | `/api/v1/cards/{id}/settle` | 정산 — 계좌로 실제 이체 + 한도 리셋 (200) |

### 정보계 (X-Analytics-Key 헤더 필수)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/analytics/accounts/{id}/balance` | 저장된 canonical 잔액(`Account.balance`) |
| GET | `/api/v1/analytics/accounts/{id}/ledger` | 원장 항목 목록 |
| GET | `/api/v1/analytics/accounts/{id}/reconcile` | 저장된 잔액 vs 원장 재계산 정합성 검증 |
| GET | `/api/v1/analytics/accounts/{id}/audit-logs` | 계좌 관련 감사로그 |
| GET | `/api/v1/analytics/cards/{id}` | 카드 상세 |
| GET | `/api/v1/analytics/cards/{id}/ledger` | 카드 원장 항목 목록 |

읽기 전용 DB 뷰 2개(`v_infobank_account_balances`, `v_infobank_ledger_entries`)로 직접 DB 조회도 가능 — 상세는 [`docs/ERD.md`](docs/ERD.md).

## 실행

이 프로젝트는 root uv workspace 멤버입니다. **repo root에서** 실행하거나, **이 디렉토리 안에서** `uv run` 쓰면 됩니다(둘 다 workspace 공유 lock/venv 사용).

```bash
# root에서
cd /path/to/kdt-ai-2-hands-on-experience
uv run --package financial-service uvicorn financial_service.app:app --reload

# 또는 이 디렉토리 안에서
cd mock-financial-service
uv run uvicorn financial_service.app:app --reload
```

SQLite 파일(`financial.db`)은 **항상 `mock-financial-service/financial.db`** 고정 경로에 생성됩니다(`database.py`가 `__file__` 기준 절대경로로 계산 — 어느 위치에서 서버를 띄웠는지와 무관). `.gitignore` 처리되어 있어 커밋 안 됨 — 로컬 전용, 팀원 간 공유 안 됨. `DATABASE_URL` 환경변수로 다른 경로/DB(Postgres 등)로 덮어쓸 수 있습니다.

**스키마 자동 동기화(Alembic)**: 서버가 시작될 때마다 `alembic upgrade head`가 자동 실행됩니다(`app.py` startup hook). `models.py`에 컬럼/테이블을 추가·변경한 뒤 **서버를 껐다 켜기만 하면** 로컬 `financial.db`가 자동으로 최신 스키마에 맞춰집니다 — 예전처럼 `rm financial.db` 하고 수동으로 재시딩할 필요 없음. `Base.metadata.create_all()`과 달리 기존 데이터를 지우지 않고 스키마만 변경합니다.

모델을 바꿨으면 커밋 전에 migration 파일을 새로 만들어야 합니다:
```bash
uv run alembic revision --autogenerate -m "설명"
```
`alembic_migrations/versions/`에 생성된 파일을 확인하고 함께 커밋하세요.

## 테스트

```bash
uv run --package financial-service pytest mock-financial-service/tests/ -v   # root에서
uv run pytest tests/ -v                                                      # 디렉토리 안에서

# 신규 mock 데이터(CardProduct 등) 테스트만
uv run pytest tests/test_canonical_dataset.py tests/test_card_product_specs.py \
  tests/test_demo_fixture_db_load.py tests/test_demo_fixtures.py \
  tests/test_fixture_adapter_smoke.py tests/test_mock_accounts_cards.py \
  tests/test_mock_card_products.py tests/test_seed_dev_db.py -v
```

248개 테스트 (계정계 핵심 + 잔액정합성/정보계/카드 142개 + CardProduct·4개월 거래내역 mock 데이터 106개).

## 에러 응답 스키마

모든 에러는 HTTP {detail} 사용 안 함 — 항상 다음 형식:

```json
{"error_code": "INSUFFICIENT_BALANCE", "message": "Balance 1000 < 5000"}
```

| error_code | HTTP | 설명 |
|------------|------|------|
| ACCOUNT_NOT_FOUND | 404 | 없는 계좌(번호) |
| BANK_NOT_SUPPORTED | 422 | 송금 대상 `receiver_bank_name`이 지원 은행("KDT은행") 아님 |
| INSUFFICIENT_BALANCE | 422 | 잔액 부족 |
| SELF_TRANSFER | 422 | 자기 계좌 송금 |
| MISSING_IDEMPOTENCY_KEY | 422 | Idempotency-Key 헤더 없음 |
| IDEMPOTENCY_CONFLICT | 409 | 같은 키, 다른 payload |
| VALIDATION_ERROR | 422 | Pydantic 입력 검증 실패 |
| CARD_NOT_FOUND | 404 | 없는 카드 |
| CARD_LIMIT_EXCEEDED | 422 | 카드 한도 초과 결제 시도 |
| UNAUTHORIZED | 401 | X-Analytics-Key 없거나 불일치 (정보계 API 전용) |

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

### 잔액 정합성 (canonical balance)

`Account.balance`가 canonical 잔액 — `transfer`/`settle_card`/계좌 생성(초기입금) 등 원장에 쓰는 모든 경로가 같은 DB 트랜잭션 안에서 `LedgerEntry`와 `Account.balance`를 함께 갱신한다(원장 따로, 잔액 갱신 따로가 아님 — 두 단계로 쪼개면 그 사이에 drift 날 여지가 생기므로 원자적으로 묶음). 원장 전체를 SUM(CREDIT)-SUM(DEBIT)로 재계산하는 `_get_balance()`는 읽기 경로에서 안 쓰고, **저장된 `balance`가 legit한지 검증하는 용도로만** 쓰인다 — `GET /analytics/accounts/{id}/reconcile`이 저장값(`cached_balance`) vs 재계산값(`expected_balance`)을 비교해 `drift_detected`를 리턴. 정상 흐름에서 drift는 절대 0이 아니면 버그 신호. 카드는 별도로 `Transaction`에 정산 태그(`settlement_watermark_rowid`, SQLite rowid 기반 고수위표)로 미정산분을 추적 — 상세 근거는 [`docs/ledger-schema.md`](docs/ledger-schema.md).

### 카드 이연정산

카드는 계좌와 별개 최소 원장(`card_ledger_entries`)만 갖고, 결제 시점엔 계좌를 안 건드림. 한도 = 순수 지출상한(미정산 사용액 + 결제액 > 한도면 거부). 정산은 새 엔티티 없이 기존 `Transaction`을 discriminator 필드(`settlement_type=CARD_SETTLEMENT` 등)로 재사용 — 단일 동기 수동트리거, 배치/스케줄러 없음.

## 2026-07-10 추가사항 — CardProduct 카탈로그 + Mock 데이터

Account/Card mock 데이터 + 신규 CardProduct(카드 상품 카탈로그) 기능 추가. 로컬 dev DB seed / 데모 fixture / pytest fixture 세 용도가 하나의 canonical 데이터셋을 공유.

**신규/변경 파일**

- `src/financial_service/models.py` — `CardProduct` 모델 추가 (`card_products` 테이블). `category` 필드는 Enum 5종(외식/쇼핑/여행/웹구독/마트-편의점).
- `src/financial_service/mock_data.py` — canonical mock 데이터셋. Account 5개, Card 8개(계좌당 1~2개), CardProduct 20개(카테고리당 4개). 전부 고정 UUID라 재실행해도 값 동일(결정론적).
- `src/financial_service/demo_fixtures.py` — 위 데이터셋을 dict/JSON 형태 데모 fixture로 노출.
- `scripts/seed_dev_db.py` — dev DB에 mock 데이터 insert하는 CLI 스크립트.
- `tests/conftest.py` — `accounts`/`cards`/`card_products` pytest fixture 3개 추가, 같은 mock_data 데이터셋 재사용.
- `models.py` (워크스페이스 루트) — re-export shim.

**FK 연결 여부**

- `Account → Card`: 기존과 동일하게 FK 유지 (`Card.account_id`, `nullable=False`). 발급된 카드는 반드시 실존 계좌에 속해야 함. mock 데이터도 이 규칙을 그대로 따름 — `MOCK_CARDS`의 각 row가 `MOCK_ACCOUNTS`에 실존하는 `account_id` 값을 참조.
- `Card ↔ CardProduct`: **FK 연결 없음.** `CardProduct`는 실제 발급된 카드와 무관한 독립 상품 카탈로그로 설계됨 — `card_products` 테이블에 `card_id` 같은 컬럼 자체가 존재하지 않음. 상품 목록 조회/분석(연회비·혜택 등 스펙 통계)이 목적이고, "어떤 카드가 어떤 상품인지" 매핑이나 상품별 발급/이용률 분석은 현재 스코프 밖. `category` 값(외식/쇼핑 등)은 향후 소비카테고리 기반 카드 추천 기능을 염두에 둔 필드지만, 지금은 스키마 레벨 강제 없이 문자열 값으로만 존재.

**`models.py` (워크스페이스 루트 shim) — 왜 필요한가**

이 저장소는 uv workspace라 실제 ORM 모델 정의는 `src/financial_service/models.py`에 있다. 하지만 `scripts/seed_dev_db.py`처럼 **워크스페이스 루트에서 직접 실행하는 스크립트**는 `sys.path`에 `src/`가 잡혀 있지 않으면 `from financial_service.models import ...`가 실패한다. 루트의 `models.py`는 로직이 전혀 없는 순수 재노출(re-export) 파일 — `sys.path`에 `src/`를 추가한 뒤 `financial_service.models`의 모든 모델(`Account`, `Card`, `CardProduct` 등)을 그대로 import해서 다시 내보내기만 한다. 덕분에 루트에서 `from models import CardProduct, Account, Card` 한 줄로 바로 쓸 수 있음. 모델 정의는 여전히 `src/financial_service/models.py` 하나뿐이고, 이 파일은 단순 진입점(entry point) 역할.

**`scripts/seed_dev_db.py` — 동작 상세**

dev DB(SQLite, 기본 `./financial.db`)에 `mock_data.py`의 canonical 데이터셋을 insert하는 CLI.

1. 테이블 생성 (`Base.metadata.create_all`; `--reset` 플래그 주면 먼저 `drop_all` 후 재생성)
2. SQLite FK 강제 pragma(`PRAGMA foreign_keys=ON`) 활성화
3. `validate_dataset()`으로 pre-flight 데이터 구조 검증
4. **FK-safe 순서로 insert**: Account 먼저 insert + `flush()` (FK 대상이 먼저 DB에 존재해야 하므로) → 그다음 Card + CardProduct insert (CardProduct는 독립이라 순서 무관)
5. **Idempotent**: Account가 이미 1건이라도 있으면 insert 전체를 스킵 (재실행해도 중복 insert 안 됨)
6. **Post-insert 검증**: 총 개수(Account 5 / Card 5~10 / CardProduct 20), 계좌당 카드 1~2개, `Card.account_id`가 실제 Account를 가리키는지 FK 무결성, 카테고리별 정확히 4개 분포 — 하나라도 깨지면 `AssertionError`로 실패하고 exit code 1 반환

사용법:
```bash
python scripts/seed_dev_db.py               # 기본 sqlite:///./financial.db
python scripts/seed_dev_db.py sqlite:///./other.db
python scripts/seed_dev_db.py --reset        # 기존 테이블 DROP 후 재생성
```

**검증**: `uv run pytest tests/ -q` → 248 passed.

**프론트엔드 병합 영향**: 없음. `app.py`/router 안 건드림 — API 엔드포인트 추가·변경 전혀 없음. 변경분은 기존 `models.py`/`conftest.py`에 추가만 된 것(additive)이거나 신규 파일뿐. API 서피스, 포트, nginx 라우팅, docker-compose 다 무관 — 프론트가 붙는 지점(HTTP 엔드포인트)은 그대로라 병합 충돌 가능성 거의 없음.

## 2026-07-13 추가사항 — 4개월치 페르소나 거래내역 mock 데이터

위 CardProduct 작업 위에 실제 소비자처럼 보이는 거래내역(계좌간송금/일반결제/카드결제)을 4개월치(2026-03-10~2026-07-10) 추가. 3인 소비 페르소나(`RealFinance_소비페르소나.md`) 기반.

**페르소나 → 계좌 매핑**

- Account 1(김지훈) — 안정형 직장인, 급여일 25일
- Account 2(박서연) — 재테크 워킹맘, 급여일 21일
- Account 3(이도윤) — 불안정 프리랜서, 불규칙 입금 + 리스크 신호(이체실패→재시도, 보복소비 몰림)
- Account 4/5 — 페르소나 미지정, 김지훈 패턴의 축소판 기본값

**카테고리 → 거래유형 매핑**

- 주거비/저축/투자/대출이자 → 계좌간송금 (Transaction, 카드 미개입)
- 통신비/구독료/헬스장/학원비/관리비 → 일반결제 (Transaction, 수신처는 biller 계좌)
- 식비/쇼핑/여행/문화/교통/편의점 → 카드결제 (CardLedgerEntry, 정산 전까지 계좌잔액 미변경)

**신규/변경 파일**

- `src/financial_service/mock_data.py` — `_build_transaction_dataset()` 결정론적 생성기 추가. 고정 스케줄(급여/월세 등) + 계좌·월별로 시드된 `random.Random`(카드결제 금액·날짜)만 사용 — OS/wall-clock 난수 없음, 재실행해도 항상 동일 결과. 하나의 전역 시간순 이벤트 타임라인을 걸으면서 Transaction/LedgerEntry/CardLedgerEntry를 생성하므로 `running_balance`는 수기 계산이 아니라 시뮬레이션 결과로 자동 산출됨.
  - `MOCK_BILLER_ACCOUNTS` 3개 추가(저축은행/증권사/대출은행 — 총 7개)
  - `MOCK_EXTERNAL_SOURCE_ACCOUNTS` 신규 — 급여입금/지인송금처럼 실제 발신 계좌가 없는 입금의 FK 대상(계좌 테이블에 discriminator 컬럼이 없어 "결제 대상" biller와는 별도 목록으로 분리)
  - `MOCK_TRANSACTIONS` / `MOCK_LEDGER_ENTRIES` / `MOCK_CARD_LEDGER_ENTRIES` + 대응 `make_*_rows()` 팩토리 함수
- `scripts/seed_dev_db.py` — Transaction/LedgerEntry/CardLedgerEntry insert 추가(FK-safe 순서: Account류 → Card/CardProduct → Transaction → LedgerEntry/CardLedgerEntry), 이중기입(DEBIT=CREDIT=금액) + FK 무결성 post-insert 검증 추가
- `tests/test_risk_signals.py` — 이도윤의 리스크 신호 3건(통신비/OTT/월세 이체실패→재시도)이 통합 데이터셋 안에서 실제로 존재하고 이중기입 제약을 지키는지 검증

**Account 테이블 구조 참고**: 계좌 종류(유저/biller/외부소스) 구분 컬럼이 없어서, `account_id` prefix로 구분함 — `acct-000*`(유저 5개), `acct-b00*`(biller 7개 + 외부소스 1개). `scripts/seed_dev_db.py`의 "5 Accounts" 카운트 체크는 유저 계좌만 필터링해서 검사.

**거래량**: 김지훈 약 24.5건/월, 박서연 약 21.5건/월 (페르소나 문서 "월 20~30건" 범위 내). 이도윤은 약 45건/월로 범위 초과 — 사용자가 명시적으로 허용.

**검증**: `uv run pytest tests/ -q` → 248 passed. `scripts/seed_dev_db.py`를 스크래치 SQLite 파일에 직접 실행해 end-to-end insert도 확인함(100 Transactions / 194 LedgerEntries / 415 CardLedgerEntries).

## 2026-07-14 추가사항 — `backend_local` 스키마 변경(계좌번호/은행명/canonical balance) 반영

`backend_local` 브랜치가 독립적으로 진행한 계좌계 리팩터링(`bank_name`/`account_number` 필드 추가, `BalanceSnapshot` 제거하고 `Account.balance`를 canonical 컬럼으로 전환)을 `card-service`에 merge하면서, 위 CardProduct/mock 거래내역 작업을 새 스키마에 맞게 재구성.

**바뀐 것**

- `MOCK_ACCOUNTS` / `MOCK_BILLER_ACCOUNTS` / `MOCK_EXTERNAL_SOURCE_ACCOUNTS` 각 row에 고정 `account_number` 추가(예: `110-001-000001`) — 모델 기본값(`_generate_account_number()`)이 랜덤이라 그대로 두면 mock 데이터의 "재실행해도 동일값" 결정론이 깨지기 때문. `bank_name`은 전 계좌 공통 상수 기본값(`BANK_NAME = "KDT은행"`)이라 그대로 둠.
- `_build_transaction_dataset()`가 이제 4번째 값으로 `MOCK_FINAL_BALANCES`(계좌별 최종 잔액 dict)도 리턴 — 전역 시간순 이벤트 워크가 끝난 시점의 각 계좌 잔액을 그대로 뽑아씀(수기 계산 아님).
- `make_account_rows()` / `make_biller_account_rows()` / `make_external_source_account_rows()`가 `Account(**d, balance=MOCK_FINAL_BALANCES.get(...))`로 `balance` 필드를 함께 채움 — `Account.balance`가 canonical해져서(`SUM(CREDIT)-SUM(DEBIT)`와 항상 일치해야 함, models.py `Account.balance` 독스트링 참고) 기본값 0으로 두면 실제 거래내역과 안 맞는 깨진 계좌가 되기 때문.
- 외부입금원 계좌(`acct-b099`)는 급여 등 오직 DEBIT만 발생시키므로 balance가 크게 음수(-5천만원대) — 시스템 밖에서 돈이 들어오는 것을 표현하는 placeholder라 정상.
- `BalanceSnapshot` 관련 코드는 애초에 mock_data.py에서 쓴 적 없어서 별도 정리 불필요.

**검증**: `uv run pytest tests/ -q` → 248 passed (기존 251 - `BalanceSnapshot` 제거로 없어진 테스트 3개 반영). `scripts/seed_dev_db.py` 재실행 end-to-end 확인.

## 2026-07-14 추가사항 — CardLedgerEntry.merchant_name / Account.alias

카드결제(`card_ledger_entries`)에 가맹점명이 전혀 없어서 mock 데이터만 봐서는 "얼마"만 알 수 있고 "어디서 썼는지" 알 수 없던 문제 해결.

- `CardLedgerEntry.merchant_name` (nullable) — 카테고리별 가맹점명 풀(외식/마트-편의점/쇼핑/여행/배달/교통/취미)에서 계좌·월별 시드 `random.Random`으로 결정론적 선택. 실API(`POST /cards/{id}/charges`)는 `amount`만 받아서 가맹점 정보를 채울 방법이 없으므로 nullable — 기존 흐름 안 깨짐.
- `Account.alias` (nullable) — 계좌 별칭. 유저 계좌는 "김지훈 생활비통장" 같은 표시용 닉네임, biller 계좌는 "통신비·구독료 자동납부" 같은 용도 라벨(간접적으로 일반결제가 뭔지 알려주는 역할도 겸함).
- `mock_data.py`의 카드결제 이벤트 생성부를 `add_transfer`/`add_card` 헬퍼 호출로 통일(기존 raw `events.append` 6-tuple 코드를 정리하면서 `merchant_name` 필드도 같이 실어나름).

## 2026-07-14 추가사항 — DB 경로 고정 + Alembic 도입

**계기**: `sqlite:///./financial.db`처럼 상대경로로 DB URL을 설정해놔서, 서버를 repo root에서 띄우는지 `mock-financial-service/` 안에서 띄우는지에 따라 `financial.db`가 서로 다른 위치에 두 개 생기는 문제 있었음. 또한 스키마(`models.py`) 바뀔 때마다 로컬 `financial.db`를 수동으로 지우고 재시딩해야 했음(`Base.metadata.create_all()`은 없는 테이블만 만들 뿐 기존 테이블의 컬럼 변경은 반영 안 함).

**1) DB 경로 고정** (`database.py`)
`DATABASE_URL`을 `Path(__file__).resolve()` 기준 절대경로로 계산 — 어디서 서버를 띄우든 항상 `mock-financial-service/financial.db` 하나로 고정됨. `DATABASE_URL` 환경변수로 덮어쓰기 가능(Postgres 전환 시 등).

**2) Alembic 도입** (`alembic.ini`, `alembic_migrations/`)
- 디렉터리명은 `alembic`이 아니라 **`alembic_migrations`** — `alembic`이라는 이름의 디렉터리가 sys.path에 걸리면(예: `mock-financial-service/`가 cwd일 때) 설치된 `alembic` pip 패키지 자체를 가려버려서(`from alembic import command` 깨짐) 이름을 바꿈.
- `alembic_migrations/env.py`가 `financial_service.models`를 import해서 `Base.metadata`를 채우고, `financial_service.database.DATABASE_URL`을 기본 접속 URL로 사용(단, 호출자가 URL을 이미 지정했으면 덮어쓰지 않음 — `scripts/seed_dev_db.py`가 다른 SQLite 파일을 대상으로 할 때 활용).
- `alembic/versions/06e94753818a_baseline_schema.py` — 현재 `models.py`와 완전히 일치하는 baseline migration. `uv run alembic check` → "No new upgrade operations detected"로 확인함.
- `pyproject.toml`(root)에 `alembic_migrations/versions/`를 ruff 검사 대상에서 제외 — 자동생성 코드라 손대지 않음.

**3) 서버 시작 시 자동 마이그레이션** (`app.py`, `migration_runtime.py`)
`app.py`의 startup hook이 `Base.metadata.create_all()` 대신 `migration_runtime.run_migrations()`(=`alembic upgrade head`)를 호출하도록 변경. **서버를 껐다 켜기만 하면** 로컬 DB가 최신 스키마로 자동 동기화됨 — 기존 데이터는 안 지워짐(팀원이 제안한 `drop_all()+create_all()` "초기화" 방식과 달리, alembic은 "변경"만 적용). `scripts/seed_dev_db.py`도 동일하게 `run_migrations()`를 쓰도록 변경해서, 이 스크립트로 만든 DB에도 `alembic_version`이 찍혀 나중에 서버가 떠도 "테이블 이미 존재" 충돌이 안 남 (단, `sqlite:///:memory:` 대상일 때는 alembic이 별도 커넥션을 열어서 in-memory DB가 공유가 안 되므로 `create_all()`로 폴백).

**앞으로 스키마 바꿀 때**: `models.py` 수정 후 `uv run alembic revision --autogenerate -m "설명"`으로 migration 파일 생성 → 커밋에 포함. 서버 재시작하면 자동 적용됨.

**검증**: `uv run pytest tests/ -q` → 248 passed. `uv run alembic check` → 변경 없음 확인. 서버 startup 시뮬레이션(`app.router.lifespan_context`)으로 실제 alembic 마이그레이션 동작 확인, 재시작 시뮬레이션으로 기존 데이터(계좌 13/거래 100/카드결제 415) 보존 확인.

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
