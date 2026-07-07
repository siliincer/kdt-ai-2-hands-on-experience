# Mock Financial Service

실제 금융 API 대신 Fake Money 기반 금융 기능을 제공하는 서비스입니다
(포트 8002, 진입점 `mock_financial_service.main:app`).

> **참고 구현 안내**: 현재 코드는 agent의 `BANK_CLIENT=http` 모드가 실제로
> 동작하도록 만든 **최소 참고 구현**입니다. 시트 API Spec 탭 계약을
> 따르며, 담당자가 자유롭게 확장/재작성해도 됩니다 — agent 쪽 계약 테스트는
> `agent/tests/test_bank_client.py`, 통합 문서는
> `agent/docs/README.md` 4절(은행 API 경계)을 참조하세요.

## 구현된 API (시트 API Spec 탭 기준)

| 메서드 | 경로 | 설명 | 에러 |
|---|---|---|---|
| GET | `/health` | 헬스체크 | — |
| GET | `/api/accounts/{user_id}?account_id=` | 계좌 조회 | 사용자/계좌 없음 404 |
| GET | `/api/recipients?user_id=&recipient_name=` | 수취인 검색 | 무매칭도 200 + 빈 목록 |
| POST | `/api/transactions/transfer-external` | 타인 송금 (원장 실차감) | 404 / 잔액부족 409 / 금액오류 422 |
| POST | `/api/audit-logs` | 감사 로그 기록 | 422 |

시트 대비 이탈 사항 (시트 반영 요청): accounts 응답에
`account_name`/`is_default` 추가, transfer 요청에 `user_id` 추가.

## 실행

```bash
# 레포 루트에서
uv run uvicorn mock_financial_service.main:app --reload --port 8002
uv run pytest mock-financial-service
```

## 예정 작업 (미구현 — 시트 API Spec에 정의됨)

- 거래 내역 조회 (`/api/transactions`)
- 입금/출금 (`/api/transactions/deposit`, `/withdraw`)
- 내 계좌 간 이체 (`/api/transactions/transfer-internal`)
- 자동 저축 규칙 (`/api/savings-rules`)
- 인메모리 원장 → DB 교체
