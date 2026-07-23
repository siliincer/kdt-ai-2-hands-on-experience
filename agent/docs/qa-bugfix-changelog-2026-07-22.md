# QA 버그 수정 내역 (2026-07-22)

`agent/docs/qa-workflow-e2e-test-report.md`(전수 테스트 기록) 진행 중 발견해서 실제로 코드까지
고친 버그 8건 정리. 관련된 미커밋 변경분 16개 파일 + 마이그레이션 1개 대상.

## 1. 승인 처리가 실제로는 안 되는데 승인 완료처럼 보임 (가장 심각)

**증상**: 송금·설정변경 승인 모달에서 "승인" 눌러도 다음 단계(추가 인증)에서
"같은 요청을 처리하고 있습니다"/409로 막힘. DB 확인 결과 `confirmations.status`가
계속 `PENDING`으로 남아있었음 — 승인이 실제로 반영 안 된 상태로 다음 단계가 진행됨.

**원인**: agent가 만드는 `confirm_modal` payload에 `purpose` 필드가 없었음. 프론트
`ConfirmModalUI.tsx`는 `purpose` 없으면 기본값 `'setting'`으로 승인 API에 보내는데,
backend `chat_service.py`의 `_CONFIRMATION_COMPONENTS`(`account_alias`/`default_account`/
`external_transfer`/`internal_transfer`)엔 `'setting'`이 없어 승인 커밋 자체가 조용히
스킵됨.

**수정**: `agent/src/agent/workflows/{external_transfer,internal_transfer,set_default_account,set_account_alias}.py`
의 `_confirmation_payload()` 4곳에 `"purpose"` 키 추가(각 workflow에 맞는 값).

## 2. 출금계좌·기본계좌·별칭변경 대상 계좌를 여러 개 선택할 수 있었음

**증상**: 출금할 계좌·기본 계좌·별칭 변경 대상 계좌 선택 화면에서 체크박스처럼 여러
계좌를 동시에 선택할 수 있었음(말이 안 되는 UX — 이 액션들은 계좌 하나만 의미가 있음).

**원인**: `AccountCardListUI.tsx`가 모든 컨텍스트에서 다중 선택(toggle) 하나로만
동작했음. agent 쪽도 실제로는 `account_ids[0]`만 쓰면서 배열 전체를 프론트에
그대로 넘기고 있었음. 반대로 잔액조회·거래내역·기간합계 조회는 여러 계좌 동시조회가
실제 기능이라 다중선택이 맞음 — 컨텍스트 구분이 없던 게 문제.

**수정**:
- `agent`: `balance_inquiry.py`/`transaction_history.py`/`period_amount_summary.py`(조회,
  `"multiple": true`) + `external_transfer.py`/`internal_transfer.py`/`set_default_account.py`/
  `set_account_alias.py`(액션, `"multiple": false`) — `account_card_list` payload 14곳에
  `multiple` 필드 추가
- `frontend`: `types/hitl.ts`에 `AccountCardListArgs.multiple` 추가, `AccountCardListUI.tsx`가
  `multiple:false`면 라디오 버튼처럼 동작(새로 클릭 시 이전 선택 덮어씀), 미지정 시 단일
  선택을 안전한 기본값으로 처리

## 3. 기본계좌 변경 승인 모달에 계좌명이 안 뜸

**증상**: "OO 계좌를 기본 출금 계좌로 설정하시겠어요?" 형태로 계좌 정보가 나와야 하는데
빈 채로 표시됨.

**원인**: agent가 `current_default_account`/`new_default_account` 키로 보내는데
`ConfirmModalUI.tsx`의 default_account 표시 분기는 `account` 키를 읽음 — 이름 불일치로
`if (a.account)`가 항상 거짓이라 아무 것도 안 그려짐.

**수정**: `set_default_account.py`의 `_confirmation_payload()`에 `"account": view.get("new_default_account")`
추가. `ConfirmModalUI.tsx`도 계좌 표시에 별칭(`account_alias`)을 은행명보다 우선 노출하도록 통일.

## 4. 기본계좌 변경 완료 메시지에 계좌명 없이 마스킹 번호만 뜸

**증상**: "기본 계좌 변경 완료" 뒤에 "계좌 110-\*\*\*-000012"만 뜨고 어떤 계좌인지
이름표가 없어 빈 계좌가 기본계좌가 된 것처럼 보임.

**원인**: `SettingResultUI.tsx`가 `account.masked_account_number`만 렌더링하고
`bank_name`/`account_alias`는 무시하고 있었음(데이터엔 이미 있었음).

**수정**: `joinParts(account_alias ?? bank_name, masked_account_number)`로 은행명/별칭도
같이 표시.

## 5. 수취 계좌번호 검증이 대시(-) 유무 때문에 항상 실패

**증상**: 실존하는 계좌번호를 정확히 입력해도 "수취 계좌를 확인할 수 없습니다" 404.

**원인**: 프론트 계좌번호 입력은 숫자만 남기고 전송(`110002000002`)하는데, backend
`accounts.account_number`엔 대시 포함 표기(`110-002-000002`)로 저장돼있고 조회가 정확
일치(`==`)였음.

**수정**: `backend/src/backend/repository/account_repository.py`의 `get_account_by_number()`를
양쪽 다 숫자만 남기고(`regexp_replace`) 비교하도록 변경.

## 6. agent 합성 request_id가 DB 컬럼 길이를 넘어 DB 에러

**증상**: 송금·별칭변경 등에서 `StringDataRightTruncationError`로 승인 단계 실패.

**원인**: agent가 만드는 `req_resume_<32자hex>:<step_id>` 형식 request_id가 step_id가
긴 경우(`prepare_external_transfer` 등) 64자를 넘는데 `financial_audit_logs.request_id`
컬럼이 `VARCHAR(64)`였음.

**수정**: 컬럼을 `VARCHAR(200)`으로 확장하는 마이그레이션 추가
(`backend/migrations/versions/f1a2b3c4d5e6_widen_financial_audit_log_request_id.py`) +
모델 갱신(`backend/src/backend/models/financial_audit_log.py`).

## 7. mock-financial-service(계정계) 송금이 "KDT은행"이 아니면 무조건 거부됨

**증상**: 수취 계좌가 실제로 다른 은행 소속이어도(예: 신한은행) 그 은행명으로 송금
요청하면 항상 `BANK_NOT_SUPPORTED` 거부.

**원인**: `crud.py`가 하드코딩된 상수 `BANK_NAME = "KDT은행"` 하나와만 비교하고 있었음
— 계좌마다 실제로 다른 은행명이 등록돼 있어도 무시함.

**수정**: 요청의 `receiver_bank_name`을 **받는 계좌에 실제 등록된 `bank_name`**과 비교하도록
변경(계좌 조회를 먼저 하고 그 값과 대조). 값이 다르면 새 에러코드
`RECEIVER_BANK_MISMATCH`로 명확히 거부 — "아무 은행이나 통과"가 아니라 "등록된 은행과
일치해야 통과"로 바로잡음.

## 8. mock-financial-service 원장 정합성 버그 — 카드결제 이력 있는 계좌로 송금하면 항상 500

**증상**: 정상적으로 리시드한 직후에도 카드결제 이력이 있는 페르소나 계좌(박서연·최수아 등)로
송금하면 `Balance integrity violation` AssertionError로 500.

**원인**: 시드 데이터 생성기(`mock_data.py`)가 계좌별 초기 잔액(`_STARTING_BALANCE`,
예: 박서연 800만원)을 잔액 dict에 직접 주입만 하고 그에 대응하는 원장 거래(Transaction/
LedgerEntry)는 한 번도 만들지 않았음. 정합성 검증 함수(`_get_balance`)는 원장만 합산하므로
초기 잔액만큼 항상 어긋남(계좌별 gap이 정확히 `_STARTING_BALANCE` 값과 일치하는 것으로 확인).

**수정**: 타임라인 맨 앞에 외부입금원(`acct-b099`, 급여/지인송금과 동일 취급) 발신 "개시 입금"
거래를 명시적으로 추가해 원장에 기록되도록 시뮬레이터 수정. `balance` dict 초기값도
`_STARTING_BALANCE`가 아닌 빈 dict로 바꿔 이중계산 방지. 리시드 후 5개 계좌 전부
`accounts.balance == SUM(ledger_entries)` 일치 확인, 실제 송금 200 성공 확인.

## 검증 요약

- `uv run pytest agent` — 378 passed
- `uv run ruff check` — 전체 통과
- `npm run lint` — 0 warnings, `npm run build` — 성공
- mock-financial-service `pytest` — 248 passed
- 라이브 API 재현으로 각 항목 전/후 동작 직접 확인(redis stream, Postgres 상태 조회 포함)
