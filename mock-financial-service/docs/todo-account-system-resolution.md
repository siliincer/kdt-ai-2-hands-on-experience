# TODO(계정계) 해소 작업 기록

## 요청 배경

PR #29(`feat/connect_fe_be_agent`, backend Agent Tool API 14종 구현) 리뷰 요청 사항 마지막 항목:

> TODO(계정계)로 주석을 남겨서 계정계 추가 작업하실 것들 표시해놨습니다.

backend 코드베이스에 남아있던 `TODO(계정계)` 주석 12건을 전수 조사한 결과, 데이터 소스/스펙이 이미 명확해서 바로 구현 가능한 6건과, 제품 결정(트리거 시점·값 출처)이 먼저 필요해 지금 구현하면 데이터를 지어내는 꼴이 되는 6건으로 나뉨. 이번 작업은 **mock-financial-service에 앞의 6건만 구현**. backend가 이 API를 쓰도록 전환하는 것과 backend TODO 주석 제거는 범위 밖(후속 작업).

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

### 검증

- `uv run pytest`: 264 passed (기존 248 + 신규 `tests/test_todo_resolution_apis.py` 16)
- `uv run ruff check .`: clean
- `uv run pyright src tests`: clean (mock_data.py의 무관한 기존 에러 3건 제외)
- 실제 서버 기동 후 curl로 6개 엔드포인트 수동 검증 완료

### 문서 동기화

- `docs/api-reference.md`: 신규 엔드포인트 5개 반영, 엔드포인트 목록 표·필드 설명 갱신
- `docs/ledger-schema.md` §8: 계정계/정보계 엔드포인트 수 갱신 (5개→7개 / GET 4개→5개)

## 보류 6건 (미구현)

제품 결정이 먼저 필요해서 지금 구현하면 값을 지어내는 꼴이 되는 항목. 코드에 `TODO(계정계)` 주석 그대로 유지, 이번 작업에서 손대지 않음.

| # | backend TODO 위치 | 보류 사유 |
|---|---|---|
| 1 | `services/agent_tools/bank_resolver.py:22` | 다은행 도입 시 fallback 제거 — "도입 시"라는 조건부 요청, 현재 다은행 요구사항 자체가 없음 |
| 2 | `services/agent_tools/balance_reader.py:7` | hold(출금보류)/`available_balance` 분리 — hold를 언제 거는지(트리거 시점) 결정이 없어 컬럼만 추가해봐야 아무도 안 씀 |
| 3 | `services/agent_tools/policy_constants.py:6` | 한도·수수료·hold 정책을 계정계에 반영할지 — 원문 자체가 "반영할지?"인 질문, 확정된 요청 아님 |
| 4 | `services/agent_tools/transaction_service.py:145` | 거래 상호명(title) — 계좌이체엔 원래 상호명 개념 없음, 어디서 받을지(송금 시 메모 필드?) 결정 필요 |
| 5 | `services/agent_tools/transaction_service.py:146` | 거래 카테고리 — 위와 동일, 값 출처·분류 기준 결정 필요 |
| 6 | (파생) | 위 5건 중 hold/정책/상호명/카테고리는 서로 얽혀있어(정책=한도+수수료+hold, 거래표시=상호명+카테고리) 개별이 아니라 묶어서 결정하는 게 나을 수 있음 — 인터뷰에서 확인 |

## 다음 단계

1. **보류 6건 우로보로스 인터뷰** — 이 문서 작성 직후 진행
2. backend가 신규 API 6종을 쓰도록 전환 (fallback 로직 제거)
3. backend `TODO(계정계)` 해소분 12건 주석 제거
