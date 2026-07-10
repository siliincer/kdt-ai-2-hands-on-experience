# 계정계 → 정보계 인계 문서

계정계(core-banking) 서버의 ERD, API, 원장 스키마 확정본. 정보계(analytics/정보계) 팀이
이 서버 데이터를 조회하기 위해 필요한 문서 3종 + 빠른 시작 가이드.

## 문서 목록

| 문서 | 내용 | 언제 보나 |
|------|------|-----------|
| [`ERD.md`](./ERD.md) | 전체 테이블/뷰 관계 다이어그램 (Mermaid) | 스키마 전체 구조 파악할 때 |
| [`ledger-schema.md`](./ledger-schema.md) | 이중기입 원장 설계 원칙 + 왜 이렇게 만들었는지 근거 | "왜 balance 컬럼이 없나", "캐시가 왜 source of truth 아닌가" 궁금할 때 |
| [`api-reference.md`](./api-reference.md) | 정보계 전용 REST API 5개 엔드포인트 상세 스펙 | 실제 연동 코드 짤 때 |

## 빠른 시작 (정보계 개발자용)

정보계는 계정계 데이터를 **두 가지 경로**로 조회 가능 — 상황에 맞게 선택.

### 경로 1 — REST API (원격, 서비스 간 호출)

```
GET /api/v1/analytics/accounts/{account_id}/balance
X-Analytics-Key: analytics-demo-key
```

- 인증: `X-Analytics-Key` 헤더 필수 (현재 데모 상수 `analytics-demo-key` — 프로덕션 전환 시 교체 필요, [`api-reference.md`](./api-reference.md) 인증 섹션 참고).
- 엔드포인트 5개: `balance`, `ledger`, `snapshot`, `reconcile`, `audit-logs`. 상세 스펙/응답 예시는 [`api-reference.md`](./api-reference.md).
- 실시간 값 필요하면 `balance`/`ledger` 사용. 캐시(마지막 새로고침 시점) 값 필요하면 `snapshot` 사용.

### 경로 2 — DB 직접 조회 (배치/집계 작업용)

읽기 전용 뷰 3개 제공 (SQLite/Postgres 공통, `SELECT`만 가능):

| 뷰 | 특징 |
|----|------|
| `v_infobank_account_balances` | 실시간 집계 (호출 시점 SUM 계산) |
| `v_infobank_ledger_entries` | 원장 항목 + 계좌 메타데이터 조인 |
| `v_account_snapshots` | 캐시 조인 (마지막 `POST /accounts/{id}/snapshot` 호출 시점 기준, 아직 스냅샷 없으면 NULL) |

뷰 정의는 [`ERD.md`](./ERD.md) "뷰(View)" 섹션 참고. DB 엔진 레벨 강제(`mode=ro`) 없음 — 컨벤션 기반 read-only이므로 뷰를 통한 접근만 사용하고 원본 테이블 직접 write 금지.

## 정합성 관련 알아둘 것

- 계정계 canonical balance(실시간 SUM)와 정보계가 보는 값(REST API `balance`/뷰 `v_infobank_account_balances`)은 **항상 동일** — 같은 원장에서 계산하므로 (`test_crosspath_equality.py` 로 검증됨).
- 캐시(`snapshot`/`v_account_snapshots`)는 새로고침 시점 기준이라 그 이후 발생한 거래는 반영 안 됨 — stale 가능. 최신값 필요하면 REST `balance`/`ledger` 또는 실시간 뷰 사용.
- 정보계 쪽에서 드리프트(캐시 vs 실제 원장 불일치) 의심되면 `GET .../reconcile` 호출 — 자동 수정은 안 하고 탐지+응답만.

## 변경 이력

원본 seed: `seed_fad3d35b4074` (Ouroboros interview → seed → run → evaluate 파이프라인으로 생성/검증). 6/6 acceptance criteria 충족, 104/104 테스트 통과, Stage 2 semantic evaluation APPROVED (0.85).
