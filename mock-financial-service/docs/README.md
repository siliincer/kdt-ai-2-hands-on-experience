# 계정계 → 정보계 인계 문서

계정계(core-banking) 서버의 ERD, API, 원장 스키마 확정본. 정보계(analytics/정보계) 팀이
이 서버 데이터를 조회하기 위해 필요한 문서 3종 + 빠른 시작 가이드.

## 문서 목록

| 문서 | 내용 | 언제 보나 |
|------|------|-----------|
| [`ERD.md`](./ERD.md) | 전체 테이블/뷰 관계 다이어그램 (Mermaid) | 스키마 전체 구조 파악할 때 |
| [`ledger-schema.md`](./ledger-schema.md) | 이중기입 원장 설계 원칙 + 왜 이렇게 만들었는지 근거 | "`Account.balance`가 왜 원장과 원자적으로 갱신되나", "reconcile이 왜 검증 전용인가" 궁금할 때 |
| [`api-reference.md`](./api-reference.md) | 정보계 전용 REST API 4개 엔드포인트 상세 스펙 | 실제 연동 코드 짤 때 |

## 빠른 시작 (정보계 개발자용)

정보계는 계정계 데이터를 **두 가지 경로**로 조회 가능 — 상황에 맞게 선택.

### 경로 1 — REST API (원격, 서비스 간 호출)

```
GET /api/v1/analytics/accounts/{account_id}/balance
X-Analytics-Key: analytics-demo-key
```

- 인증: `X-Analytics-Key` 헤더 필수 (값은 env var `ANALYTICS_API_KEY`로 설정, 미설정 시 로컬 기본값 `analytics-demo-key` — [`api-reference.md`](./api-reference.md) 인증 섹션 참고).
- 엔드포인트 4개: `balance`, `ledger`, `reconcile`, `audit-logs`. 상세 스펙/응답 예시는 [`api-reference.md`](./api-reference.md).
- `balance`는 `Account.balance` 저장 컬럼을 그대로 읽음 — 원장 기록마다 같은 트랜잭션에서 갱신되므로 별도 새로고침/캐시 개념 없음. 정합성 확인이 필요하면 `reconcile` 사용.

### 경로 2 — DB 직접 조회 (배치/집계 작업용)

읽기 전용 뷰 2개 제공 (SQLite/Postgres 공통, `SELECT`만 가능):

| 뷰 | 특징 |
|----|------|
| `v_infobank_account_balances` | 실시간 집계 (호출 시점 SUM 계산) |
| `v_infobank_ledger_entries` | 원장 항목 + 계좌 메타데이터 조인 |

뷰 정의는 [`ERD.md`](./ERD.md) "뷰(View)" 섹션 참고. DB 엔진 레벨 강제(`mode=ro`) 없음 — 컨벤션 기반 read-only이므로 뷰를 통한 접근만 사용하고 원본 테이블 직접 write 금지.

## 정합성 관련 알아둘 것

- 계정계 canonical balance(`Account.balance`, 원장 기록과 같은 DB 트랜잭션에서 갱신)와 정보계가 보는 값(REST API `balance`/뷰 `v_infobank_account_balances`)은 **항상 동일** (`test_crosspath_equality.py` 로 검증됨).
- 별도 캐시/새로고침 단계가 없으므로 stale 상태 자체가 존재하지 않음 — `balance`/`ledger` 모두 항상 최신값.
- 정보계 쪽에서 드리프트(저장된 `balance` vs 원장 재계산 불일치) 의심되면 `GET .../reconcile` 호출 — 자동 수정은 안 하고 탐지+응답만. 정상 흐름에서 drift는 항상 0이며, 0이 아니면 캐시 미갱신이 아니라 버그를 의미.

## 변경 이력

원본 seed: `seed_fad3d35b4074` (Ouroboros interview → seed → run → evaluate 파이프라인으로 생성/검증). 6/6 acceptance criteria 충족, 104/104 테스트 통과, Stage 2 semantic evaluation APPROVED (0.85).
