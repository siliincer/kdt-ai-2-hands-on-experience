# Agent와 Backend 연동 계약

> 상태: 현재 구현을 기준으로 정리한 목표 계약
>
> 대상: Agent, Backend, Frontend 개발자
>
> 목적: Agent가 금융 원장과 Mock Financial Service에 직접 접근하지 않고 Backend를 통해 금융 조회, 검증, 승인, 인증, 실행을 수행하도록 통신 규약과 개발 범위를 확정한다.
>
> 관련 문서:
> - `agent/docs/agent-tools-api-spec.md`: Agent가 Backend에 요구하는 금융 Tool API 계약
> - `agent/docs/agent-ui-hitl-contract.md`: UI Payload, 사용자 입력, 승인·인증 재개 계약
> - `agent/docs/agent-team-integration-implementation-roadmap.md`: Workflow, State, Step과 구현 계획
> - `agent/docs/agent-management-sheet-v3.xlsx`: Workflow와 계약 매핑의 관리 정본

---

## 1. 결론

이 연동은 다음 세 가지 통신 경로로 나눈다.

```text
1. Frontend -> Backend
   사용자 채팅, 사용자 입력, 승인, 인증, UI 데이터 조회

2. Backend -> Agent
   Agent 실행 시작과 중단된 Workflow 재개

3. Agent -> Backend
   진행 이벤트 Webhook 발행과 금융 Tool API 호출
```

`POST /api/v1/webhooks/agent`는 Agent 진행 이벤트를 Redis Stream과 SSE로 중계하는 용도로만 사용한다. 계좌 조회, 송금 사전 검증, 승인 상태 확인, 송금 실행 같은 금융 요청은 별도의 `/api/v1/agent-tools/*` API로 처리한다.

Frontend는 Agent를 직접 호출하지 않는다. Agent도 Frontend에 직접 응답하지 않는다. 사용자에게 보여줄 모든 Agent 응답은 Backend Webhook과 SSE를 통과한다.

---

## 2. 적용 범위와 현재 상태

### 2.1 현재 구현되어 있는 범위

| 구간 | API 또는 방식 | 상태 |
| --- | --- | --- |
| Frontend -> Backend | `POST /api/v1/chat` | 구현됨 |
| Frontend -> Backend | `POST /api/v1/agent/approve` | 구현됨, 현재는 Mock Agent 재개 |
| Frontend -> Backend | `GET /api/v1/sse/ticket` | 구현됨 |
| Frontend -> Backend | `GET /api/v1/sse/connect` | 구현됨 |
| Agent -> Backend | `POST /api/v1/webhooks/agent` | 구현됨 |
| Backend -> Frontend | Redis Stream 기반 SSE 중계 | 구현됨 |
| Frontend -> Backend | `GET /api/v1/ui/balance` | 구현됨, 현재 Mock 데이터 |
| Backend -> Agent | 실행 시작 API 호출 | 미구현, Mock Driver 사용 중 |
| Backend -> Agent | Workflow 재개 API 호출 | 미구현, Mock Driver 사용 중 |
| Agent -> Backend | `/api/v1/agent-tools/*` | 미구현 |
| 승인 Context | 생성, 검증, 만료, 변경 무효화 | 미구현 |
| 추가 인증 Context | 생성, 검증, 만료 | 미구현 |
| 금융 실행 멱등성 | `Idempotency-Key` 저장과 재사용 | 미구현 |

### 2.2 이 문서에서 사용하는 상태 표기

- `현재`: 지금 코드로 호출할 수 있는 계약
- `목표`: Backend와 Agent 연동을 위해 추가해야 하는 계약
- `확장`: Frontend UI와 함께 이후 추가할 계약

Agent는 `목표` 또는 `확장` 상태 API가 Backend에 배포되기 전에 호출하지 않는다.

### 2.3 Webhook 하나로 충분하지 않은 이유

현재 `POST /api/v1/webhooks/agent`는 Agent가 만든 이벤트를 Frontend로 전달하기 위한 단방향 이벤트 수신 API다.

현재 Backend Handler의 동작은 다음과 같다.

```text
1. X-Agent-Secret 검증
2. AgentWebhookPayload 검증
3. Payload를 AgentStreamEvent로 변환
4. agent:stream:{chat_session_id} Redis Stream에 XADD
5. Redis message_id 반환
```

Webhook이 반환하는 값은 금융 조회나 실행 결과가 아니다.

```json
{
  "success": true,
  "message": "Agent 이벤트가 스트림에 발행되었습니다.",
  "data": {
    "message_id": "1720843200000-0"
  }
}
```

따라서 현재 Webhook으로 처리할 수 있는 범위는 다음과 같다.

| 처리 가능 | 예시 |
| --- | --- |
| 진행 상태 전달 | `status` |
| 답변 내용 전달 | `token` |
| Tool 실행 중 표시 | `tool_call` |
| 읽기 UI 렌더 신호 | `component` |
| 사용자 승인 요청 | `need_approval` |
| 실행 완료와 오류 전달 | `done`, `error` |

반면 다음 요청은 현재 Webhook으로 처리할 수 없다.

| 처리 불가 | Agent에 필요한 응답 |
| --- | --- |
| 사용자 계좌 조회 | 계좌 ID와 마스킹 계좌정보 |
| 출금 가능 잔액 조회 | 현재 출금 가능 금액 |
| 최근 수취인 조회 | 수취인 ID와 마스킹 정보 |
| 신규 수취 계좌 검증 | `to_recipient_candidate_id`와 검증 결과 |
| 송금 사전 검증 | `confirmation_id`, 정책 결과, 추가 인증 필요 여부 |
| 송금 실행 | `transaction_id`와 실행 결과 |
| 설정 변경 | 변경 결과와 변경된 설정 참조값 |

#### 이유 1. Webhook 응답은 금융 결과가 아니다

Agent Tool은 다음 Step을 결정하기 위해 Backend의 처리 결과를 즉시 받아야 한다.

```text
Agent -> Backend 잔액 조회
Backend -> Agent available_balance 반환
Agent -> sufficient 또는 insufficient Route 선택
```

현재 Webhook은 Payload를 Redis Stream에 저장한 뒤 `message_id`만 반환하므로 Agent가 잔액, 수취인 검증 결과, 송금 결과를 받을 수 없다.

#### 이유 2. Webhook의 `metadata`는 금융 요청 계약이 아니다

기술적으로는 `metadata`에 다음과 같은 값을 넣을 수 있다.

```json
{
  "metadata": {
    "account_id": "acc_001",
    "amount": 50000
  }
}
```

하지만 현재 Handler는 `metadata`를 해석해 계좌 Service나 송금 Service를 호출하지 않는다. 데이터는 그대로 Redis Stream에 들어가 Frontend SSE로 전달될 뿐이다.

또한 자유 형식 `dict` 하나로 금융 요청을 처리하면 다음 계약을 강제하기 어렵다.

- Tool별 필수 필드와 타입
- 계좌 소유권 검증
- 조회 기간과 페이지 크기 제한
- Confirmation과 Auth Context 검증
- `Idempotency-Key`
- 실행 전후 Transaction
- Tool별 성공 응답과 표준 오류 코드

따라서 `metadata`에 금융 요청을 넣는 것은 Tool API를 구현한 것이 아니다.

#### 이유 3. 이벤트 통보와 요청·응답의 생명주기가 다르다

Webhook은 이미 발생했거나 현재 진행 중인 상태를 통보한다.

```text
계좌를 확인하고 있습니다.
사용자 승인이 필요합니다.
송금이 완료되었습니다.
```

Agent Tool API는 Backend에 작업을 요청하고 그 결과로 Workflow를 분기한다.

```text
이 계좌가 사용자 소유인가?
현재 잔액이 충분한가?
이 Confirmation이 승인 상태인가?
송금 실행이 성공했는가?
```

두 통신을 하나의 Webhook으로 합치면 Backend가 나중에 Agent로 결과를 다시 보내는 Callback과 다음 기능이 추가로 필요하다.

- 요청과 응답을 연결할 상관관계 ID
- Agent의 비동기 대기 상태
- Callback timeout
- 결과 유실과 순서 변경 처리
- 중복 Callback 처리
- Agent 재시작 후 대기 요청 복원
- 송금 성공 여부가 불명확한 경우의 복구

현재 프로젝트는 Agent가 Backend REST API 결과를 바로 받아 LangGraph Route를 결정하는 구조가 더 단순하고 명확하다.

#### 이유 4. 금융 API에는 더 강한 검증이 필요하다

현재 Webhook은 공유 Secret을 검증하지만 다음 금융 Context를 검증하지 않는다.

- `execution_context_id`와 사용자
- `chat_session_id` 소유권
- 요청 계좌의 사용자 소유권
- Agent Tool Scope
- Confirmation 대상과 만료
- 추가 인증 상태와 만료
- 실행 요청 중복 여부
- 실행 직전 잔액과 정책

금융 Tool API는 서비스 인증 외에도 Execution Context, 소유권, 승인, 인증, 멱등성을 Endpoint별로 검증해야 한다.

#### 이유 5. 송금 실행은 Redis 이벤트 발행과 다른 Transaction이다

Webhook의 성공은 Redis Stream에 이벤트가 들어갔다는 뜻이다. 금융 실행 성공을 의미하지 않는다.

```text
Webhook 성공
= Redis XADD 성공

송금 API 성공
= 권한, 승인, 인증, 잔액, 정책 검증 성공
 + 원장 변경 성공
 + 멱등성 결과 저장
 + 금융 감사 로그 기록
```

두 성공의 의미가 다르기 때문에 같은 Endpoint 응답으로 표현하면 안 된다.

#### 같은 파일에 Route를 추가하는 것과 Webhook 하나로 처리하는 것은 다르다

기술적으로 `webhook_api.py` 파일에 여러 Route를 추가할 수는 있다. 하지만 다음 두 문장은 의미가 다르다.

```text
webhook_api.py 파일에 Agent Tool Route도 작성한다.
POST /webhooks/agent 하나로 모든 Tool을 처리한다.
```

첫 번째는 파일 구성의 문제이고, 두 번째는 API 책임의 문제다. 하나의 파일에 작성하더라도 최소한 Endpoint와 Schema는 분리해야 한다.

```text
POST /api/v1/webhooks/agent
  이벤트 전달 전용

GET 또는 POST /api/v1/agent-tools/*
  금융 조회, 검증, 실행 전용
```

다만 계좌, 거래, 수취인, 송금, 설정 API가 늘어나면 인증, Schema, Service, 테스트가 커지므로 `agent_tools` Router를 별도 파일 또는 폴더로 분리하는 것을 권장한다.

#### 최종 결정

```text
Agent -> Backend Webhook
  Frontend에 보여줄 진행 상태와 UI 이벤트 전달
  응답: Redis message_id

Agent -> Backend Tool API
  금융 조회, 검증, Prepare, Execute 요청
  응답: Workflow가 사용할 금융 처리 결과
```

호출 방향은 둘 다 Agent에서 Backend지만, Webhook은 이벤트 통보이고 Agent Tool API는 금융 요청·응답이므로 서로 대체하지 않는다.

---

## 3. 전체 구조

```text
Frontend
  |
  | POST /api/v1/chat
  | POST /api/v1/agent/approve
  | POST /api/v1/agent/input                 확장
  | GET  /api/v1/ui/*
  | GET  /api/v1/sse/ticket, /sse/connect
  v
Backend
  |-- 사용자 인증과 Chat Session 소유권 확인
  |-- Execution Context 생성과 관리
  |-- 사용자 승인과 추가 인증 상태 관리
  |-- 금융 조회, 검증, 실행과 감사 기록
  |-- Redis Stream과 SSE 중계
  |
  | POST /internal/v1/executions
  | POST /internal/v1/executions/{agent_thread_id}/resume
  v
Agent
  |-- 자연어 이해와 Workflow 선택
  |-- Slot 수집과 다음 Step 결정
  |-- Backend Tool API 호출
  |-- UI 렌더 신호와 진행 이벤트 생성
  |
  | POST /api/v1/webhooks/agent
  | /api/v1/agent-tools/*
  v
Backend
  |
  | DB 또는 Mock Financial Service
  v
금융 데이터와 원장
```

Backend가 Agent를 호출하는 API는 Agent Server가 제공하는 내부 API다. `/api/v1/agent-tools/*`와 Webhook은 Backend가 제공하고 Agent가 호출하는 API다.

---

## 4. 책임 분리

### 4.1 Frontend 책임

- Backend에만 사용자 Access Token을 전달한다.
- 사용자 메시지와 선택, 입력, 승인, 거절을 Backend로 보낸다.
- SSE 이벤트를 화면 메시지와 등록된 UI 컴포넌트로 변환한다.
- 읽기 전용 카드 데이터는 Backend의 `/api/v1/ui/*`에서 조회한다.
- 생체인증, PIN 등 추가 인증 UI는 Backend 인증 API와 직접 통신한다.
- Agent 서비스 주소, 서비스 토큰, Agent Webhook Secret을 알지 않는다.

### 4.2 Backend 책임

- Frontend Access Token을 검증하고 사용자를 결정한다.
- `chat_session_id`의 생성과 사용자 소유권을 관리한다.
- `execution_context_id`를 생성하고 사용자, Chat Session, Agent Thread를 연결한다.
- Agent 실행 시작과 재개 요청을 전송한다.
- Agent Tool API마다 사용자 권한과 계좌 소유권을 다시 검증한다.
- Confirmation과 Auth Context의 상태, 만료, 대상 데이터 고정을 관리한다.
- 잔액, 한도, 계좌 상태, 수취인, 정책을 검증하고 금융 실행을 수행한다.
- 실행형 API의 멱등성과 금융 감사 로그를 관리한다.
- Agent Webhook 이벤트의 실행 Context와 Chat Session 일치 여부를 검증한다.
- Redis Stream을 SSE로 Frontend에 중계한다.

### 4.3 Agent 책임

- 사용자 발화에서 Workflow와 Slot을 결정한다.
- 금융 데이터가 필요하면 Backend Tool API만 호출한다.
- Backend가 반환한 참조 ID와 마스킹된 최소 정보만 Workflow State에 저장한다.
- 진행 상태와 UI 렌더 신호를 Webhook으로 Backend에 보낸다.
- `waiting_input` 동기 응답 대신 정해진 SSE 이벤트로 입력 대기를 알린다.
- Backend가 전달한 `chat_session_id`, `execution_context_id`와 내부 `agent_thread_id`의 연결을 유지한다.
- 사용자 승인이나 인증 완료 이벤트만으로 금융 실행 가능 여부를 판단하지 않는다.
- 실행 전 Backend API의 최종 검증 결과를 따른다.

#### 4.3.1 Agent 발신 보장

Agent는 Backend에 요청을 보낼 때 다음을 보장한다.

1. 모든 요청에 Backend가 발급한 `execution_context_id`와 추적 가능한 `request_id`를 포함한다.
2. 사용자 화면에 보낼 진행 상태와 UI 신호는 Webhook으로만 보낸다.
3. 금융 조회와 실행 요청은 허용된 Backend Tool API로만 보낸다.
4. 금융 Tool 요청에는 `user_id`와 Frontend Access Token을 포함하지 않는다.
5. 전체 계좌번호, 인증 원문, 서비스 Secret을 Payload와 로그에 포함하지 않는다.
6. 상태 변경 요청에는 Backend가 발급한 `confirmation_id`를 사용한다.
7. 실행 요청에는 고정된 `Idempotency-Key`를 사용하며 timeout 후 임의의 새 키로 다시 실행하지 않는다.
8. Backend가 반환한 오류 코드를 Workflow 분기에 사용하고 내부 오류를 사용자에게 그대로 전달하지 않는다.
9. `done`을 보낸 실행 턴에는 추가 이벤트를 보내지 않는다.
10. 미배포 상태인 목표 또는 확장 API와 이벤트는 기능 협의와 배포 확인 전까지 보내지 않는다.

### 4.4 Agent가 하지 않는 일

- Frontend Access Token 검증
- DB 직접 접속
- 금융 원장 직접 조회 또는 변경
- Mock Financial Service 직접 호출
- 임의의 `user_id`를 이용한 금융 API 호출
- 승인과 추가 인증의 최종 판정
- 잔액과 이체 한도의 최종 판정
- 금융 감사 로그의 정본 관리

---

## 5. 식별자 규약

| 필드 | 발급 주체 | 저장 주체 | 용도 |
| --- | --- | --- | --- |
| `request_id` | 최초 요청을 받은 서비스 | 양쪽 | 단일 HTTP 요청 추적 |
| `chat_session_id` | Backend | Frontend, Backend, Agent | 대화와 SSE Stream 식별 |
| `execution_context_id` | Backend | Backend, Agent | 사용자와 실행 권한 Context 식별 |
| `agent_thread_id` | Agent | Backend, Agent | LangGraph Checkpointer 식별 |
| `input_request_id` | Agent | Backend, Agent | 일반 사용자 입력 대기와 응답 매칭 |
| `confirmation_id` | Backend | Backend, Agent | 고정된 변경 요청과 사용자 승인 매칭 |
| `auth_context_id` | Backend | Frontend, Backend, Agent | 추가 인증 상태 식별 |
| `transaction_id` | Backend | Backend, Agent | 완료된 금융 실행 식별 |

### 5.1 식별자 사용 원칙

1. Frontend와 SSE의 기본 대화 키는 `chat_session_id`다.
2. Agent 내부 Checkpointer 키는 `agent_thread_id`다.
3. Backend는 `execution_context_id`를 통해 사용자와 두 세션 키를 연결한다.
4. Agent는 Backend Tool API에 `user_id`를 보내지 않는다.
5. 승인 요청과 응답은 별도 `approval_id`를 만들지 않고 Backend가 발급한 `confirmation_id`를 그대로 사용한다.
6. 일반 입력 요청은 승인과 구분하기 위해 `input_request_id`를 사용한다.
7. `preview_id`, `approval_context_id`처럼 같은 Confirmation 생명주기를 나타내는 별도 ID는 만들지 않는다.

Backend가 관리하는 Execution Context 예시는 다음과 같다.

```json
{
  "execution_context_id": "exec_123",
  "user_id": "user_001",
  "chat_session_id": "95bdd0ac-cfa2-44c8-8258-043f0f43fd47",
  "agent_thread_id": "thread_123",
  "scopes": ["account:read", "transfer:request"],
  "status": "active",
  "expires_at": "2026-07-13T13:00:00+09:00"
}
```

`user_id`는 Backend 내부에만 있으며 Agent Tool 요청 본문이나 Header에 포함하지 않는다.

---

## 6. 서비스 간 인증과 공통 Header

Frontend용 Bearer Token과 서비스 간 Token은 분리한다.

### 6.1 Agent -> Backend Webhook

현재 계약을 유지한다.

```http
X-Agent-Secret: <AGENT_WEBHOOK_SECRET>
Content-Type: application/json
X-Request-Id: req_123
X-Execution-Context-Id: exec_123
```

`X-Execution-Context-Id`와 `X-Request-Id`는 Backend 개발 후 필수로 전환한다.

### 6.2 Agent -> Backend Tool API

```http
Authorization: Bearer <AGENT_SERVICE_TOKEN>
X-Execution-Context-Id: exec_123
X-Request-Id: req_456
Content-Type: application/json
```

상태를 변경하는 API에는 다음 Header를 추가한다.

```http
Idempotency-Key: idem_789
```

### 6.3 Backend -> Agent

```http
Authorization: Bearer <BACKEND_SERVICE_TOKEN>
X-Request-Id: req_123
Content-Type: application/json
```

초기 개발 단계에서 하나의 공유 Secret을 재사용할 수는 있지만, Frontend 인증용 Secret과 서비스 간 인증 Secret은 반드시 분리한다. 운영 환경에서는 Secret 회전 또는 mTLS 적용이 가능해야 한다.

---

## 7. Frontend -> Backend 현재 계약

### 7.1 사용자 메시지

```http
POST /api/v1/chat
Authorization: Bearer <frontend-access-token>
Content-Type: application/json
```

```json
{
  "chat_session_id": null,
  "message": "생활비 통장에서 홍길동에게 5만 원 보내줘"
}
```

Backend 응답:

```json
{
  "success": true,
  "message": "메시지가 접수되었습니다.",
  "data": {
    "chat_session_id": "95bdd0ac-cfa2-44c8-8258-043f0f43fd47"
  }
}
```

Backend는 응답 전에 Chat Session을 확정하고 사용자 메시지를 저장한다. Agent 실행은 비동기로 시작하며 진행 상황은 SSE로 보낸다.

### 7.2 사용자 승인과 거절

```http
POST /api/v1/agent/approve
Authorization: Bearer <frontend-access-token>
Content-Type: application/json
```

```json
{
  "chat_session_id": "95bdd0ac-cfa2-44c8-8258-043f0f43fd47",
  "confirmation_id": "confirm_123",
  "decision": "approve"
}
```

현재 Backend는 Chat Session 소유권만 확인한다. 목표 구현에서는 다음을 추가한다.

1. 요청의 `confirmation_id`와 Pending Approval 일치 확인
2. Confirmation 대상 사용자와 Chat Session 확인
3. 만료와 현재 상태 확인
4. `modify` 요청이면 기존 Confirmation 폐기
5. 별도 입력 UI와 Backend 검증을 거쳐 수정된 값으로 Prepare를 다시 수행하고 새로운 `confirmation_id` 발급
6. 승인·수정·취소 상태 저장 후 Agent Workflow 재개

### 7.3 일반 입력 응답

계좌 선택, 수취인 선택, 금액, 기간 입력은 승인과 다른 의미이므로 다음 API를 추가한다.

```http
POST /api/v1/agent/input
Authorization: Bearer <frontend-access-token>
Content-Type: application/json
```

```json
{
  "chat_session_id": "95bdd0ac-cfa2-44c8-8258-043f0f43fd47",
  "input_request_id": "input_123",
  "value": {
    "amount_input_outcome": "submitted",
    "amount": 50000
  }
}
```

Backend는 Chat Session 소유권과 현재 대기 중인 입력을 확인하고 Agent 재개 API로 전달한다.

---

## 8. Backend -> Agent 내부 API 목표 계약

현재 `backend/services/chat_service.py`의 Mock Driver 호출을 Agent HTTP Client 호출로 교체한다.

### 8.1 실행 시작

Agent Server가 다음 API를 제공한다.

```http
POST /internal/v1/executions
Authorization: Bearer <backend-service-token>
```

요청:

```json
{
  "request_id": "req_123",
  "chat_session_id": "95bdd0ac-cfa2-44c8-8258-043f0f43fd47",
  "execution_context_id": "exec_123",
  "message": "생활비 통장에서 홍길동에게 5만 원 보내줘"
}
```

Agent 응답:

```json
{
  "accepted": true,
  "agent_thread_id": "thread_123"
}
```

규칙:

- Agent는 요청을 접수한 뒤 빠르게 `200` 또는 `202`로 반환한다.
- 사용자에게 보여줄 결과를 이 HTTP 응답에 담지 않는다.
- 진행과 최종 결과는 Backend Webhook으로 보낸다.
- Backend는 반환된 `agent_thread_id`를 Execution Context에 연결한다.
- 같은 `request_id`의 중복 시작 요청은 같은 결과를 반환하거나 이미 접수되었다고 응답한다.

### 8.2 Workflow 재개

```http
POST /internal/v1/executions/{agent_thread_id}/resume
Authorization: Bearer <backend-service-token>
```

승인 재개 요청:

```json
{
  "request_id": "req_456",
  "chat_session_id": "95bdd0ac-cfa2-44c8-8258-043f0f43fd47",
  "execution_context_id": "exec_123",
  "resume": {
    "type": "approval",
    "confirmation_id": "confirm_123",
    "decision": "approve"
  }
}
```

일반 입력 재개 요청:

```json
{
  "request_id": "req_457",
  "chat_session_id": "95bdd0ac-cfa2-44c8-8258-043f0f43fd47",
  "execution_context_id": "exec_123",
  "resume": {
    "type": "input",
    "input_request_id": "input_123",
    "value": {
      "amount_input_outcome": "submitted",
      "amount": 50000
    }
  }
}
```

Agent는 다음을 검증한다.

1. Thread가 실제 중단 상태인지
2. `execution_context_id`와 `chat_session_id`가 Thread에 연결되어 있는지
3. 현재 대기 중인 `confirmation_id` 또는 `input_request_id`가 일치하는지
4. Pending Input에 저장된 `ui_contract_id`와 입력 형식이 일치하는지

금융 권한과 Confirmation 유효성은 Backend가 먼저 검증하며, 금융 실행 API에서도 다시 검증한다.

---

## 9. Agent -> Backend Webhook 현재 계약

### 9.1 Endpoint

```http
POST /api/v1/webhooks/agent
X-Agent-Secret: <agent-webhook-secret>
X-Execution-Context-Id: exec_123
X-Request-Id: req_123
Content-Type: application/json
```

### 9.2 공통 Payload

```json
{
  "chat_session_id": "95bdd0ac-cfa2-44c8-8258-043f0f43fd47",
  "event_type": "status",
  "content": "계좌 정보를 확인하고 있어요.",
  "confirmation_id": null,
  "metadata": {}
}
```

현재 허용 이벤트:

```text
status
token
tool_call
component
need_approval
done
error
```

### 9.3 이벤트별 규약

#### `status`

진행 상태를 사람이 읽을 수 있는 문장으로 보낸다.

```json
{
  "event_type": "status",
  "content": "출금 계좌를 확인하고 있어요.",
  "metadata": {
    "step": "resolve_source_account"
  }
}
```

#### `token`

Assistant 텍스트에 이어 붙일 문장 또는 토큰을 보낸다.

```json
{
  "event_type": "token",
  "content": "생활비 통장의 잔액은 ",
  "metadata": null
}
```

#### `tool_call`

Backend Tool 호출 진행 상태를 보낸다. 현재 FE 계약에 따라 `metadata.tool`을 사용한다.

```json
{
  "event_type": "tool_call",
  "content": "잔액을 조회하고 있어요.",
  "metadata": {
    "tool": "fetch_balance"
  }
}
```

#### `component`

읽기 전용 UI 렌더 신호만 보낸다. 금융 데이터 전체를 Payload에 넣지 않는다.

```json
{
  "event_type": "component",
  "content": "자산 현황을 불러왔어요.",
  "metadata": {
    "component": "balance",
    "params": {}
  }
}
```

Frontend는 `metadata.component`에 대응하는 `/api/v1/ui/*` API를 호출한다. 현재 실제 지원 값은 `balance` 하나다. 미등록 Component는 Backend와 Frontend 배포가 완료되기 전에 Agent가 보내지 않는다.

#### `need_approval`

변경 또는 금융 실행에 대한 명시적 승인 요청이다.

```json
{
  "event_type": "need_approval",
  "content": "아래 정보로 송금할까요?",
  "confirmation_id": "confirm_123",
  "metadata": {
    "ui_contract_id": "UI-EXTERNAL-TRANSFER-CONFIRMATION",
    "ui": {
      "type": "confirm_modal",
      "payload": {
        "recipient": {
          "name": "홍*동",
          "bank_name": "하나은행",
          "masked_account_number": "***-***-7890"
        },
        "amount": 50000,
        "currency": "KRW"
      }
    }
  }
}
```

규칙:

- `confirmation_id`는 필수다.
- 금융 실행 확인에서는 Backend가 Prepare API에서 발급한 `confirmation_id`를 사용한다.
- 승인 UI 데이터는 Prepare 응답의 `confirmation_view`를 `metadata.ui.payload`로 전달한다.
- 전체 계좌번호, Access Token, 인증 원문은 Payload에 포함하지 않는다.
- `need_approval` 뒤에는 `done`을 보내지 않는다.
- 사용자의 결정으로 Workflow가 재개된 뒤 후속 이벤트와 `done`을 보낸다.

#### `done`

현재 사용자 턴을 종료한다.

```json
{
  "event_type": "done",
  "content": "송금이 완료되었습니다.",
  "metadata": {
    "transaction_id": "txn_123"
  }
}
```

`done` 이후 같은 실행 턴에 추가 이벤트를 보내지 않는다.

#### `error`

사용자에게 공개 가능한 오류만 보낸다.

```json
{
  "event_type": "error",
  "content": "계좌 정보를 확인하지 못했습니다.",
  "metadata": {
    "error_code": "BACKEND_TEMPORARY_ERROR",
    "retryable": true
  }
}
```

Stack Trace, DB 오류, 내부 URL, Secret은 포함하지 않는다.

### 9.4 Webhook 응답

```json
{
  "success": true,
  "message": "Agent 이벤트가 스트림에 발행되었습니다.",
  "data": {
    "message_id": "1720843200000-0"
  }
}
```

Agent는 `2xx`가 아니거나 네트워크 오류가 발생하면 읽기 전용 이벤트에 한해 제한적으로 재시도할 수 있다. 같은 이벤트를 재시도할 수 있도록 목표 구현에서는 `event_id` 또는 `X-Request-Id` 기반 중복 제거를 추가한다.

---

## 10. 일반 사용자 입력 이벤트 확장

현재 Backend와 Frontend는 승인 UI를 중심으로 구현되어 있다. 목표 계약에서는 계좌·수취인·금액·기간·별칭·선택 입력을 처리하기 위해 `need_input`과 UI 계약 Registry를 지원한다.

일반 입력 요청은 `prompt_for`를 사용하지 않는다. Agent가 발급한 `input_request_id`가 요청 인스턴스를 식별하고, Backend가 Pending Input에 저장한 `ui_contract_id`가 제출값 Schema를 결정한다.

목표 Payload:

```json
{
  "chat_session_id": "95bdd0ac-cfa2-44c8-8258-043f0f43fd47",
  "event_type": "need_input",
  "content": "송금 금액을 입력해 주세요.",
  "metadata": {
    "workflow_id": "wf_external_transfer",
    "step_id": "request_external_transfer_amount",
    "input_request_id": "input_123",
    "ui_contract_id": "UI-TRANSFER-AMOUNT-INPUT",
    "ui": {
      "type": "number_input",
      "payload": {
        "currency": "KRW",
        "min": 1
      }
    }
  }
}
```

지원 목표 UI:

| `ui.type` | 목적 | Backend 검증 후 Resume 값 예시 |
| --- | --- | --- |
| `account_card_list` | 계좌 하나 또는 여러 개 선택 | `{"account_selection_outcome":"selected","account_ids":["acc_001"]}` |
| `recipient_select` | 기존 수취인 선택 또는 신규 계좌 입력·검증 | `{"recipient_selection_outcome":"selected","to_recipient_id":"rcp_001"}` |
| `number_input` | 금액 입력 | `{"amount_input_outcome":"submitted","amount":50000}` |
| `period_input` | 조회 기간 입력 | `{"period_selection_outcome":"selected","start_date":"2026-07-01","end_date":"2026-07-13"}` |
| `text_input` | 계좌 별칭 입력 | `{"alias_input_outcome":"submitted","alias":"여행 자금"}` |
| `option_select` | 합계 유형·수정 대상·재인증 선택 | UI 계약별 Enum 값 |
| `auth_request` | Backend 추가 인증 진행 | `{"auth_status":"verified"}` |

`need_input`은 Backend SSE Schema, Frontend Type, 이벤트 Fold 로직, UI Registry와 `/api/v1/agent/input`이 함께 지원된 이후 사용한다.

### 10.1 `recipient_select`

`recipient_select`는 이름 힌트와 일치하는 기존 거래 수취인 후보, 최근 송금 수취인, 신규 은행·계좌번호 입력을 하나의 UI 계약으로 처리한다. 상세 UI 상태와 Payload는 `agent/docs/agent-ui-hitl-contract.md`를 정본으로 사용한다.

처리 흐름은 다음과 같다.

1. 최초 발화에 `recipient_name_hint`가 있으면 Agent가 `API-RECIPIENT-RESOLVE`를 호출한다.
2. 완료된 기존 타인송금 거래에서 고유 수취인이 정확히 하나면 Backend가 `to_recipient_id`를 반환하며 선택 UI를 생략한다.
3. 동명이인이 여러 명이거나 일치 결과가 없으면 Agent가 `UI-RECIPIENT-SELECT` Webhook을 보내고 중단한다.
4. 이름 힌트가 없으면 Agent는 수취인 자동 확정 API를 호출하지 않고 바로 같은 UI를 요청한다.
5. 이름 후보와 최근 수취인 목록은 Backend와 Frontend가 구성한다. Agent는 이 목록을 조회하거나 State에 저장하지 않는다.
6. Frontend가 입력한 전체 계좌번호는 Backend가 검증하고 `to_recipient_candidate_id`를 발급한다.
7. 검증 실패는 Agent를 재개하지 않고 같은 UI에서 재입력받는다.
8. 최종 선택이 완료된 경우에만 Backend가 검증된 참조로 Agent를 재개한다.

기존 수취인 선택 Resume:

```json
{
  "execution_context_id": "exec_123",
  "resume": {
    "type": "input",
    "input_request_id": "input_recipient_123",
    "value": {
      "recipient_selection_outcome": "selected",
      "to_recipient_id": "rcp_001",
      "to_recipient_candidate_id": null
    }
  }
}
```

신규 계좌 검증 완료 Resume:

```json
{
  "execution_context_id": "exec_123",
  "resume": {
    "type": "input",
    "input_request_id": "input_recipient_123",
    "value": {
      "recipient_selection_outcome": "selected",
      "to_recipient_id": null,
      "to_recipient_candidate_id": "rcp_candidate_001"
    }
  }
}
```

`selected`에서는 두 수취인 참조 중 정확히 하나만 존재해야 한다. 취소는 `recipient_selection_outcome=cancelled`와 두 참조의 null 값으로 재개한다. 전체 계좌번호, 은행 코드, 예금주 검증 원문과 최근 수취인 목록은 Agent State와 Resume Payload에 포함하지 않는다.

---

## 11. Agent -> Backend Tool API 목표 계약

Agent Tool API의 요청·응답 필드, 오류, 멱등성과 Backend 검증 항목은 `agent/docs/agent-tools-api-spec.md`를 정본으로 사용한다. 이 문서에서는 전체 통신 구조와 책임 경계만 정의하며 Endpoint별 Schema를 중복 정의하지 않는다.

모든 Path에는 공통 Prefix `/api/v1/agent-tools`가 적용된다.

| contract_id | 메서드 | Path | 역할 |
| --- | --- | --- | --- |
| `API-ACCOUNT-LIST` | GET | `/accounts` | 계좌 후보 조회 |
| `API-BALANCE-QUERY` | POST | `/accounts/balances:query` | 복수 계좌 잔액 조회 |
| `API-TRANSACTION-QUERY` | POST | `/transactions:query` | 거래내역 첫 페이지 조회 |
| `API-TRANSACTION-SUMMARY` | POST | `/transactions:summary` | 기간 거래 합계 조회 |
| `API-RECIPIENT-RESOLVE` | POST | `/recipients:resolve` | 이름 힌트의 기존 거래 수취인 자동 확정 |
| `API-EXTERNAL-TRANSFER-PREPARE` | POST | `/transfers/external:prepare` | 타인송금 조건 사전 평가 |
| `API-AUTH-CONTEXT-CREATE` | POST | `/auth-contexts` | 송금 추가 인증 Context 생성 |
| `API-EXTERNAL-TRANSFER-EXECUTE` | POST | `/transfers/external` | 타인송금 실행 |
| `API-INTERNAL-TRANSFER-PREPARE` | POST | `/transfers/internal:prepare` | 본인송금 조건 사전 평가 |
| `API-INTERNAL-TRANSFER-EXECUTE` | POST | `/transfers/internal` | 본인송금 실행 |
| `API-DEFAULT-ACCOUNT-PREPARE` | POST | `/settings/default-account:prepare` | 기본계좌 변경 조건 평가 |
| `API-DEFAULT-ACCOUNT-EXECUTE` | POST | `/settings/default-account` | 기본계좌 변경 실행 |
| `API-ACCOUNT-ALIAS-PREPARE` | POST | `/settings/account-alias:prepare` | 계좌 별칭 변경 조건 평가 |
| `API-ACCOUNT-ALIAS-EXECUTE` | POST | `/settings/account-alias` | 계좌 별칭 변경 실행 |

Agent는 `X-Execution-Context-Id`로 Backend가 사용자를 결정하게 하며 Tool 요청에 `user_id`, 전체 계좌번호, 인증 원문과 Frontend Access Token을 포함하지 않는다. 조회 API는 멱등성 키를 사용하지 않고 Prepare, Auth Context 생성과 Execute는 API 명세의 `Idempotency-Key` 규약을 따른다.

---

## 12. 전체 Workflow 예시

### 12.1 잔액 조회

```text
1. Frontend -> Backend /chat
2. Backend가 Chat Session과 Execution Context 생성
3. Backend -> Agent 실행 시작
4. Agent가 사용자 발화에서 계좌 힌트 추출
5. Agent -> Backend API-ACCOUNT-LIST
6. 계좌 선택이 필요하면 Agent -> Backend UI-BALANCE-ACCOUNT-SELECTION Webhook 후 중단
7. Frontend -> Backend 입력 제출
8. Backend가 계좌 권한을 검증하고 Agent를 Resume
9. Agent -> Backend API-BALANCE-QUERY
10. Agent -> Backend UI-BALANCE-RESULT Webhook
11. Backend -> Frontend SSE 결과 전달과 턴 종료
```

Backend가 계좌를 자동 확정하면 6번부터 8번까지 생략한다. Agent는 Backend가 검증한 `account_ids`로 잔액을 한 번에 조회하며 계좌별 반복 호출이나 잔액 계산을 수행하지 않는다.

### 12.2 타인송금

```text
1. Frontend -> Backend /chat
2. Backend -> Agent 실행 시작
3. Agent가 수취인 이름 힌트, 출금 계좌 힌트와 금액 추출
4. 이름 힌트가 있으면 Agent -> Backend API-RECIPIENT-RESOLVE
5. 수취인이 확정되지 않으면 UI-RECIPIENT-SELECT Webhook 후 중단
6. Backend가 사용자 선택 또는 신규 계좌를 검증하고 Agent를 Resume
7. Agent -> Backend API-ACCOUNT-LIST로 출금 계좌 확인
8. 계좌 또는 금액 입력이 필요하면 해당 UI Webhook 후 Backend 검증값으로 Resume
9. Agent -> Backend API-EXTERNAL-TRANSFER-PREPARE
10. Backend가 confirmation_id와 confirmation_view 반환
11. Agent -> Backend UI-EXTERNAL-TRANSFER-CONFIRMATION Webhook 후 중단
12. Frontend -> Backend /agent/approve
13. Backend가 Confirmation 승인 상태를 저장하고 Agent를 Resume
14. Agent -> Backend API-AUTH-CONTEXT-CREATE
15. Agent -> Backend UI-EXTERNAL-TRANSFER-AUTH Webhook 후 중단
16. Frontend <-> Backend 추가 인증
17. Backend가 인증 결과를 저장하고 Agent를 Resume
18. Agent -> Backend API-EXTERNAL-TRANSFER-EXECUTE
19. Backend가 승인·인증·잔액·한도·정책을 재검증하고 원장 변경과 금융 Audit 기록
20. Agent -> Backend UI-EXTERNAL-TRANSFER-RESULT Webhook
21. Backend -> Frontend SSE 결과 전달과 턴 종료
```

본인송금과 타인송금은 모두 사용자 승인과 추가 인증이 필수다. Agent는 승인이나 인증 상태를 폴링하지 않는다. 사용자가 출금 계좌, 수취인 또는 금액을 수정하면 Backend가 기존 Confirmation을 무효화하고 Agent는 해당 입력을 다시 받은 뒤 Prepare부터 재실행한다.

### 12.3 Webhook 종료 규칙

관리시트의 `emit_*_result`는 업무 결과를 전송하는 하나의 Workflow Step이다. Backend SSE가 별도 `done` 이벤트를 요구하는 현재 구현에서는 공통 Webhook Adapter가 결과 Component 전송 직후 terminal `done`을 이어서 전송할 수 있으며, 이를 별도 업무 Step으로 관리하지 않는다.

입력·승인·인증 대기 Webhook 뒤에는 `done`을 보내지 않는다. 사용자가 입력·승인·인증을 취소하면 Backend는 자신이 접수한 취소 결과로 Frontend 상호작용과 Stream을 종료하고, Agent는 중복 취소 Webhook 없이 Workflow State만 정리하고 종료한다.

---

## 13. Agent State 저장 규칙

공통 State와 Workflow별 State의 필드·타입·보존 범위는 `agent-management-sheet-v3.xlsx`의 `Workflow Data Schema` 탭을 정본으로 사용한다. Agent State는 중첩된 임의 객체가 아니라 관리시트에 등록된 평면 필드만 사용한다.

타인송금 State 예시는 다음과 같다.

```json
{
  "workflow_id": "wf_external_transfer",
  "chat_session_id": "95bdd0ac-cfa2-44c8-8258-043f0f43fd47",
  "execution_context_id": "exec_123",
  "agent_thread_id": "thread_123",
  "from_account_id": "acc_001",
  "to_recipient_id": "rcp_001",
  "to_recipient_candidate_id": null,
  "amount": 50000,
  "currency": "KRW",
  "confirmation_id": "confirm_123",
  "auth_context_id": "auth_123",
  "transaction_id": "txn_123"
}
```

Agent State에 저장하지 않는 값:

- 전체 계좌번호와 카드번호
- Access Token과 Refresh Token
- 비밀번호, PIN, 생체인증 원문
- 주민등록번호 등 개인 식별정보
- DB Credential과 내부 테이블 구조
- 서비스 Token과 Webhook Secret
- Workflow에 불필요한 전체 거래내역
- 최근 수취인과 이름 후보 목록
- Backend 정책의 내부 점수와 비공개 규칙

Workflow 종료 후 State는 보존 정책에 따라 만료한다. 금융 감사의 정본은 Backend가 금융 API 처리 과정에서 저장하며 Agent는 별도 Audit API를 호출하지 않는다.

---

## 14. 오류 코드와 Agent 처리

오류 코드와 정상 업무 Outcome은 `agent/docs/agent-tools-api-spec.md` 6장을 정본으로 사용한다. `success=false`의 요청·인증·상태·기술 오류와 `success=true`의 `data.outcome` 업무 판단을 구분한다.

대표 오류 처리 원칙은 다음과 같다.

| 오류 또는 상황 | Agent 처리 |
| --- | --- |
| `INVALID_EXECUTION_CONTEXT`, `INSUFFICIENT_SCOPE` | 실행 중단 |
| `EXECUTION_CONTEXT_EXPIRED` | 실행 중단 또는 새 실행 요청 |
| `ACCOUNT_NOT_FOUND`, `ACCOUNT_ACCESS_DENIED` | 계약된 경우에만 계좌 선택 단계로 이동 |
| `RECIPIENT_NOT_FOUND`, `RECIPIENT_CANDIDATE_EXPIRED` | 수취인 선택 또는 신규 계좌 검증 단계로 이동 |
| `CONFIRMATION_REQUIRED`, `CONFIRMATION_EXPIRED`, `CONFIRMATION_MISMATCH` | 기존 Confirmation을 사용하지 않고 Prepare부터 재진행 |
| `AUTH_REQUIRED` | 새 Auth Context 생성 단계로 이동 |
| `IDEMPOTENCY_REQUEST_IN_PROGRESS` | `Retry-After` 이후 같은 요청 재호출 |
| `IDEMPOTENCY_KEY_CONFLICT` | 실행 중단 후 요청과 키 사용을 점검 |
| `BACKEND_TEMPORARY_ERROR`, 연결·응답 Timeout, `502`, `503`, `504` | 공통 조건에 해당할 때 같은 논리 요청을 최대 1회 재시도 |

`blocked`, `correction_required`, `reauthentication_required`와 같은 값은 기술 오류가 아니라 각 Endpoint가 정의한 정상 업무 Outcome이다. Agent는 Backend의 `outcome`, `correction_view`, `blocked_view`를 임의로 재해석하지 않고 관리시트 Route에 따라 처리한다.

실행 API의 통신 오류는 같은 `Idempotency-Key`와 같은 Body로만 재시도한다. 사용자에게는 공개 가능한 오류 메시지만 전달하고 Stack Trace, DB 오류, 내부 URL과 Secret을 노출하지 않는다.

---

## 15. Backend 추가 개발 범위

### 15.1 필수 개발

#### A. Agent Client

- `AGENT_SERVICE_URL` 설정 추가
- Backend 서비스 인증 설정 추가
- Agent 실행 시작 Client 구현
- Agent Workflow 재개 Client 구현
- timeout, 재시도, 중복 요청 처리
- 현재 `mock_agent_driver` 호출 교체

권장 위치:

```text
backend/src/backend/services/agent_client.py
```

#### B. Execution Context

- `execution_context_id` 발급
- 사용자, `chat_session_id`, `agent_thread_id` 매핑
- Scope, 상태, 만료 관리
- Webhook과 Tool API 공통 Dependency 구현

권장 위치:

```text
backend/src/backend/services/execution_context_service.py
backend/src/backend/security/agent_service_auth.py
```

#### C. Webhook 강화

- `X-Execution-Context-Id` 검증
- Context와 `chat_session_id` 일치 확인
- `need_approval`의 `confirmation_id` 필수 검증
- 이벤트별 Metadata Schema 분리
- 종료된 턴의 추가 이벤트 차단
- `event_id` 또는 요청 ID 기반 중복 제거
- Payload 크기 제한과 감사용 이벤트 기록

현재 `webhook_api.py`는 이벤트 수신 전용으로 유지한다.

#### D. Agent Tool API

- 계좌, 잔액, 거래, 합계 조회
- 기존 거래 수취인 자동 확정과 사용자 입력 계좌 검증
- 외부 송금과 내부 이체 Prepare, Execute
- 기본계좌와 별칭 변경 Prepare, Execute
- 공통 서비스 인증과 Execution Context 검증
- 오류 코드와 CommonResponse 적용

권장 구조:

```text
backend/src/backend/api/agent_tools/account_api.py
backend/src/backend/api/agent_tools/transaction_api.py
backend/src/backend/api/agent_tools/recipient_api.py
backend/src/backend/api/agent_tools/transfer_api.py
backend/src/backend/api/agent_tools/setting_api.py
```

`recipient_select`의 신규 계좌번호 조회는 Frontend가 호출하므로 다음 사용자 인증 API도 추가한다.

```text
POST /api/v1/recipient-candidates:verify
```

이 API는 Frontend Bearer Token과 Chat Session 소유권을 검증한다. 계좌번호 원문을 Agent로 전달하지 않고 사용자, Chat Session, 만료시간에 묶인 `to_recipient_candidate_id`를 반환한다.

#### E. Confirmation Service

- Prepare 결과 고정
- 승인 대상 사용자와 Chat Session 저장
- 승인, 거절, 만료 상태 관리
- 사용자가 실행 조건을 수정하면 기존 Confirmation 무효화
- Execute 시 Confirmation과 현재 요청 일치 재검증

현재 `/api/v1/agent/approve`가 이 Service를 사용하도록 변경한다.

#### F. Auth Context Service

- 추가 인증 Context 생성
- Frontend 인증 결과 제출 API
- 상태와 만료 관리
- Execute 직전 재검증
- Agent에는 인증 원문이 아닌 상태만 제공

#### G. 멱등성과 금융 감사

- `Idempotency-Key` 저장소
- 같은 키와 같은 요청은 같은 결과 반환
- 같은 키와 다른 요청은 충돌 응답
- 실행 결과가 불명확한 네트워크 오류에 대한 결과 조회
- 금융 실행과 정책 판정의 Backend Audit Log 기록

### 15.2 Frontend와 함께 개발할 범위

- `need_input` SSE 타입 추가
- `account_card_list`, `recipient_select`, `number_input`, `period_input`, `auth_request` UI 추가
- `POST /api/v1/recipient-candidates:verify` Client 추가
- `POST /api/v1/agent/input` Client 추가
- `render_balance`, `confirm_transfer` 이외 UI Registry 확장
- 읽기 Component에 대응하는 `/api/v1/ui/*` API와 TanStack Query 연결
- Confirmation 수정 시 재확인 UX 적용

### 15.3 운영 환경 개발

- `AGENT_SERVICE_URL`, 서비스 Token, Webhook Secret 설정
- Secret 회전 정책
- Agent에서 DB와 Mock Financial Service로 가는 직접 네트워크 차단
- Backend와 Agent 간 timeout과 연결 풀 설정
- Webhook, Tool API, 금융 실행 Metric과 Alert
- 개발과 운영 Compose에 Agent 서비스와 주소 정합화

---

## 16. 권장 Backend 파일 책임

```text
backend/src/backend/api/
  chat_api.py
    Frontend 채팅, 승인, 일반 입력 접수

  webhook_api.py
    Agent 진행 이벤트 수신 전용

  sse_api.py
    Frontend SSE Ticket과 Stream 연결

  ui_api.py
    Frontend 읽기 전용 View Model API

  agent_tools/
    Agent가 호출하는 금융 Tool API

backend/src/backend/services/
  agent_client.py
    Backend가 Agent를 시작하고 재개하는 HTTP Client

  execution_context_service.py
    사용자, Chat Session, Agent Thread 연결

  confirmation_service.py
    Prepare와 사용자 승인 상태

  auth_context_service.py
    추가 인증 상태

  transfer_service.py
    금융 실행과 최종 재검증

  idempotency_service.py
    실행 중복 방지
```

하나의 `webhook_api.py`에 위 기능을 모두 넣지 않는다. Webhook은 이벤트 수신이고 Agent Tool API는 금융 요청과 응답이므로 인증, 검증, Transaction, 오류 의미가 서로 다르다.

---

## 17. 구현 순서

### 단계 1. 통신 기반

1. Backend `agent_client.py` 구현
2. Agent 내부 실행 시작과 재개 API 구현
3. `chat_session_id`, `execution_context_id`, `agent_thread_id` 매핑
4. Agent Webhook Client와 인증 적용
5. Mock Driver를 실제 Agent 호출로 교체

### 단계 2. 읽기 Workflow

1. 계좌 목록 API
2. 잔액 API
3. 거래내역과 합계 API
4. 기존 거래 수취인 자동 확정 API와 사용자 입력 계좌 검증 계약
5. Agent `bank_client`를 Backend Tool Adapter로 교체
6. Agent의 Mock Financial Service 직접 호출 제거

### 단계 3. 일반 입력 UI

1. `need_input` SSE Schema 추가
2. Backend Stream 변환과 검증
3. Frontend 입력 UI와 `/agent/input` 추가
4. Agent의 `waiting_input`을 `need_input` Webhook으로 전환

### 단계 4. 설정과 본인 계좌 이체

1. Confirmation Service
2. 설정 Prepare와 Execute
3. 내부 이체 Prepare와 Execute
4. 멱등성과 감사 기록

### 단계 5. 타인 송금

1. 외부 송금 Prepare
2. 승인 수정과 Confirmation 무효화
3. Auth Context와 Frontend 인증 연동
4. 외부 송금 Execute와 최종 재검증
5. 장애와 중복 실행 통합 테스트

### 단계 6. 운영 안전성

1. Agent 직접 금융 접근 제거 확인
2. 서비스 간 Secret 분리와 회전
3. Network Policy 적용
4. 추적 ID, Metric, Alert 적용
5. 보안과 장애 복구 테스트

---

## 18. 테스트 기준

### 18.1 계약 테스트

- Backend Webhook Pydantic Schema와 Agent Payload 일치
- Backend SSE Schema와 Frontend Type 일치
- `metadata.tool`, `metadata.component` 키 일치
- Backend Tool API 성공과 오류 Envelope 일치
- OpenAPI 또는 공유 Schema를 이용한 변경 감지

### 18.2 권한 테스트

- 다른 사용자의 `chat_session_id` 승인 거부
- 다른 사용자의 계좌 ID 조회와 실행 거부
- 다른 Execution Context의 Webhook 발행 거부
- 만료된 Context와 Confirmation, Auth Context 거부
- 허용되지 않은 Scope의 Tool 호출 거부

### 18.3 HITL 테스트

- `need_approval` 뒤 Stream 유지
- 승인 후 같은 Stream에 후속 이벤트 전달
- 거절 시 금융 실행 없이 `done`
- 수정된 승인 값으로 기존 Confirmation 실행 불가
- 중복 승인과 만료 승인 거부
- 잘못된 `input_request_id`와 저장된 `ui_contract_id`에 맞지 않는 입력 거부

### 18.4 금융 실행 테스트

- 실행 직전 잔액과 한도 재검증
- 같은 `Idempotency-Key` 재호출 시 중복 이체 없음
- 같은 키와 다른 Payload 충돌
- 인증이 필요한 거래에서 미인증 실행 거부
- Backend 오류나 timeout 후 결과 조회 가능
- 금융 감사 로그에 사용자, Context, Confirmation, 실행 결과 기록

---

## 19. 완료 기준

- Frontend가 Agent를 직접 호출하지 않는다.
- Agent가 Frontend Access Token을 받거나 저장하지 않는다.
- Backend가 실제 Agent 실행 시작과 재개를 호출한다.
- Agent가 진행 이벤트를 Webhook으로 보내고 Frontend가 SSE로 받는다.
- Agent가 DB와 Mock Financial Service를 직접 호출하지 않는다.
- 모든 금융 Tool이 Backend `/api/v1/agent-tools/*`만 호출한다.
- Backend가 Execution Context로 사용자를 결정한다.
- 모든 금융 조회가 계좌 소유권과 Scope를 검증한다.
- 모든 상태 변경이 유효한 Confirmation을 검증한다.
- 추가 인증 대상 실행이 유효한 Auth Context를 검증한다.
- 실행형 API에 멱등성이 적용된다.
- 수정된 실행 조건은 기존 Confirmation으로 실행할 수 없다.
- 금융 감사 로그의 정본이 Backend에 남는다.
- Agent State에는 참조 ID와 최소 마스킹 데이터만 저장된다.
- Webhook은 이벤트 중계 책임만 가진다.

---

## 20. 팀 간 최종 합의 문구

Agent는 자연어 이해, Workflow 선택, Slot 수집, 다음 Step 결정과 사용자 응답 조립을 담당한다. 금융 데이터 조회, 계좌 소유권 판정, 잔액과 한도 검증, 승인과 추가 인증 상태, 정책 판정, 원장 변경, 멱등성, 금융 감사는 Backend가 담당한다.

Agent는 Backend가 발급한 `execution_context_id`를 사용해 허용된 `/api/v1/agent-tools/*` API만 호출하며 임의의 `user_id`, Frontend Access Token, 전체 계좌번호, 인증 원문을 전달하거나 저장하지 않는다.

Agent가 사용자에게 보낼 진행 상태와 UI 신호는 `POST /api/v1/webhooks/agent`로 Backend에 전달한다. Backend는 검증된 이벤트만 Redis Stream에 발행하고 SSE로 Frontend에 중계한다. Webhook은 금융 Tool API를 대신하지 않는다.

송금과 설정 변경은 다음 순서를 따른다.

```text
정보 수집
-> Backend Prepare
-> 사용자 Confirm
-> 필요 시 Backend Auth
-> Backend Execute
-> Agent 결과 설명
```

이 문서를 Agent와 Backend 연동 구현의 기준으로 사용하며, 현재 구현과 목표 계약의 차이는 각 단계에서 계약 테스트로 확인한다.
