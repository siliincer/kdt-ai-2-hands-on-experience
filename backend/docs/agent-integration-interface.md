# Agent·FE·계정계 연동 인터페이스 (Backend 관점 핵심 요약)

> 대상: Agent(LangGraph) 팀, mock-financial-service(계정계) 팀, Frontend 팀
>
> 목적: 지금까지 Backend(채널계+정보계)에 **실제로 구현된** 연동 인터페이스를 한 장으로 정리한다.
> 현재는 실 Agent 대신 `services/mock_agent_driver.py`(목)가 같은 이벤트를 발행하지만, **계약·엔드포인트·
> 스키마는 실 Agent 연동을 그대로 받도록 완성**되어 있다. 상세 정본은 아래 문서를 따른다.
>
> - `AI_CONTEXT/AI_Coding_direction/agent 연동/agent-ui-hitl-contract.md` (UI Payload·Resume 값, 정본)
> - `AI_CONTEXT/AI_Coding_direction/agent 연동/agent-tools-api-spec.md` (Tool API, 정본)
> - `AI_CONTEXT/AI_Coding_direction/agent 연동/agent-backend-integration-contract.md` (통신 구조)
> - 구현 계획·이력: `AI_CONTEXT/AI_CODING_CONTEXT/2026-07-18_1924_Agent연동_UI-HITL-Contract_구현계획.md`

---

## 0. 통신 구조 한눈에

```text
Frontend ──[1] SSE 채팅/HITL──► Backend ──[3] 실행/재개(목표)──► Agent
   ▲                              │  ▲                            │
   └────[2] SSE 중계(Redis)───────┘  └──[4] Webhook 이벤트─────────┘
                                     └──[5] agent-tools 금융 API◄──┘
                                     │
                                     └──[6] financial_client──► mock-financial-service(계정계)
```

- **[1] FE→BE**: 사용자 메시지·입력·승인·인증 제출, UI 데이터 조회, SSE 티켓/연결.
- **[2] BE→FE**: Redis Stream(`agent:stream:{chat_session_id}`)을 SSE로 중계.
- **[3] BE→Agent (목표, 현재 mock)**: 실행 시작·중단 Workflow 재개.
- **[4] Agent→BE Webhook**: 진행/UI 이벤트 발행(→ Redis→SSE). need_input 은 pending_input 영속까지.
- **[5] Agent→BE agent-tools**: 금융 조회·검증·Prepare·Execute (14개 구현 완료).
- **[6] BE→계정계**: 잔액·원장·송금 실행(`services/financial/financial_client.py`).

핵심 식별자(발급 주체): `chat_session_id`(BE) / `execution_context_id`(BE) / `agent_thread_id`(Agent) /
`input_request_id`(Agent) / `confirmation_id`(BE) / `auth_context_id`(BE) / `transaction_id`(BE).
한 `chat_session`(=agent_thread)에는 **동시에 하나의 활성 대기**만 허용한다.

---

## 1. [4] Agent → Backend Webhook  ⟵ Agent 팀이 붙일 지점

```http
POST /api/v1/webhooks/agent
X-Agent-Secret: <AGENT_WEBHOOK_SECRET>
X-Execution-Context-Id: <exec_id>       # need_input 에서 pending_input 에 연결
X-Request-Id: <req_id>
Content-Type: application/json
```

```json
{ "chat_session_id": "...", "event_type": "<type>", "content": "사람이 읽는 문장",
  "approval_id": null, "metadata": { ... } }
```

`event_type`(구현된 SSE Enum, `schemas/sse.py`):

| event_type | 용도 | 필수 metadata |
| --- | --- | --- |
| `status` | 진행 상태 문장 | `{step?}` |
| `token` | assistant 텍스트 이어붙임 | — |
| `tool_call` | Tool 진행 표시 | `{tool}` |
| `component` | 읽기/결과 UI 렌더 | `{component, params}`(결과는 params 인라인, ADR C3) |
| `need_input` | 일반 입력 대기 | `{input_request_id, ui_contract_id, ui:{type,payload}}` |
| `need_approval` | 승인 대기 | top-level `approval_id`(=confirmation_id) + `{tool:"modal", args}` |
| `authentication_required` | 추가 인증 대기 | `{auth_context_id, ui_contract_id, ui:{type,payload}}` |
| `done` | 턴 종료 | `{transaction_id?}` |
| `error` | 공개 가능한 오류 | `{error_code, retryable}` |

**중요**: `event_type == need_input` 이면 Backend Webhook 핸들러가 SSE 발행 **전에**
`pending_inputs` 행을 만든다(`register_pending_input_from_event`). Agent 는 `metadata.input_request_id`·
`ui_contract_id`·`ui.type` 만 정확히 채우면 된다. `authentication_required` 의 `auth_context_id` 는
Agent 가 `POST /agent-tools/auth-contexts`(아래 §3)로 먼저 발급받은 값을 넣는다.

`done` 이후 같은 턴에 추가 이벤트를 보내지 않는다.

---

## 2. [3] Backend → Agent 내부 API  ⟵ Agent 서버가 제공해야 할 지점 (목표, 현재 mock)

현재 `services/chat_service.py` 가 `mock_agent_driver` 를 백그라운드로 돌린다.
**실 연동 시 이 호출만 Agent HTTP Client 로 교체**하면 된다(§6 이월 참조).

```http
POST /internal/v1/executions                      # 실행 시작
POST /internal/v1/executions/{agent_thread_id}/resume   # 중단 Workflow 재개
Authorization: Bearer <BACKEND_SERVICE_TOKEN>
```

실행 시작 요청 → 응답 `{ "accepted": true, "agent_thread_id": "..." }`(빠른 202, 결과는 Webhook).
재개 요청 `resume.type` ∈ `input` / `approval` / `auth`:

```json
{ "request_id":"...", "chat_session_id":"...", "execution_context_id":"...",
  "resume": { "type":"input", "input_request_id":"...", "value": { ... } } }
```

Backend 는 이미 **재개 값을 검증**해서 넘긴다(소유권·활성 pending_input·`ui_contract_id` Schema·
Confirmation/AuthContext 상태). Agent 는 검증된 값을 State 에 저장하고 같은 입력을 다시 요청하지 않는다.

---

## 3. [5] Agent → Backend agent-tools 금융 API  ⟵ 이미 14개 구현 완료

`/api/v1/agent-tools/*`, 서비스 토큰 + `X-Execution-Context-Id` 필수. 상태 변경은 `Idempotency-Key`.
Backend 가 Context 에서 사용자를 결정하므로 **요청 본문에 `user_id` 를 넣지 않는다.**

```text
GET  /accounts?query=...                     # 계좌 목록
POST /accounts/balances:query                # 잔액
POST /transactions:query   /transactions:summary
POST /recipients:resolve                     # 수취인 도출(이력 join)
POST /transfers/external:prepare  POST /transfers/external      # 타인송금 Prepare/Execute
POST /transfers/internal:prepare  POST /transfers/internal      # 본인송금
POST /auth-contexts (201)                    # 추가 인증 Context 생성
POST /settings/default-account:prepare  POST /settings/default-account
POST /settings/account-alias:prepare    POST /settings/account-alias
```

보조(FE 전용): `POST /api/v1/recipient-candidates:verify`(신규 계좌 원문 검증→`recipient_candidate_id`).

오류 envelope(정본 `agent-tools-api-spec`): `error.{category, code, message, retryable, details}`.
Prepare 응답의 `confirmation_id`·`confirmation_view` 를 Agent 는 이름 바꾸지 않고 `need_approval` 로 전달한다.

---

## 4. [1] Frontend → Backend HITL 제출 API  ⟵ FE 팀 참조 (구현 완료)

| 엔드포인트 | 용도 | 요청 body |
| --- | --- | --- |
| `POST /api/v1/chat` | 사용자 메시지 | `{chat_session_id?, message}` → `{chat_session_id}` |
| `POST /api/v1/agent/input` | 일반 입력·선택 회신 | `{chat_session_id, input_request_id, value}` |
| `POST /api/v1/agent/approve` | 승인/수정/취소 | `{chat_session_id, approval_id, decision, args?, component?, change_target?}` |
| `POST /api/v1/agent/authenticate` | 추가 인증(비밀번호) | `{chat_session_id, auth_context_id, password}` → `{auth_status}` |
| `GET /api/v1/sse/ticket` · `/sse/connect` | SSE 티켓·구독 | — |

인증 원문(비밀번호)은 **Backend 까지만** 전달하고 Agent 로 넘기지 않는다(계약 7.2).

`value`(제출값) 스키마는 `ui_contract_id`/UI 타입별로 `*_outcome` 필드를 갖는다:

| UI 타입 | value 예시 |
| --- | --- |
| `account_card_list` | `{account_selection_outcome:"selected", account_ids:[...]}` |
| `text_input` | `{alias_input_outcome:"submitted", alias:"..."}` |
| `number_input` | `{amount_input_outcome:"submitted", amount:50000}` |
| `recipient_select` | `{recipient_selection_outcome:"selected", to_recipient_id \| to_recipient_candidate_id}` |
| `period_input` | `{period_selection_outcome:"selected", start_date, end_date}` |
| `option_select` | `{option_selection_outcome:"selected", option:"spending"}` |
| `confirm_modal`(approve) | `decision:"approve" \| "change_requested" \| "cancelled"`, `change_target?` |
| `auth_request` | (password 로 `/agent/authenticate`) → `auth_status:"verified"\|"failed"` |

취소는 각 `*_outcome:"cancelled"`. FE 는 `input_*`/`render_*`/`confirm_modal`/`auth_request` 를
`ui/componentRegistry.ts` 의 toolName 으로 렌더한다(`need_input`→`input_<ui_type>`,
`component`→`render_<component>`, `need_approval`→`confirm_<tool>`).

---

## 5. [6] Backend → mock-financial-service(계정계)  ⟵ 계정계 팀 참조

Backend 는 `services/financial/financial_client.py` 로 정보계 읽기(`get_balance`, `get_ledger`)와
계정계 쓰기(`POST /transfers`, Idempotency-Key)를 호출한다. **소유권·수취인·Confirmation·인증·멱등성·
기본계좌·별칭·정책·감사는 Backend 책임**이고, 계정계는 잔액·원장·송금 실행의 물리 저장만 제공한다.

계정계에 향후 필요한 소요(현재는 Backend mock/메모리 + TODO 로 흡수, `9.1절` 정본):

- `/ledger` 에 `start_date`·`end_date`·`transaction_type`·`keyword` 파라미터
- `LedgerEntry` 에 `title`·`category`·`counterparty_account_id`
- 사용자(소유 계좌들) 기준 거래 + 상대방 함께 주는 read 경로(수취인 이름 join)
- (선택) hold 개념(`available_balance` 분리)

---

## 6. 실 Agent 연동 시 교체 지점(요약)

1. `services/chat_service.py` 의 `run_initial_turn`/`resume_after_*`/`run_after_auth` 호출을 Agent HTTP
   Client(`POST /internal/v1/executions*`) 로 교체. `services/mock_agent_driver.py`·`services/mock/hitl_fixtures.py`
   삭제(인메모리 `_WF_STATE`·설정 반영 mock 포함).
2. Agent 가 Webhook 으로 이벤트를 발행하면 나머지(pending_input 영속·Confirmation/AuthContext 생명주기·
   SSE 중계·FE 제출·재개 검증)는 **이미 동작**한다.
3. `X-Execution-Context-Id` Webhook 필수화, `BACKEND_SERVICE_TOKEN`/`AGENT_SERVICE_TOKEN` 분리.

> 슬롯 추출(풀 문장에서 이미 준 값 건너뛰기)은 **Agent 의 몫**이다. Backend 브리지는 `need_input` 을
> 필드 단위로 받으므로, Agent 가 부족한 필드에 대해서만 `need_input` 을 발행하면 그 UI 만 렌더·재개된다.
