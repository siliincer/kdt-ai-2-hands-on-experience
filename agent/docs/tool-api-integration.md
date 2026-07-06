# Tool API 연동 설계 — 은행 API 경계와 frontend UI 계약

tool이 인메모리 mock을 직접 읽던 구조를 **API 경계**로 바꾸고, frontend가
카드형 UI를 렌더링할 수 있도록 **구조화 UI 계약**을 추가한 설계 기록이다.
두 계약 모두 시트가 정본이다: **API Spec 탭**(tool→은행 REST), **UI Spec
탭**(ui_type별 화면).

## 1. 아키텍처

```
frontend (useAgentChat)
   │  POST /backendApi/api/v1/agent/chat
   ▼
backend 게이트웨이 (8000)                    ┌────────────────────────┐
   │  POST {AGENT_SERVICE_URL}/chat          │ ChatResponse.ui        │
   ▼                                         │ (confirm_modal 등)     │
agent (8001)                                 └────────────────────────┘
   │  tool ──> BankClient (Protocol)
   │             ├─ LocalBankClient (기본)  ──> 내장 mock 원장
   │             └─ HttpBankClient (compose) ──> mock-financial-service (8002)
   ▼                                              GET /api/accounts/...
LangGraph 워크플로우                              POST /api/transactions/...
```

- **tool은 원장을 직접 만지지 않는다** — 항상 `get_bank_client()` 경유
  (`agent/src/agent/bank_client.py`)
- 전환: `BANK_CLIENT=local`(기본, 외부 의존 없음 — 테스트/노트북) /
  `BANK_CLIENT=http`(docker compose가 켬 — 실제 서비스 간 통신)
- 에러 계약: 실패는 `BankClientError` 하나로 통일, tool이 잡아서
  error/failed 라우트로 보낸다 (그래프 크래시 금지). HTTP 구현은
  **GET 404를 빈 목록으로 번역**해 local 모드의 not_found 라우트 의미를
  보존한다

## 2. API Spec 매핑 (tool ↔ 클라이언트 ↔ 엔드포인트)

| 사용하는 tool | BankClient 메서드 | 엔드포인트 (mock-financial-service) |
|---|---|---|
| verify_account, verify_from_account, check_balance, run_pre_execution_guardrail, get_balance(fetch_balance) | `get_accounts(user_id, account_id?)` | `GET /api/accounts/{user_id}` |
| resolve_recipient_input, verify_recipient_account, check_recipient_input | `get_recipients(user_id, recipient_name?)` | `GET /api/recipients` |
| transfer_money | `transfer(user_id, from_account_id, to_recipient_id, amount, memo?)` | `POST /api/transactions/transfer-external` |
| write_audit_log (best-effort — 실패해도 흐름 유지) | `post_audit_log(...)` | `POST /api/audit-logs` |

시트 API Spec 대비 이탈 사항 (**시트 반영 요청**):
1. accounts 응답에 `account_name`, `is_default` 필드 추가 (계좌명 매칭·기본계좌 판단에 필수)
2. transfer 요청 body에 `user_id` 추가 (원장이 user_id 키 구조)
3. deposit / withdraw / transfer-internal / savings-rules / transactions는 미구현 (mock-financial-service README 예정 작업)

## 3. frontend UI 계약 (ChatResponse.ui)

`status: "waiting_input"`일 때 `ui` 필드에 구조화 힌트가 실린다.
**ui가 없으면 reply 텍스트로 렌더링** — 항상 안전한 폴백이 있다.

흐름: tool이 `prompt_ui`(시스템 state 키)를 설정 → input 노드가 interrupt
payload에 `ui`로 실어 보내고 소비 후 클리어 (대화형 tool은 payload에 직접
포함) → `service.run_chat` → `ChatResponse.ui` → backend passthrough →
frontend `AgentChatUi` 타입 (`frontend/src/features/agent_chat/api/types.ts`).

### ui_type별 payload 예시

**account_card_list** — 계좌 카드 선택 (잔액조회는 `multi: true` 복수 선택):
```json
{ "type": "account_card_list", "multi": true,
  "options": [
    {"account_id": "acc_001", "account_name": "입출금통장", "balance": 1250000},
    {"account_id": "acc_002", "account_name": "생활비통장", "balance": 430000}
  ] }
```

**search_select** — 수취인 검색/선택:
```json
{ "type": "search_select",
  "options": [
    {"recipient_id": "rec_001", "name": "김철수", "bank": "국민은행",
     "account_number": "123-456-789012"}
  ] }
```

**number_input** — 금액 입력:
```json
{ "type": "number_input" }
```

**confirm_modal** — 송금 승인 카드:
```json
{ "type": "confirm_modal",
  "display": {"recipient_name": "김철수", "bank": "국민은행",
              "account_number": "123-456-789012",
              "from_account_name": "입출금통장", "amount": 50000},
  "actions": ["송금하기", "취소", "수취인 수정", "금액 수정", "계좌 수정"] }
```
(경고 확인은 `"variant": "warning"` + actions ["확인","취소"])

**auth_request** — 본인 인증 (⚠️ 시트 UI Spec에 없는 타입 — 추가 요청 대상):
```json
{ "type": "auth_request", "methods": ["지문", "Face ID", "비밀번호"],
  "actions": ["인증완료", "취소"] }
```

### frontend 사용 규약

- `actions`의 라벨 문자열을 **그대로 다음 메시지로 회신**하면 된다
  (예: "송금하기" 버튼 클릭 → `mutate({message: "송금하기", thread_id})`).
  agent 파서가 라벨을 인식한다
- `thread_id`는 직전 status가 `waiting_input`일 때만 회송 (기존 규약 동일)
- 개선 여지: actions는 `{label, value}` 구조가 더 견고하다 — 시트 UI Spec
  개선 요청으로 기록

## 4. BANK_CLIENT 전환 방법

```bash
# local (기본) — 외부 의존 없음
uv run uvicorn agent.main:app --port 8001

# http — mock-financial-service와 실통신
uv run uvicorn mock_financial_service.main:app --port 8002 &
BANK_CLIENT=http MOCK_FINANCIAL_SERVICE_URL=http://localhost:8002 \
  uv run uvicorn agent.main:app --port 8001

# docker compose는 agent에 BANK_CLIENT=http를 주입한다 (전체 스택 검증)
docker compose up -d --build
```

- 테스트는 conftest가 `BANK_CLIENT`를 제거해 항상 local (원장 스냅샷 복원)
- HTTP 계약은 `agent/tests/test_bank_client.py`가 httpx.MockTransport로
  네트워크 없이 검증한다 (메서드/경로/파라미터/바디)
- 팩토리는 lru_cache — 런타임에 모드를 바꾸면 `get_bank_client.cache_clear()`

## 5. mock-financial-service (참고 구현)

`mock-financial-service/`에 API Spec 계약대로 FastAPI 참고 구현을 넣었다
(담당 팀원이 자유롭게 확장/재작성 가능 — 서비스 README 참조).
에러 의미론: accounts 404 / recipients 검색형 200 / transfer 404·409·422.

주의 (http 모드 이중 원장): local 원장과 서비스 원장은 각자 시드를 가진
독립 인메모리다. http 모드에서 잔액 변화는 **서비스 원장에만** 반영되며
재시작 시 초기화된다. 검증 완료된 E2E: agent(http) → 송금 완주 →
서비스 원장 1,250,000 → 1,200,000 차감 + 감사 로그 수신.

## 6. 향후 계획

- [ ] frontend가 ui_type별 컴포넌트 렌더링 (FE 팀 — 계약은 3절)
- [ ] 원장의 진짜 주인 결정: mock-financial-service 확장 또는 backend DB
      (어느 쪽이든 agent는 `MOCK_FINANCIAL_SERVICE_URL`만 바꾸면 됨)
- [ ] actions `{label, value}` 구조화 (시트 UI Spec 개선과 함께)
- [ ] audit log 스키마 정식화 (현재 best-effort 전송)
- [ ] 시트 반영 요청: API Spec 이탈 3건(2절), auth_request ui_type(3절)
