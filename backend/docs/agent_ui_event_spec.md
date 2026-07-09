# Agent → UI 이벤트 명세 (SSE Generative UI Contract)

> **대상 독자**: Agent 서버 개발자

> **목적**: 웹훅 호출만으로 프론트(assistant-ui chat) 화면에 카드/폼/진행표시를 렌더링한다.

> **상태**: `status/token/tool_call/need_approval/done/error` **구현됨**.

> `component` 시그널 + `balance/spending/transactions/budget/cards` 카드 및 UI Data API **구현됨**(Phase 5-D).
> `account_detail` 카드는 미구현(계약만 존재).

---

## 1. 아키텍처

```
Agent  ──POST /api/v1/webhooks/agent──▶  Backend
                                          │  XADD agent:stream:{chat_session_id}
                                          ▼
                                      Redis Stream (6380)
                                          │  XREAD BLOCK
                                          ▼
                        Backend  ──SSE /api/v1/sse/connect──▶  FE(zustand + assistant-ui)
```

- Agent 는 **실시간 프로토콜 불필요**. 단계마다 일반 HTTP POST(웹훅) 한 번씩 쏘면 된다.
- 하나의 대화 턴 = 하나의 `chat_session_id`. FE 가 `/chat` 으로 먼저 만들고 Agent 에 전달한다
  (Agent 연동 시 백엔드가 `chat_session_id` 를 Agent 호출에 넘길 예정).

---

## 2. 웹훅 엔드포인트

```
POST /api/v1/webhooks/agent
Header: X-Agent-Secret: <AGENT_WEBHOOK_SECRET>
Content-Type: application/json
```

### 공통 페이로드 (`AgentWebhookPayload`)

| 필드              | 타입   | 필수   | 설명                           |
| ----------------- | ------ | ------ | ------------------------------ |
| `chat_session_id` | UUID   | ✅     | 렌더 대상 대화 세션            |
| `event_type`      | enum   | ✅     | 아래 §3                        |
| `content`         | string | ✅     | 사람이 읽는 텍스트/접근성 라벨 |
| `approval_id`     | string | ⛔/✅  | `need_approval` 일 때 필수     |
| `metadata`        | object | 상황별 | 컴포넌트/데이터 페이로드       |

한 턴 안에서 여러 번 호출한다(진행 상황을 순차 XADD). 순서는 XADD 순서대로 FE 에 도착한다.

---

## 3. 이벤트 타입

| `event_type`    | 의도                      | FE 렌더                            |
| --------------- | ------------------------- | ---------------------------------- |
| `status`        | 진행 상태 문구            | "진행 상황" 접이식 블록에 누적     |
| `token`         | LLM 토큰 스트리밍         | assistant 텍스트 버블에 append     |
| `tool_call`     | 도구 호출 진행 표시       | 렌치 칩("계좌 조회 중…")           |
| `component`     | **읽기전용 UI 카드 렌더** | 카드(잔액/소비/거래내역/예산/카드) |
| `need_approval` | **HITL: 편집·확인 폼**    | 편집 가능한 confirm 폼 + 승인/거절 |
| `done`          | 턴 종료                   | assistant 메시지 확정, `[DONE]`    |
| `error`         | 오류                      | 에러 텍스트                        |

- **읽기전용 데이터** → `component`
- **사용자 입력/확인 필요(HITL·빈 정보 채우기)** → `need_approval`
- `done` 을 보내면 그 턴의 스트림이 닫힌다. **`need_approval` 뒤에는 `done` 을 보내지 말 것**
  (사용자 응답 대기 → `/agent/approve` 이후 후속 이벤트 → 그때 `done`).

---

## 4. `component` — 읽기전용 카드 (렌더 시그널만)

> **핵심(ADR-002)**: `component` 이벤트는 **데이터를 싣지 않는다.** "무엇을 그릴지"만 알린다.
> 실제 데이터는 FE 가 아래 **UI Data API** 로 직접 조회한다(tanstack query 캐싱). Agent 는 데이터 소유 불필요.

```jsonc
{
  "chat_session_id": "…",
  "event_type": "component",
  "content": "총 자산을 불러왔어요", // 폴백/접근성 텍스트
  "metadata": {
    "component": "balance", // FE 컴포넌트 레지스트리 키
    "params": {}            // (선택) 조회 파라미터. 예: account_detail → { "account_id": 1 }
  }
}
```

FE 레지스트리 키 → 컴포넌트/조회 엔드포인트:

| `component` | 렌더 | UI Data API (FE→BE, Bearer) | params |
|-------------|------|------------------------------|--------|
| `balance` | 자산 현황 | `GET /api/v1/ui/balance` | — |
| `account_detail` | 계좌 상세 | `GET /api/v1/ui/account/{account_id}` | `account_id` |
| `spending` | 소비 분석 | `GET /api/v1/ui/spending` | — |
| `transactions` | 거래 내역 | `GET /api/v1/ui/transactions` | `month?` |
| `budget` | 예산 현황 | `GET /api/v1/ui/budget` | — |
| `cards` | 카드 관리 | `GET /api/v1/ui/cards` | — |

---

## 4b. UI Data API 응답 스키마 (BE → FE)

> Agent 가 아니라 **BE(정보계/BFF)** 가 제공한다. Agent 개발자는 참고만. BE 는 postgres/redis/
> mock-financial-service 에서 조회해 아래 view model 로 반환한다(현재 D단계는 목 픽스처).

### 4b.1 `GET /ui/balance` — 내 자산 현황

```json
{
  "component": "balance",
  "data": {
    "total": 12850000,
    "accounts": [
      {
        "id": 1,
        "bank": "신한은행",
        "alias": "입출금통장",
        "tail": "4200",
        "balance": 8200000,
        "color": "#0052A3"
      },
      {
        "id": 2,
        "bank": "카카오뱅크",
        "alias": "세이프박스",
        "tail": "1234",
        "balance": 4650000,
        "color": "#FAE100"
      }
    ]
  }
}
```

### 4.2 `account_detail` — 계좌 상세

```json
{
  "component": "account_detail",
  "data": {
    "account": {
      "bank": "신한은행",
      "alias": "입출금통장",
      "tail": "4200",
      "balance": 8200000
    },
    "recent": [
      {
        "name": "급여 입금",
        "emoji": "💰",
        "date": "06.25 09:00",
        "amount": 3200000,
        "type": "in"
      },
      {
        "name": "월세 이서연",
        "emoji": "🏠",
        "date": "06.01 09:00",
        "amount": -550000,
        "type": "out"
      }
    ]
  }
}
```

### 4.3 `spending` — 소비 분석

```json
{
  "component": "spending",
  "data": {
    "pie": [
      { "name": "식비", "value": 38, "color": "#2DD4BF", "amount": 474000 }
    ],
    "bar": [
      {
        "name": "식비",
        "change": 12,
        "prev": 406714,
        "curr": 455520,
        "added": [{ "name": "배달의민족", "amount": 28500 }],
        "removed": [{ "name": "CU 편의점", "amount": 8000 }]
      }
    ],
    "monthly": [{ "month": "6월", "amount": 1247000 }],
    "catTx": {
      "식비": [{ "name": "스타벅스", "date": "06.28", "amount": 7500 }]
    }
  }
}
```

### 4.4 `transactions` — 거래 내역

```json
{
  "component": "transactions",
  "data": {
    "months": ["2025-06", "2025-05"],
    "items": [
      {
        "id": 601,
        "name": "급여 입금",
        "emoji": "💰",
        "date": "06.25 09:00",
        "month": "2025-06",
        "day": 25,
        "amount": 3200000,
        "type": "in",
        "category": "수입"
      }
    ]
  }
}
```

### 4.5 `budget` — 예산 현황

```json
{
  "component": "budget",
  "data": {
    "budgetItems": [{ "cat": "식비", "used": 400000, "total": 500000 }],
    "subItems": [{ "name": "Netflix", "amount": 13900, "active": true }]
  }
}
```

### 4.6 `cards` — 카드 관리

```json
{
  "component": "cards",
  "data": {
    "cards": [
      {
        "name": "신한 Deep Dream",
        "num": "5412 3456 7890 1234",
        "exp": "11/27",
        "bg": "linear-gradient(135deg,#0F1E3D 0%,#1a3a6b 60%,#2DD4BF 100%)"
      }
    ]
  }
}
```

---

## 5. `need_approval` — HITL 편집·확인 폼

정보가 다 채워졌을 때의 확인창, 그리고 **빈 정보 채우기**(누락 필드) 둘 다 이 이벤트로 처리한다.
`args` 는 프리필 값이며 사용자가 각 항목을 수정할 수 있다.

```jsonc
{
  "chat_session_id": "…",
  "event_type": "need_approval",
  "content": "아래 정보로 송금할까요? 각 항목을 확인하고 수정할 수 있어요.",
  "approval_id": "appv_abc123", // 필수: 응답 매칭 키
  "metadata": {
    "component": "transfer", // confirm 폼 종류
    "args": {
      // 프리필(빈 값이면 사용자가 채움)
      "name": "김철수",
      "bank": "하나은행",
      "account": "110-123-456789",
      "amount": "30000",
      "time": "지금 바로",
    },
  },
}
```

지원 `component`: `transfer`(송금), `autotransfer`(자동이체). 빈 정보 채우기는 `args` 의 해당 필드를
비워서 보내면 된다(예: `"account": ""`).

### 5.1 사용자 응답 (FE → Backend)

FE 가 사용자의 편집·결정을 아래로 보낸다. Agent 는 이 결과로 워크플로우를 재개한다.

```
POST /api/v1/agent/approve
{
  "chat_session_id": "…",
  "approval_id": "appv_abc123",
  "decision": "approve" | "reject",
  "args": { …사용자가 수정한 값… }          // approve 시
}
```

이후 Agent 는 다시 웹훅으로 `status/tool_call/…/done` 을 쏴서 결과를 렌더링한다.

---

## 6. 한 턴의 전형적 시퀀스

**읽기전용 조회("잔액 알려줘")**

```
status("조회 중…") → component(balance) → done("총 자산은 …원이에요")
```

**송금(HITL)**

```
status("정보 확인 중…") → tool_call("계좌 조회 중…") → need_approval(transfer, args)
   ⟶ [사용자 편집 후 approve] ⟶ POST /agent/approve
status("송금 처리 중…") → tool_call("송금 실행") → done("보냈어요 ✓")
```

**빈 정보 채우기**

```
need_approval(transfer, args={account:""}) ⟶ [사용자가 계좌 입력·approve] ⟶ done
```

---

## 7. 대기 UX

Agent 응답이 없는 idle 구간에는 FE 가 "🤖 Agent가 생각 중입니다…" 인디케이터를 자동 표시한다.
Agent 는 별도 처리 불필요 — 다음 이벤트(`status` 등)를 보내면 사라진다. 다만 장시간 작업 시
중간중간 `status` 를 쏴 주면 UX 가 매끄럽다.

---

## 8. 빠른 시작 (curl)

```bash
# 잔액 카드 렌더 (chat_session_id 는 /chat 응답 또는 /sse/ticket 응답에서 획득)
curl -s -X POST http://localhost:8000/api/v1/webhooks/agent \
  -H "X-Agent-Secret: $AGENT_WEBHOOK_SECRET" -H "Content-Type: application/json" \
  -d '{
    "chat_session_id": "'"$CSID"'",
    "event_type": "component",
    "content": "총 자산 12,850,000원",
    "metadata": { "component": "balance", "data": {
      "total": 12850000,
      "accounts": [{ "id":1, "bank":"신한은행", "alias":"입출금통장", "tail":"4200", "balance":8200000, "color":"#0052A3" }]
    }}
  }'

# 턴 종료
curl -s -X POST http://localhost:8000/api/v1/webhooks/agent \
  -H "X-Agent-Secret: $AGENT_WEBHOOK_SECRET" -H "Content-Type: application/json" \
  -d '{ "chat_session_id":"'"$CSID"'", "event_type":"done", "content":"총 자산은 1,285만원이에요." }'
```

---

## 9. 규칙 요약 (체크리스트)

- [ ] 한 턴은 반드시 `done`(또는 `need_approval`→대기) 로 끝낸다.
- [ ] `need_approval` 뒤에 `done` 을 보내지 않는다(승인 대기).
- [ ] `component`/`need_approval` 의 `metadata.component` 는 §4/§5 레지스트리 키만 사용.
- [ ] `data`/`args` 는 스키마 필드명을 그대로 지킨다(FE 가 그대로 렌더).
- [ ] 금액은 숫자(원 단위 정수), 문자열 금액은 `args`(폼 입력)에서만 허용.

## 10. 버전

- v0.1 (2026-07-08) — 최초 명세. `component` 이벤트/스키마는 Phase 5-D 에서 FE 구현.
- v0.2 (2026-07-09) — `balance/spending/transactions/budget/cards` 카드 + UI Data API
  (`GET /ui/{spending,transactions,budget,cards}`) 구현. mock 드라이버 키워드 매칭 확장.
