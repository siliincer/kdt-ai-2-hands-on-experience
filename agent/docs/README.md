# Agent 서비스 통합 문서

agent 서비스(LangGraph 금융 에이전트)의 **단일 문서**다. 아키텍처, 계약(채팅
API/UI·은행 REST), 엔진 내부, 실행·검증, 파트별 인계까지 이 문서 하나로 본다.

| 다른 자료 | 언제 보는가 |
|---|---|
| [agent/README.md](../README.md) | 처음이라면 여기부터 — 폴더 구조와 동작 원리를 코드 지식 없이 읽을 수 있는 전체 개요 |
| [naming-convention.md](naming-convention.md) | step_id/tool_id 명명규칙과 시트 재작성 이력 — 스텝/툴을 추가·개명할 때 |
| `agent/notebooks/` 3권 | 실행 검증 노트북 (01 잔액조회 / 02 멀티턴 / 03 타인송금 — 03 Part 4에 실서비스 연결 설명) |

**무언가를 바꾸려 할 때 "어디서 시작하는가"는 [2절 계약별 정본과 변경
루틴](#2-계약별-정본과-변경-루틴)이 결정한다.**

---

## 1. 아키텍처와 통신 경로

fin-ai 저장소(`fin-ai/app`)의 YAML 설정 기반 LangGraph 에이전트를 이
모노레포의 `agent/` 서비스로 포팅했다 (포팅 결정사항의 상세 기록은 8절).

- **최상위 그래프**: `global_guardrail`(가드레일 검사) → `workflow_matching`(의도
  분류) → 워크플로우별 서브그래프 → `return_response`
- **서브그래프**: `config/workflows.yaml`의 steps/routes 정의를 읽어 시작 시점에
  LangGraph 서브그래프로 자동 컴파일한다 (`subgraph_builder.py`)
- **Tool**: `tool_id` 문자열 → Python 함수 매핑(`tools/registry.py`)
- **휴먼인더루프**: `step_type: input` 스텝에서 `interrupt()`로 그래프를 멈추고
  사용자 답변(`Command(resume=...)`)으로 재개
- **LLM**: 의도 분류·슬롯 추출·응답 생성에 사용하되, 전부 결정적 폴백(키워드
  규칙)이 있어 **API 키 없이도 동작**한다

### 통신 경로 3개 총괄

시스템에는 **독립적인 통신 경로가 3개** 있다. bank_client는 이 중
[3] 하나만 담당한다. 아래는 목표 구조이며, 현재 제품 경로는 그 다음 그림과 같다.

```
frontend ──> backend ──> mock_agent_driver
                    └─> mock-financial-service /api/v1

agent (독립, 8001) ──> LangGraph ──> LocalBankClient
                                      └─ 프로세스 인메모리 원장
```

| # | 경로 | 담당 코드 | 계약 | 역할 |
|---|---|---|---|---|
| [1] | frontend ↔ backend | frontend agent chat API ↔ backend `/api/v1/chat` | CommonResponse + SSE | 제품 채팅 요청/응답 |
| [2] | backend 채팅 실행 | `backend/src/backend/services/chat_service.py` | 현재 `mock_agent_driver` | 제품 데모 응답 |
| [3] | agent tool ↔ local 원장 | `agent/src/agent/bank_client.py` | Python client 계약 | 독립 Agent 계좌 조회·송금 |

> `agent/bank_client.py`는 Agent가 원장을 호출하는 경계다. Backend가 Agent를 호출하는
> HTTP client는 아직 구현되지 않았다. Agent의 `ui` 필드를 제품 SSE/UI 계약으로
> 변환하는 방식도 Backend/AI 담당자가 함께 정해야 한다.

### 계층별 파일

| 계층 | 파일 | 역할 |
|---|---|---|
| agent | `agent/src/agent/main.py`, `service.py`, `schemas.py` | FastAPI 진입점, interrupt-재개 대화 프로토콜 |
| agent | `agent/src/agent/{graph,nodes,subgraph_builder,...}.py` | fin-ai에서 포팅한 실행 엔진 |
| agent | `agent/src/agent/bank_client.py` | 원장 접근 추상화 (`LocalBankClient` / `HttpBankClient`) |
| mock-financial-service | `mock-financial-service/src/financial_service/` | Backend용 Fake Money HTTP API (8002) |
| backend | `backend/src/backend/services/chat_service.py` | 현재 mock Agent driver 오케스트레이션 |
| frontend | `frontend/src/features/agent_chat/api/` | 채팅 mutation 훅 + 타입 |

---

## 2. 계약별 정본과 변경 루틴

계약은 성격이 두 가지고, **정본은 계약마다 하나**다. 정본이 아닌 곳은
파생물이며, 어긋나면 정본이 이긴다.

| 계약 | 정본 (source of truth) | 파생물 | 어긋남을 잡는 장치 |
|---|---|---|---|
| **설계 계약** — 워크플로우·스텝·툴·라우팅·가드레일 규칙·위험등급·안내 문구 | **구글 시트 8탭** (Workflow / Workflow Step / Workflow Routing / Workflow Data Schema / Task / Tool_v2 / Risk Level / Guardrail Rule) | `agent/src/agent/config/*.yaml` (sync 스크립트가 생성) | sync `--dry-run` 경고, `tests/test_config_sanity.py` |
| **채팅 API/UI 계약** — frontend·backend와 오가는 wire (`ChatRequest`/`ChatResponse`/`ui` 5종) | **`agent/src/agent/schemas.py`** | OpenAPI(`localhost:8001/docs`), 이 문서 3절, 시트 UI Spec 탭(요약), frontend `types.ts` | 계약 테스트 `tests/test_ui_contract.py`, `test_agent_chat_api.py` — ui가 스키마를 벗어나면 응답 직렬화에서 실패 |
| **은행 REST 계약** — agent tool ↔ mock-financial-service | **두 파트 합의 → `agent/src/agent/bank_client.py`** | 이 문서 4절 매핑 표, 시트 API Spec 탭(요약) | 소비자 계약 테스트 `tests/test_bank_client.py` (MockTransport로 메서드/경로/바디 검증) |

시트 탭의 지위:

| 탭 | 지위 |
|---|---|
| sync가 읽는 8탭 (위 표) | **정본** — 여기를 고치면 sync로 코드에 전파된다 |
| UI Spec / API Spec | **요약** — 기획 초안·전체 조망용. 정본은 코드/이 문서 (위 표). 탭 상단에 "이 탭은 요약입니다. 정본: agent/docs/README.md 3절 (채팅 UI) / agent/src/agent/bank_client.py + README.md 4절 (은행 API)" 안내 행을 두어 혼동을 막는다 |
| Tool (구버전), Code Book | 참고/폐기 예정 — sync가 읽지 않는다 |

> 이렇게 나눈 이유: 시트는 사람이 합의하는 곳이라 검증 장치가 없다.
> 런타임 계약(실제 요청이 오가는 wire)까지 시트를 정본으로 두면 코드와
> 반드시 어긋난다 (실제로 auth_request ui_type 누락, accounts 응답 필드
> 이탈 3건이 발생했다). 런타임 계약은 타입+OpenAPI+테스트가 자동으로
> 지켜주는 코드가 정본이고, 시트는 조망용 요약으로 유지한다.

### 변경 루틴 — "바꾸려는 것"이 시작점을 결정한다

**규칙 1: 정본이 아닌 곳을 먼저 고치지 않는다.**
**규칙 2: 정본을 고친 같은 PR에서 파생물(문서·요약)을 갱신한다.**

| 바꾸려는 것 | 루틴 | 통보 |
|---|---|---|
| 워크플로우 흐름·스텝·툴 추가/개명·가드레일 규칙·문구 | ① [naming-convention.md](naming-convention.md) 규칙으로 이름 결정 → ② 시트 수정 → ③ `uv run python agent/scripts/sync_config_from_sheets.py --dry-run`으로 경고 확인 → ④ sync 실행 → ⑤ 필요 시 tool 함수/registry/테스트 → ⑥ `uv run pytest agent` | 불필요 (agent 내부) |
| 채팅 API/UI 계약 (status·ui.type·필드 추가/변경) | ① `schemas.py` 수정 → ② 계약 테스트 갱신·통과 → ③ 이 문서 3절 예시 갱신 → ④ 시트 UI Spec 탭 요약 갱신 → ⑤ **FE/BE 담당에 공유** (이 문서 링크로) | **필수** — 필드 제거/개명/타입 변경은 파괴적이므로 사전 합의 |
| 은행 REST 계약 (엔드포인트·필드) | ① mock-financial-service 담당과 합의 → ② `bank_client.py` + `test_bank_client.py` → ③ 이 문서 4절 표 갱신 → ④ 시트 API Spec 탭 요약 갱신 | **필수** (mock-financial-service 담당) |
| mock 데이터/시나리오 | `agent/src/agent/data/mock_bank.py` 수정 → 노트북 재실행 여부 판단 | 불필요 |

후속 과제: 시트 요약 탭 ↔ 코드 자동 대조 스크립트 (sync 스크립트에
`--check-spec-tabs` 추가 등) — 현재는 규칙 2(같은 PR에서 요약 갱신)로 관리.

---

## 3. 채팅 API 계약 (backend / frontend 담당자용 스펙)

agent 서비스(8001)와 주고받는 방법의 스펙이다. "상대 파트가 무엇을 어떻게
구현해야 하는가"를 다룬다.

계약의 소스 코드 위치 (문서와 코드가 어긋나면 코드가 기준):

| 무엇 | 어디 |
|---|---|
| 요청/응답/UI 타입 정의 | `agent/src/agent/schemas.py` (`ChatRequest`, `ChatResponse`, `ChatUi` 5종) |
| OpenAPI (Swagger) | agent 실행 후 `http://localhost:8001/docs` |
| 계약 강제 테스트 | `agent/tests/test_ui_contract.py`, `test_agent_chat_api.py` |
| frontend 대응 타입 | `frontend/src/features/agent_chat/api/types.ts` |

### 3-1. Agent HTTP 계약 (향후 Backend 연결용)

> 아래는 독립 Agent가 현재 제공하는 계약이다. Backend 제품 채팅은 아직 이 API를
> 호출하지 않는다. 실제 연결 시 timeout/error, interrupt/approval, SSE 변환 계약을
> 합의하고 consumer test를 추가해야 한다.

엔드포인트:

| Method | Path | 용도 |
|---|---|---|
| POST | `/chat` | 대화 한 턴 실행 (interrupt 재개 포함) |
| GET | `/health` | liveness (`{"status": "ok"}`) |

POST /chat 요청:

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `message` | string (1~2000자) | O | 사용자 발화 (버튼 라벨 회신 포함) |
| `thread_id` | string \| null | X | **직전 응답이 `waiting_input`일 때만** 그대로 회송 |
| `user_id` | string | X | 기본 `"user_001"` (mock 사용자) |

POST /chat 응답:

| 필드 | 타입 | 설명 |
|---|---|---|
| `reply` | string | 사용자에게 보여줄 문장 |
| `status` | `completed` \| `waiting_input` \| `blocked` \| `no_match` \| `failed` | 처리 결과 |
| `thread_id` | string | 이번 턴의 대화 스레드 id |
| `prompt_for` | string \| null | `waiting_input`일 때 요청 중인 입력의 state 키 (opaque) |
| `ui` | ChatUi \| null | `waiting_input`일 때 구조화 UI 힌트 (3-3) |

게이트웨이가 지켜야 할 규칙:

1. **agent는 업무 실패도 HTTP 200으로 표현한다** (`status: blocked/failed/...`).
   agent가 4xx/5xx를 내는 경우는 요청 스키마 위반(422)과 내부 결함(500)뿐이다.
2. **전송 장애의 HTTP 변환은 게이트웨이 책임**: 연결 불가 → 502, 타임아웃 → 504.
3. **읽기 타임아웃 60초 이상** (LLM 다회 호출 턴 존재).
4. **`thread_id`·`ui`·`prompt_for`는 변형 없이 pass-through** — 게이트웨이는
   CommonResponse 봉투(`{success, message, data}`)로 감싸기만 한다.
5. agent 재시작 시 대기 중 세션이 사라진다. 만료된 `thread_id` 회송은 에러가
   아니라 **조용히 새 턴**으로 처리되므로 게이트웨이의 재시도 로직은 불필요하다.

### 3-2. frontend 계약 (채팅 UI 담당)

status별 클라이언트 행동:

| status | 행동 |
|---|---|
| `waiting_input` | `reply`(질문) 표시 + **이 응답의 `thread_id`를 다음 요청에 회송** + `ui`가 있으면 카드 렌더링 |
| `completed` | `reply` 표시. thread_id 폐기 (다음 발화는 새 대화) |
| `blocked` | `reply`(차단 사유) 표시. thread_id 폐기 |
| `no_match` | `reply`(재질문 유도) 표시. thread_id 폐기 |
| `failed` | `reply`(오류 안내) 표시. thread_id 폐기 |

**사용자 선택 회신 규약 (중요)**: 선택/버튼 클릭을 별도 필드로 보내지 않는다.
**버튼 라벨 문자열을 다음 요청의 `message`에 그대로** 담는다. 서버가 라벨을
파싱해 처리한다 (예: `"송금하기"` 회신 → 승인 처리.
`test_ui_contract.py::test_action_label_reply_approves`가 보장).
자유 텍스트("1번이랑 2번", "3만원", "취소")도 항상 허용된다.

frontend는 agent를 직접 부르지 않는다. 기존 훅 사용:

```ts
// frontend/src/features/agent_chat/api/useAgentChat.ts
// POST /backendApi/api/v1/agent/chat → backend가 agent로 프록시
const { mutate } = useAgentChat();
mutate({ message: '김철수한테 5만원 보내줘' });
// 응답 status === 'waiting_input'이면:
mutate({ message: '송금하기', thread_id: prev.thread_id });
```

### 3-3. ui.type 5종 — 실제 페이로드와 렌더링 요구

`status: "waiting_input"`일 때 `ui` 필드에 구조화 힌트가 실린다.
**`ui`가 null이면 `reply` 텍스트 말풍선으로 폴백** — 항상 안전한 폴백이 있다.
타입 정의: `agent/src/agent/schemas.py`의 `ChatUi`.

내부 전달 흐름: tool이 `prompt_ui`(시스템 state 키)를 설정 → input 노드가
interrupt payload에 `ui`로 실어 보내고 소비 후 클리어 (대화형 tool은 payload에
직접 포함) → `service.run_chat` → `ChatResponse.ui` → backend passthrough →
frontend `AgentChatUi` 타입.

**`account_card_list`** — 계좌 카드 목록 선택. `multi: true`면 복수 선택 허용
(잔액조회가 사용).

```json
{ "type": "account_card_list", "multi": true,
  "options": [
    { "account_id": "acc_001", "account_name": "입출금통장", "balance": 1250000 },
    { "account_id": "acc_002", "account_name": "생활비통장", "balance": 430000 } ] }
```

회신: 선택 번호/이름 텍스트 (예: `"1번"`, `"입출금통장"`, multi면 `"1번이랑 2번"`).

**`search_select`** — 수취인 검색/선택. 목록 외 이름·계좌번호 직접 입력도 허용.

```json
{ "type": "search_select",
  "options": [
    { "recipient_id": "rec_001", "name": "김철수", "bank": "국민은행",
      "account_number": "123-456-789012" } ] }
```

**`number_input`** — 금액 입력. 자연어 금액("5만원")도 서버가 정규화한다.

```json
{ "type": "number_input" }
```

**`confirm_modal`** — 돈이 움직이는 최종 게이트. **반드시 명시적 확인 UI로
렌더링하고, 자동 확인은 금지한다** (fe_example의 `ConfirmBottomSheet` 패턴 참조).

승인 카드 (variant 없음):

```json
{ "type": "confirm_modal",
  "display": { "recipient_name": "김철수", "bank": "국민은행",
               "account_number": "123-456-789012",
               "from_account_name": "입출금통장", "amount": 50000 },
  "actions": ["송금하기", "취소", "수취인 수정", "금액 수정", "계좌 수정"] }
```

주의 안내 (고액·신규 수취인, `variant: "warning"`):

```json
{ "type": "confirm_modal", "variant": "warning",
  "display": { "amount": 1200000 }, "actions": ["확인", "취소"] }
```

**`auth_request`** — 본인 인증 (mock). 인증 UI 표시 후 `"인증완료"` 회신.

```json
{ "type": "auth_request", "methods": ["지문", "Face ID", "비밀번호"],
  "actions": ["인증완료", "취소"] }
```

주의:

- 해석 불가 답변은 승인 게이트에서 **보수적으로 취소** 처리된다.
- optional 필드(`multi`, `variant`)는 HTTP 응답에서 null로 올 수 있다 —
  없음(null)과 미포함을 동일하게 취급하라.
- 개선 여지: `actions`는 `{label, value}` 구조가 더 견고하다 — 후속 과제
  (9절). 변경은 정본 `schemas.py`에서 시작한다 (2절 변경 루틴).

### 3-4. 대화 시퀀스 예시 — 송금 3턴 (agent 직접 호출 기준)

```bash
curl -X POST localhost:8001/chat -H 'content-type: application/json' \
  -d '{"message": "김철수한테 5만원 보내줘"}'
```

```json
{ "reply": "[송금 확인]\n  받는 분    : 김철수 (국민은행 123-456-789012)\n  보내는 계좌: 입출금통장\n  금액       : 50,000원\n진행하려면 '승인', 중단하려면 '취소',\n수정하려면 '수취인 수정' / '금액 수정' / '계좌 수정'을 입력해주세요.",
  "status": "waiting_input", "thread_id": "f3a9c1...",
  "prompt_for": "transfer.approval_decision",
  "ui": { "type": "confirm_modal",
          "display": { "recipient_name": "김철수", "bank": "국민은행",
                       "account_number": "123-456-789012",
                       "from_account_name": "입출금통장", "amount": 50000 },
          "actions": ["송금하기", "취소", "수취인 수정", "금액 수정", "계좌 수정"] } }
```

```bash
curl -X POST localhost:8001/chat -H 'content-type: application/json' \
  -d '{"message": "송금하기", "thread_id": "f3a9c1..."}'
```

```json
{ "reply": "본인 인증을 진행해주세요 (지문 / Face ID / 비밀번호). 완료 후 '인증완료'를 입력해주세요.",
  "status": "waiting_input", "thread_id": "f3a9c1...",
  "prompt_for": "transfer.auth_result",
  "ui": { "type": "auth_request", "methods": ["지문", "Face ID", "비밀번호"],
          "actions": ["인증완료", "취소"] } }
```

```bash
curl -X POST localhost:8001/chat -H 'content-type: application/json' \
  -d '{"message": "인증완료", "thread_id": "f3a9c1..."}'
```

```json
{ "reply": "김철수님에게 50,000원을 송금했습니다. 거래번호: txn_5bc7969b",
  "status": "completed", "thread_id": "f3a9c1...",
  "prompt_for": null, "ui": null }
```

같은 시퀀스의 실행 가능한 버전: `agent/notebooks/03_external_transfer.ipynb`
Part 3, 자동 테스트: `agent/tests/test_agent_chat_api.py`.

### 3-5. 계약 변경 절차

1. `agent/src/agent/schemas.py`의 타입을 먼저 바꾼다 (계약의 소유처).
2. `agent/tests/test_ui_contract.py`가 깨지면 의도된 변경인지 확인하고 갱신한다.
3. 이 문서의 예시를 갱신하고, frontend `types.ts` 담당자에게 변경을 공유한다.
4. 필드 **추가**는 하위 호환(클라이언트는 모르는 필드 무시), 필드
   **제거/개명/타입 변경**은 파괴적 변경이므로 양쪽 합의 후 진행한다.

---

## 4. 은행 API 경계 (bank_client ↔ mock-financial-service)

tool이 인메모리 mock을 직접 읽던 구조를 **API 경계**로 바꾼 설계다.
경로 [3](1절)에 해당한다.

### 4-1. 동작 원칙

- **tool은 원장을 직접 만지지 않는다** — 항상 `get_bank_client()` 경유
  (`agent/src/agent/bank_client.py`)
- 전환: `BANK_CLIENT=local`(기본, 외부 의존 없음 — 테스트/노트북/Compose) /
  `BANK_CLIENT=http`(legacy adapter, 현재 금융 서비스 API와 직접 호환되지 않음)
- 에러 계약: 실패는 `BankClientError` 하나로 통일, tool이 잡아서
  error/failed 라우트로 보낸다 (그래프 크래시 금지). HTTP 구현은
  **GET 404를 빈 목록으로 번역**해 local 모드의 not_found 라우트 의미를
  보존한다

| 모드 | 구현 | 원장 위치 | 사용처 |
|---|---|---|---|
| `local` (기본) | `LocalBankClient` | agent 프로세스 인메모리 (`data/mock_bank.py`) | 노트북, pytest, 단독 실행, Docker Compose |
| `http` | `HttpBankClient` | legacy API 계약 | mock transport 단위 테스트만 지원 |

대상 주소는 `MOCK_FINANCIAL_SERVICE_URL`(기본 `http://localhost:8002`).

### 4-2. Legacy HTTP adapter 계약

| 사용하는 tool | BankClient 메서드 | legacy endpoint |
|---|---|---|
| verify_account, verify_from_account, check_balance, run_pre_execution_guardrail, fetch_balance | `get_accounts(user_id, account_id?)` | `GET /api/accounts/{user_id}` |
| resolve_recipient_input, verify_recipient_account, check_recipient_input | `get_recipients(user_id, recipient_name?)` | `GET /api/recipients` |
| execute_transfer | `transfer(user_id, from_account_id, to_recipient_id, amount, memo?)` | `POST /api/transactions/transfer-external` |
| write_audit_log (best-effort — 실패해도 흐름 유지) | `post_audit_log(...)` | `POST /api/audit-logs` |

현재 `mock-financial-service`는 `/api/v1/accounts`, `/api/v1/transfers` 계약을
사용하므로 위 adapter와 호환되지 않는다. 계정 매핑, 수취인 조회, idempotency 및 감사
로그 계약을 합의한 adapter가 구현되기 전에는 `BANK_CLIENT=http`를 배포에서 사용하지
않는다.

Legacy adapter는 `account_name`, `is_default`, `user_id` 기반 원장과 별도 수취인 API를
가정한다. 이 전제부터 현재 금융 서비스와 다시 합의해야 한다.

### 4-3. BANK_CLIENT 전환 방법

```bash
# local (기본) — 외부 의존 없음
uv run uvicorn agent.main:app --port 8001

# Compose도 현재 local 원장을 사용한다.
docker compose --profile agent up -d --build
```

- 테스트는 conftest가 `BANK_CLIENT`를 제거해 항상 local (원장 스냅샷 복원)
- HTTP 계약은 `agent/tests/test_bank_client.py`가 httpx.MockTransport로
  네트워크 없이 검증한다 (메서드/경로/파라미터/바디)
- 팩토리는 lru_cache — 런타임에 모드를 바꾸면 `get_bank_client.cache_clear()`

### 4-4. mock-financial-service

`mock-financial-service/`는 Backend가 사용하는 별도 Fake Money 원장이다. Agent의
legacy HTTP adapter와는 API 계약이 다르며, 현재 두 원장은 연결되지 않는다.
실제 네트워크 E2E는 adapter 재설계와 consumer test가 완료된 뒤 지원 범위로 올린다.

---

## 5. 엔진 내부 — state 설계와 tool 구현 가이드

### 5-1. state 구조

`AgentState` = 고정 시스템 필드 + 단일 `data` 버킷:

- **시스템 필드** (엔진 소속): `user_id`, `user_input`, `workflow_id`,
  `current_step_id`, `route_key`, `status`, `final_response`, `prompt_for`,
  `prompt_message`, `guardrail_result`, `log_id`, `logs`, `execution_trace`
- **`data: Annotated[dict, merge_data]`**: 모든 업무 데이터. 키는 워크플로우
  네임스페이스가 붙은 dotted 문자열 (`balance.account_hint`,
  `transfer.recipient`). reducer가 각 노드의 반환 delta를 병합한다.

배경: LangGraph는 스키마에 선언 안 된 top-level 키를 조용히 버리고, dotted
키는 TypedDict 필드가 될 수 없다. data 버킷 방식이라 **새 워크플로우를
추가해도 state.py 수정이 필요 없다.**

시스템/업무 키 분리는 엔진(`subgraph_builder._split_updates`)이 담당한다 —
tool은 flat dict를 반환하면 되고, 시스템 키만 top-level로 가고 나머지는
data 버킷에 저장된다.

### 5-2. tool 구현 방법

1. `agent/src/agent/tools/bank_tools.py`에 `state: dict`를 받는 함수를 추가한다.
   - 업무 데이터 읽기: `_data(state).get("transfer.recipient")` (Tool_v2의
     `input_state_keys` 계약)
   - 업무 데이터 쓰기: 반환 dict에 네임스페이스 키로
     (`{"transfer.recipient": {...}, "route_key": "verified"}` — Tool_v2의
     `write_state_keys` 계약)
   - 스칼라 반환 → step의 `output_data_key` 위치에 저장, route_key는 `success`
   - None 반환 → route_key `error`
   - 변경분(delta)만 반환, state in-place 수정 금지
2. `agent/src/agent/tools/registry.py`의 `TOOL_REGISTRY`에 등록한다.
3. `config/workflows.yaml`에서 해당 step의 routes를 확인하고, 함수가 반환하는
   route_key가 route 맵의 키와 일치하는지 확인한다 (계약 불일치 시 조기 종료).
4. `agent/tests/`에 LLM 없이 도는 테스트를 추가한다 (conftest가 API 키를 제거함).

### 5-3. wf_external_transfer 현황

**잔액조회와 타인송금 모두 end-to-end로 동작한다.** 송금 tool 15개가
Tool_v2 계약대로 구현되어 있다 (`bank_tools.py` 타인 송금 섹션).
슬롯 추출(수취인/금액/계좌)은 **LLM structured output이 1순위**이고
정규식/키워드는 폴백이다 — 키가 없어도 폴백 경로로 완주한다. 금액은 LLM이
원 단위 정수로 환산하며('오만원' 같은 한글 수사 대응), 환산 오류의 최종
방어선은 verify_amount 범위 검증과 승인 카드(사용자 확인 후 실행)다.

대화형 스텝 처리 방식 (승인/인증/경고):

- 해당 tool이 **직접 `interrupt()`를 호출**해 멈추고, 사용자 답변을
  키워드 파싱해 route_key(approved/cancelled/edit_* 등)를 정한다
- 재개 시 노드가 처음부터 재실행되므로 interrupt 이전 코드는 프롬프트
  조립 같은 멱등 작업만 둔다. 한 노드 실행에서 interrupt를 두 번 호출하지
  않는다 (재개 매칭이 위치 기반)
- 승인 게이트의 해석 불가 답변은 **보수적으로 취소** 처리한다

안전장치 체인: 금액 정규화·한도(5천만) → 잔액 확인(실시간 재조회) →
송금 정책 검사(1천만 차단/100만 경고/신규 수취인 경고) → 승인 카드(수정 루프
포함) → 본인 인증(mock) → **실행 직전 재검사**(승인 요약 `transfer.approval`과
실행 내용 대조 + 잔액 재확인) → 실행(원장 실차감) → 감사 로그.

정책 검사의 판정 기준(임계값·메시지·액션)은 코드가 아니라
`config/guardrail_rules.yaml`(=Guardrail Rule 시트)이 source of truth다 —
`policy/guardrail_engine.py`가 expression(`amount >= 10000000` 등)을 평가하고,
guardrail 스텝 tool은 발동 규칙을 라우트(blocked/warning_required 등)로
매핑만 한다. 전역 규칙(프롬프트 인젝션·타인 계좌 조회·비정상 호출)은
그래프 진입점 `global_guardrail_node`에서 같은 엔진으로 평가된다.

시나리오별 동작은 `agent/notebooks/03_external_transfer.ipynb`와
`agent/tests/test_transfer_flow.py`(10종) 참조.

### 5-4. config 동기화 (시트 → YAML)

```bash
uv run python agent/scripts/sync_config_from_sheets.py --dry-run  # 경고 검토
uv run python agent/scripts/sync_config_from_sheets.py           # 재생성
```

설계 계약은 시트가 source of truth다 (2절). 경고는 전부 advisory이며 시트
정리 요청 목록을 겸한다. config를 재생성했으면 서버/테스트를 재시작해야
반영된다 (YAML 캐시가 프로세스 수명).

---

## 6. 세션/체크포인터 한계

- 대화 상태는 **`MemorySaver`(프로세스 내 메모리)** 에만 저장된다.
  - 서버 재시작 시 대기 중이던 interrupt 세션이 전부 사라진다 (이때 클라이언트가
    thread_id를 회송해도 새 턴으로 처리되므로 오류는 발생하지 않는다)
  - **uvicorn 워커 1개 전제**다. 워커를 늘리면 재개 요청이 다른 워커로 가서
    세션을 못 찾는다 (현재 Dockerfile CMD가 1워커라 문제 없음)
- mock 데이터(`data/mock_bank.py`)도 프로세스 전역 가변 상태다. `execute_transfer`가
  잔액을 실제로 차감하므로 재시작 전까지 모든 요청이 공유한다.
  Docker Compose에서도 현재 이 local 원장을 사용하므로 Agent 재시작 시 초기화된다.
- **향후 과제**: persistent checkpointer(Redis/Postgres — compose에 둘 다 이미
  있음)로 교체하고, thread_id를 사용자 세션과 결합해 멀티턴 메모리를 확장한다.

---

## 7. 실행과 검증

```bash
# agent 단독 실행 (OPENAI_API_KEY 없어도 키워드 폴백으로 동작)
uv run uvicorn agent.main:app --reload --host 127.0.0.1 --port 8001

# 스모크
curl -X POST localhost:8001/chat -H 'content-type: application/json' \
  -d '{"message":"생활비 통장 잔액 얼마야?"}'

# 테스트 (전부 LLM 미사용 결정적 경로)
uv run pytest agent
uv run pytest backend

# 단계별 실행 검증 노트북 3권 (팀원 온보딩용, 실행 출력 포함)
# agent/notebooks/01_balance_inquiry.ipynb   — 잔액조회 단계별 실행
# agent/notebooks/02_multiturn.ipynb         — interrupt/재개 멀티턴
# agent/notebooks/03_external_transfer.ipynb — 타인송금 시나리오 8종 + HTTP
uv run --with jupyter jupyter lab   # 커널: 레포 루트 .venv

# 전체 스택
cp .env.example .env   # OPENAI_API_KEY 입력 시 LLM 의도분류/응답생성 활성화
docker compose up -d --build
```

관련 환경변수 (`.env.example`):

- `LLM_PROVIDER`: `openai`(기본) | `vertex` | `ollama` — LLM 제공자 선택
- `LLM_MODEL`: 모델 지정 (미지정 시 openai=gpt-4o-mini,
  vertex=gemini-2.5-flash, ollama=qwen2.5:3b)
- `OPENAI_API_KEY`: openai 사용 시 필요 (없으면 규칙 기반 폴백으로 완주)
- `OLLAMA_BASE_URL` / `OLLAMA_MODEL`: ollama 사용 시. 명시적으로
  `get_llm(model=...)`을 호출하면 그 값이 `OLLAMA_MODEL`보다 우선한다. Ollama 서버는 로컬
  개발 머신에서만 실행하고, 배포 서버에는 Ollama 런타임을 올리지 않는다.
  Docker 컨테이너에서 호스트 Ollama에 붙을 때는
  `OLLAMA_BASE_URL=http://host.docker.internal:11434`를 사용한다.
- `GOOGLE_CLOUD_PROJECT` / `VERTEX_LOCATION`: vertex 사용 시. 현재 인증 지원 범위는
  host 실행의 ADC(`gcloud auth application-default login`)다. Compose에는 서비스 계정
  파일 mount 계약이 없으므로 Vertex container 실행은 지원하지 않는다.
- `AGENT_SERVICE_URL`: backend가 agent를 찾는 주소
- `BANK_CLIENT`: `local`(기본) | `http` — 은행 원장 접근 방식 (4절)
- `MOCK_FINANCIAL_SERVICE_URL`: http 모드의 원장 주소

---

## 8. 포팅 결정사항 기록 (fin-ai → agent/)

이력 성격의 기록이다 — 현재 구조가 왜 이렇게 생겼는지의 근거.

### 8-1. 라이브 실행 경로만 포팅 (레거시 제외)

fin-ai에는 실행 엔진이 두 벌 존재했다. 순차 실행기(`workflow_executor.py`)는
구버전 설계로, 현재 그래프(`graph.py`)에서는 전혀 호출되지 않는 죽은 경로였다.
다음을 포팅에서 제외했다:

- `workflow_executor.py` — 서브그래프 기반 실행이 완전히 대체
- `policy/risk_engine.py` — 순차 실행기 전용 의존이라 함께 사장(라이브 경로에서는
  위험도 판단이 `assess_transfer_risk` tool 안에 구현되어 있음)
- `nodes.workflow_execution_node` — 위 실행기를 부르는 유일한 노드 함수
- `context_schema.py` — CLI 전용 참고 스크립트
- `scripts/` — Google Sheet 동기화 스크립트(시트 id 하드코딩, 이 레포와 무관.
  이후 이 레포 시트에 맞는 sync 스크립트를 새로 작성 — 5-4절)
- `notebooks/`, `config/backup/`, fin-ai 자체 docs

단, `config/risk_levels.yaml`은 workflows.yaml이 위험등급 메타데이터로 참조하고
있어 향후 위험 정책 재도입을 대비해 함께 가져왔다 (`workflow_loader.get_risk_policy`
접근자도 유지).

### 8-2. config 경로 일원화

원본은 config 디렉터리 경로 상수가 3개 모듈(`workflow_loader`, `workflow_matcher`,
`subgraph_builder`)에 각각 중복 정의되어 있었고, 모두 "패키지 폴더의 한 단계 위"를
가리켰다. src 레이아웃(`agent/src/agent/`)으로 옮기면 이 가정이 깨지므로:

- config를 패키지 안(`agent/src/agent/config/`)으로 옮기고
- `agent/src/agent/paths.py` 하나에 `CONFIG_DIR`/`WORKFLOWS_PATH`를 정의해
  세 모듈이 공유하게 했다

`Path(__file__)` 기준이라 로컬 실행·pytest·Docker 어디서든 동일하게 동작한다.

### 8-3. import 경로 재작성

원본은 `agent/`, `tools/`, `policy/`, `data/`가 최상위 패키지 4개로 나란히 있는
구조였다. 포팅하면서 전부 `agent` 패키지의 하위 패키지로 넣었다:

- `from tools.registry import ...` → `from agent.tools.registry import ...`
- `from policy.guardrail_engine import ...` → `from agent.policy.guardrail_engine import ...`
- `from data.mock_bank import ...` → `from agent.data.mock_bank import ...`
- 기존 `from agent.* import ...`는 그대로 유효

### 8-4. CLI → FastAPI 대화 프로토콜

원본 `main.py`는 stdin 기반 REPL이었다. HTTP로 바꾸면서 interrupt-재개를 다음
규칙으로 설계했다 (`agent/src/agent/service.py`):

- **새 턴은 항상 새 thread_id**로 실행한다. 원본 `ask()`도 발화마다 새 thread를
  만들었고, 스레드를 재사용하면 이전 턴의 `final_response`/`prompt_message` 같은
  상태가 남아 다음 턴을 오염시킬 수 있다.
- 그래프가 `interrupt()`로 멈추면 `status: waiting_input`과 함께 thread_id를
  반환한다. 클라이언트는 **이때만** thread_id를 다음 요청에 회송한다.
- 회송된 thread_id에 pending interrupt가 있으면 `Command(resume=답변)`으로 재개,
  없으면(만료·오타 등) 조용히 새 턴으로 처리한다 — 에러를 던지지 않는다.

### 8-5. 동기 그래프 처리

포팅한 엔진은 전부 동기 코드다(LLM 호출, tool 함수 모두 blocking). FastAPI
엔드포인트를 `async def`가 아닌 **sync `def`** 로 두어 Starlette가 threadpool에서
실행하게 했다. 이벤트 루프를 막지 않으면서 엔진 코드를 수정하지 않는 가장 작은
선택이다. 향후 처리량이 필요하면 LangGraph `ainvoke` + async tool 전환을 검토한다.

### 8-6. 응답 봉투 계층

- **agent 서비스**: 내부 서비스이므로 plain JSON(`ChatResponse`)을 반환
- **backend**: 이 레포의 표준 봉투로 감싼다 — 성공 `{success, message, data}`,
  실패 `{success: false, error: {code, message}}`
- **frontend**: `customFetch`가 봉투를 풀어 `data`(AgentChatResponse)만 반환

에이전트 장애는 backend에서 `HTTPException`으로 변환된다: 연결 불가 → 502,
타임아웃 → 504 (LLM 다회 호출을 감안해 읽기 타임아웃 60초).

---

## 9. 연결 현황과 파트별 인계 단서

"tool이 mock으로만 도는 것 아닌가?"에 대한 답: **tool은 원장을 직접 만지지
않고 전부 `bank_client.get_bank_client()`를 경유**하며, 연결 모드는 환경변수
하나로 갈린다 (4절). 노트북·pytest가 인메모리로 도는 것은 기본값이 `local`이기
때문이지 연결 코드가 없어서가 아니다.

### 구간별 연결 상태 (2026-07 기준)

| 구간 | 상태 | 근거 파일 |
|---|---|---|
| frontend → backend | 훅까지 완료, **UI 미구현** | `frontend/src/features/agent_chat/api/useAgentChat.ts`, `types.ts` |
| backend → agent | **미연결** (`mock_agent_driver` 사용) | `backend/src/backend/services/chat_service.py` |
| agent tool → local 원장 | 완료 (독립·비영속) | `agent/src/agent/bank_client.py` |
| agent tool → mock-financial-service | **미연결** (API 계약 불일치) | `agent/src/agent/bank_client.py` |
| mock-financial-service | 완료 (+ 자체 테스트) | `mock-financial-service/src/`, `tests/` |

### 파트별 인계 단서 (agent 파트 밖 — 담당자 작업 필요)

- **frontend**: 채팅 페이지/컴포넌트가 없다. 구현 스펙은 **3-2·3-3절**에
  정리되어 있다 (status별 행동, `ui.type` 5종 페이로드/렌더링 요구, 버튼 라벨
  회신 규약, 승인 게이트 필수 규칙). `useAgentChat` 훅과 `types.ts` 계약은
  이미 있고, `frontend/src/features/agent_transfer/`의 빈 파일 2개는 이 작업의
  자리표시자로 보인다.
- **mock-financial-service**: 수취인 응답에 `last_transfer_at` 필드 추가 필요.
  agent의 `new_recipient_warning` 가드레일이 이 필드로 신규 수취인을 판정하는데,
  현재 로컬 원장(`agent/src/agent/data/mock_bank.py`)에만 있다. 필드가 없으면
  규칙은 안전하게 미발동한다(누락 변수 규칙) — 즉 http 모드에서는 신규 수취인
  경고가 꺼진 상태다.
- **infra(nginx)**: `/backendApi/`만 Backend로 전달한다. Agent는 외부에 공개하지 않고
  EC2 loopback/Docker 내부에서 독립 검증한다.
- **backend**: 은행 도메인 API(계좌/송금)는 backend에 없고 mock-financial-service가
  담당한다. backend가 원장 API를 중계/소유해야 한다는 요구가 생기면 별도 설계
  필요 (현재 backend `Settings`는 `MOCK_FINANCIAL_SERVICE_URL`을 읽지 않는다).

### 향후 과제

- [x] `wf_external_transfer` tool을 Tool_v2 계약대로 구현 — 완료 (5-3절)
- [ ] `HttpBankClient`를 현재 `mock-financial-service`의 `/api/v1` 계약에 맞게
      재설계하고 consumer test 추가
- [x] `LLM_PROVIDER` 환경변수 지원 — 완료 (openai/vertex/ollama 전환, 7절)
- [x] 가드레일 `expression` 조건 타입 구현 — 완료 (5-3절.
      `guardrail_engine._evaluate_expression`, global/tool scope 규칙 활성)
- [ ] 송금 답변 파싱(승인/금액 등)을 키워드에서 LLM 보강으로 확장
- [ ] MemorySaver → persistent checkpointer (Redis/Postgres)
- [ ] frontend 채팅 UI를 `useAgentChat` 훅에 연결 (fe_example의 카드형 채팅 UI
      참고 — 현재는 API 계층만 존재. 인계 단서는 위)
- [ ] 가드레일 `target_owner` 추출을 키워드 휴리스틱에서 LLM 우선으로 승격
      (`policy/context_extractor.py`)
- [ ] frontend가 ui_type별 컴포넌트 렌더링 (FE 팀 — 계약은 3-3절)
- [ ] 원장의 진짜 주인과 API 계약 결정 후 Agent adapter, user-account mapping,
      recipient, idempotency, audit consumer test를 함께 구현
- [ ] actions `{label, value}` 구조화 (정본 schemas.py에서 시작 — 2절 변경 루틴)
- [ ] audit log 스키마 정식화 (현재 best-effort 전송)
- [ ] 시트 UI Spec / API Spec 탭 요약 갱신: API 차이 3건(4-2절),
      auth_request ui_type(3-3절) + 탭 상단 "요약" 안내 행 추가
