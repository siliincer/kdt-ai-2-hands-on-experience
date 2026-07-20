# TODO(계정계) 해소 작업 기록

## 요청 배경

PR #29(`feat/connect_fe_be_agent`, backend Agent Tool API 14종 구현) 리뷰 요청 사항 마지막 항목:

> TODO(계정계)로 주석을 남겨서 계정계 추가 작업하실 것들 표시해놨습니다.

backend 코드베이스에 남아있던 `TODO(계정계)` 주석 처리

## 구현 완료 6건

| # | backend TODO 위치 | 해소 내용 | mock-financial-service 변경 |
|---|---|---|---|
| 1 | `repository/account_repository.py:105` | 계좌번호 기반 조회 API | `GET /accounts/by-number/{account_number}` |
| 2 | `services/recipient_candidate_service.py:5` | 계좌번호+예금주명 조회 API | 위와 동일 엔드포인트로 해소 |
| 3 | `services/agent_tools/setting_service.py:11` | alias 수정 write endpoint | `PATCH /accounts/{account_id}/alias` |
| 4 | `services/agent_tools/recipient_service.py:11` | 거래 이력 상대방 정보 | `LedgerEntryResponse`에 `counterparty_account_id`/`counterparty_account_number`/`counterparty_owner` 추가 |
| 5 | `services/agent_tools/transaction_service.py:127` | transfer 타입 구분 | 같은 응답에 `transaction_type`(`TRANSFER`\|`CARD_SETTLEMENT`) 추가 |
| 6 | `services/agent_tools/transaction_service.py:41` | `/ledger` 기간 필터 | `/api/v1/accounts/{id}/transactions`, `/api/v1/analytics/accounts/{id}/ledger`에 `start_date`/`end_date` 쿼리 파라미터 |
| — | `services/agent_tools/transfer_service.py:114` | 사용자(계좌) 기준 일일 이체 합계 API | `GET /api/v1/analytics/accounts/{id}/transfers/daily-total` (신규) |

### 스키마 변경

DB 마이그레이션 없음. 전부 기존에 있던 컬럼(`accounts.alias`)이나 관계(`transactions.sender_account_id`/`receiver_account_id`)를 재사용:

- `models.py`: `Transaction.sender_account`/`receiver_account` ORM relationship 추가(컬럼 아님, `foreign_keys=` 로 모호성 해소)
- `schemas.py`: `AccountResponse.alias`, `LedgerEntryResponse` 확장, `AccountAliasUpdate`/`DailyTransferredResponse` 신규
- `crud.py`: `get_ledger_entries()` 에 `start_date`/`end_date` + `joinedload` eager-fetch, `update_account_alias()`, `get_daily_transferred_amount()`, `ledger_entry_counterparty_fields()` 신규
- `routers.py`(계정계, 5→7 엔드포인트), `analytics_router.py`(정보계, GET 4→5 엔드포인트)

### 작업 중 발견/수정한 버그

계좌 개설 시 초기입금이 `sender_account_id == receiver_account_id`(자기 자신)인 합성(seed) `Transaction`으로 모델링되어 있음(`crud._create_seed_transaction`). 최초 구현 시 이 seed 거래가:

1. 일일 이체 합계에 "보낸 돈"으로 잘못 합산됨 (예: 초기입금 100,000 + 실제 송금 30,000 = 130,000으로 집계, 정답은 30,000)
2. 상대방 정보 조회 시 counterparty가 "자기 자신"으로 표시됨

`get_daily_transferred_amount()`에 `sender_account_id != receiver_account_id` 조건 추가, `ledger_entry_counterparty_fields()`에 self-seed 판별 후 `counterparty_*` 필드를 `null` 반환하도록 수정.



### 문서 동기화

- `docs/api-reference.md`: 신규 엔드포인트 5개 반영, 엔드포인트 목록 표·필드 설명 갱신
- `docs/ledger-schema.md` §8: 계정계/정보계 엔드포인트 수 갱신 (5개→7개 / GET 4개→5개)




---

## 거래 상호명·카테고리 (소비 분석용)

실제 은행 시스템엔 없는 개념이지만, mock 장부로 **소비 분석**을 하려면 필요하다는 방향 확정에 따라 구현. 카드결제(`CardLedgerEntry`)에만 적용 — 계좌이체는 기존 `LedgerEntryResponse.counterparty_owner`(상대 계좌 owner 이름)를 상호명으로 그대로 쓴다(신규 컬럼 없음).

### 설계 결정

1. **category는 `CardLedgerEntry`에만 붙는다 — `Transaction`/`LedgerEntry`(계좌 원장)엔 안 붙음.**
   이유: `crud.settle_card()`는 카드의 미정산 `card_ledger_entries`(가맹점별로 다를 수 있음) 전체를
   합산해 **단일** `Transaction` + DEBIT `LedgerEntry` 1건으로 묶는다. 정산 단위 ≠ 소비 단위라서
   가맹점별 카테고리는 정산 레벨엔 의미 있게 붙일 수 없고, 결제 시점 단위인 `CardLedgerEntry`에만
   붙는다. 소비분석은 카드와 계좌를 합산해서 보면 될것.
2. ** 상호명은 신규 컬럼 없이 `counterparty_owner` 재사용.** 개인간 송금은 수취인, 결제는 그자리 자체가
   상호명 역할을 한다.
3. **가맹점→카테고리 매핑은 `financial_service/merchant_catalog.py`가 단일 출처.** 고정
   매핑(외식/마트-편의점/쇼핑/여행/배달/교통/취미-문화) — `mock_data.py`의 시드 데이터와 향후
   실 API 경로가 모두 같은 매핑을 참조해 drift를 막는다.
4. **소비분석 제안**: 계좌 원장(`transaction_type=TRANSFER`인 행의 `counterparty_owner`를
   상호명으로) + 카드 원장(`CardLedgerEntry.merchant_name`/`category`)을 합산하되, 계좌 원장에서
   `transaction_type=CARD_SETTLEMENT`인 행은 **반드시 제외**한다 — 같은 지출이 카드 원장에 이미
   가맹점별로 잡혀 있으므로 포함하면 이중계산된다.

### 구현

| 항목 | 내용 |
|------|------|
| 가맹점 카탈로그 | `merchant_catalog.py` 신규 — `MERCHANTS_BY_CATEGORY`, `MERCHANT_CATEGORY`(역인덱스), `category_for_merchant()` |
| DB 컬럼 | `card_ledger_entries.category` 추가 (nullable, `merchant_name`과 동일 패턴). Alembic 리비전 `8d934672ae0e` |
| API 응답 | `CardLedgerEntryResponse`에 `merchant_name`(기존 컬럼, 응답 노출 추가) + `category`(신규) 추가. `GET /analytics/cards/{id}/ledger` |
| mock 데이터 | `mock_data.py`가 `merchant_catalog.MERCHANTS_BY_CATEGORY`를 참조하도록 리팩터, 카드 이벤트마다 `category_for_merchant()`로 category 부여 |