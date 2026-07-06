# 에이전트 통합 문서 (fin-ai 포팅)

fin-ai 저장소(`fin-ai/app`)의 LangGraph 금융 에이전트를 이 모노레포의 `agent/`
서비스로 포팅하면서 고려한 내용과 결정사항을 정리한다.

## 1. 개요와 아키텍처

### 원본(fin-ai) 구조

fin-ai는 YAML 설정 기반의 LangGraph 에이전트다.

- **최상위 그래프**: `global_guardrail`(가드레일 검사) → `workflow_matching`(의도
  분류) → 워크플로우별 서브그래프 → `return_response`
- **서브그래프**: `config/workflows.yaml`의 steps/routes 정의를 읽어 시작 시점에
  LangGraph 서브그래프로 자동 컴파일한다 (`subgraph_builder.py`)
- **Tool**: `tool_id` 문자열 → Python 함수 매핑(`tools/registry.py`).
  데이터는 인메모리 mock(`data/mock_bank.py`)
- **휴먼인더루프**: `step_type: input` 스텝에서 `interrupt()`로 그래프를 멈추고
  사용자 답변(`Command(resume=...)`)으로 재개
- **LLM**: OpenAI(`gpt-4o-mini` 기본). 의도 분류·슬롯 추출·응답 생성에 사용하되,
  전부 결정적 폴백(키워드 규칙)이 있어 **API 키 없이도 동작**한다
- **원본 진입점**: CLI REPL(`main.py`) — 포팅하면서 FastAPI로 대체

### 포팅 후 배치

```
frontend (React)
  └─ useAgentChat 훅 ── POST /backendApi/api/v1/agent/chat (vite dev proxy)
       ↓
backend 게이트웨이 (8000)
  └─ api/agent_api.py ── httpx ──> AGENT_SERVICE_URL/chat
       ↓
agent 서비스 (8001, agent.main:app)
  └─ service.run_chat ──> LangGraph GRAPH.invoke (MemorySaver)
```

| 계층 | 파일 | 역할 |
|---|---|---|
| agent | `agent/src/agent/main.py`, `service.py`, `schemas.py` | FastAPI 진입점, interrupt-재개 대화 프로토콜 |
| agent | `agent/src/agent/{graph,nodes,subgraph_builder,...}.py` | fin-ai에서 포팅한 실행 엔진 |
| backend | `backend/src/backend/api/agent_api.py`, `services/agent_client.py` | 프록시 라우터 + HTTP 클라이언트 |
| frontend | `frontend/src/features/agent_chat/api/` | 채팅 mutation 훅 + 타입 |

## 2. 포팅 결정사항과 근거

### 2-1. 라이브 실행 경로만 포팅 (레거시 제외)

fin-ai에는 실행 엔진이 두 벌 존재했다. 순차 실행기(`workflow_executor.py`)는
구버전 설계로, 현재 그래프(`graph.py`)에서는 전혀 호출되지 않는 죽은 경로였다.
다음을 포팅에서 제외했다:

- `workflow_executor.py` — 서브그래프 기반 실행이 완전히 대체
- `policy/risk_engine.py` — 순차 실행기 전용 의존이라 함께 사장(라이브 경로에서는
  위험도 판단이 `assess_transfer_risk` tool 안에 구현되어 있음)
- `nodes.workflow_execution_node` — 위 실행기를 부르는 유일한 노드 함수
- `context_schema.py` — CLI 전용 참고 스크립트
- `scripts/` — Google Sheet 동기화 스크립트(시트 id 하드코딩, 이 레포와 무관)
- `notebooks/`, `config/backup/`, fin-ai 자체 docs

단, `config/risk_levels.yaml`은 workflows.yaml이 위험등급 메타데이터로 참조하고
있어 향후 위험 정책 재도입을 대비해 함께 가져왔다 (`workflow_loader.get_risk_policy`
접근자도 유지).

### 2-2. config 경로 일원화

원본은 config 디렉터리 경로 상수가 3개 모듈(`workflow_loader`, `workflow_matcher`,
`subgraph_builder`)에 각각 중복 정의되어 있었고, 모두 "패키지 폴더의 한 단계 위"를
가리켰다. src 레이아웃(`agent/src/agent/`)으로 옮기면 이 가정이 깨지므로:

- config를 패키지 안(`agent/src/agent/config/`)으로 옮기고
- `agent/src/agent/paths.py` 하나에 `CONFIG_DIR`/`WORKFLOWS_PATH`를 정의해
  세 모듈이 공유하게 했다

`Path(__file__)` 기준이라 로컬 실행·pytest·Docker 어디서든 동일하게 동작한다.

### 2-3. import 경로 재작성

원본은 `agent/`, `tools/`, `policy/`, `data/`가 최상위 패키지 4개로 나란히 있는
구조였다. 포팅하면서 전부 `agent` 패키지의 하위 패키지로 넣었다:

- `from tools.registry import ...` → `from agent.tools.registry import ...`
- `from policy.guardrail_engine import ...` → `from agent.policy.guardrail_engine import ...`
- `from data.mock_bank import ...` → `from agent.data.mock_bank import ...`
- 기존 `from agent.* import ...`는 그대로 유효

### 2-4. CLI → FastAPI 대화 프로토콜

원본 `main.py`는 stdin 기반 REPL이었다. HTTP로 바꾸면서 interrupt-재개를 다음
규칙으로 설계했다 (`agent/src/agent/service.py`):

- **새 턴은 항상 새 thread_id**로 실행한다. 원본 `ask()`도 발화마다 새 thread를
  만들었고, 스레드를 재사용하면 이전 턴의 `final_response`/`prompt_message` 같은
  상태가 남아 다음 턴을 오염시킬 수 있다.
- 그래프가 `interrupt()`로 멈추면 `status: waiting_input`과 함께 thread_id를
  반환한다. 클라이언트는 **이때만** thread_id를 다음 요청에 회송한다.
- 회송된 thread_id에 pending interrupt가 있으면 `Command(resume=답변)`으로 재개,
  없으면(만료·오타 등) 조용히 새 턴으로 처리한다 — 에러를 던지지 않는다.

### 2-5. 동기 그래프 처리

포팅한 엔진은 전부 동기 코드다(LLM 호출, tool 함수 모두 blocking). FastAPI
엔드포인트를 `async def`가 아닌 **sync `def`** 로 두어 Starlette가 threadpool에서
실행하게 했다. 이벤트 루프를 막지 않으면서 엔진 코드를 수정하지 않는 가장 작은
선택이다. 향후 처리량이 필요하면 LangGraph `ainvoke` + async tool 전환을 검토한다.

### 2-6. 응답 봉투 계층

- **agent 서비스**: 내부 서비스이므로 plain JSON(`ChatResponse`)을 반환
- **backend**: 이 레포의 표준 봉투로 감싼다 — 성공 `{success, message, data}`,
  실패 `{success: false, error: {code, message}}`
- **frontend**: `customFetch`가 봉투를 풀어 `data`(AgentChatResponse)만 반환

에이전트 장애는 backend에서 `HTTPException`으로 변환된다: 연결 불가 → 502,
타임아웃 → 504 (LLM 다회 호출을 감안해 읽기 타임아웃 60초).

## 3. API 계약

### agent `POST /chat` (내부, 8001)

```json
// 요청
{ "message": "잔액 얼마야?", "thread_id": null, "user_id": "user_001" }
// 응답
{ "reply": "조회할 계좌를 선택해 주세요 (여러 개 가능):\n  1. 입출금통장\n  2. 생활비통장",
  "status": "waiting_input", "thread_id": "f3a9...",
  "prompt_for": "balance.account_selection_input" }
```

`prompt_for` 값은 네임스페이스 state 키다 (시트 v2 개편 이후). 클라이언트는
opaque 문자열로 취급하면 된다.

### backend `POST /api/v1/agent/chat` (외부 공개)

요청 본문은 agent와 동일. 응답은 CommonResponse 봉투:

```json
{ "success": true, "message": "에이전트 응답을 가져왔습니다.",
  "data": { "reply": "...", "status": "completed", "thread_id": "...", "prompt_for": null } }
```

### status 의미

| status | 의미 | 클라이언트 처리 |
|---|---|---|
| `completed` | 워크플로우 정상 완료 | reply 표시 |
| `waiting_input` | 추가 입력 대기 | reply(질문) 표시 + 다음 요청에 thread_id 회송 |
| `blocked` | 가드레일 차단 | reply(차단 안내) 표시 |
| `no_match` | 매칭 워크플로우 없음 | reply(재질문 유도) 표시 |
| `failed` | 실행 실패 | reply(오류 안내) 표시 |

### frontend 훅

```ts
const { mutate } = useAgentChat();
mutate({ message: '잔액 얼마야?' });
// status === 'waiting_input' 이면:
mutate({ message: '1번', thread_id: prev.thread_id });
```

## 4. 세션/체크포인터 한계

- 대화 상태는 **`MemorySaver`(프로세스 내 메모리)** 에만 저장된다.
  - 서버 재시작 시 대기 중이던 interrupt 세션이 전부 사라진다 (이때 클라이언트가
    thread_id를 회송해도 새 턴으로 처리되므로 오류는 발생하지 않는다)
  - **uvicorn 워커 1개 전제**다. 워커를 늘리면 재개 요청이 다른 워커로 가서
    세션을 못 찾는다 (현재 Dockerfile CMD가 1워커라 문제 없음)
- mock 데이터(`data/mock_bank.py`)도 프로세스 전역 가변 상태다. `transfer_money`가
  잔액을 실제로 차감하므로 재시작 전까지 모든 요청이 공유한다.
- **향후 과제**: persistent checkpointer(Redis/Postgres — compose에 둘 다 이미
  있음)로 교체하고, thread_id를 사용자 세션과 결합해 멀티턴 메모리를 확장한다.

## 5. state 설계와 tool 구현 가이드 (시트 v2 개편)

### state 구조

`AgentState` = 고정 시스템 필드 + 단일 `data` 버킷:

- **시스템 필드** (엔진 소속): `user_id`, `user_input`, `workflow_id`,
  `current_step_id`, `route_key`, `status`, `final_response`, `prompt_for`,
  `prompt_message`, `guardrail_result`, `log_id`, `logs`, `execution_trace`
- **`data: Annotated[dict, merge_data]`**: 모든 업무 데이터. 키는 워크플로우
  네임스페이스가 붙은 dotted 문자열 (`balance.account_hint`,
  `transfer.recipient`). reducer가 각 노드의 반환 delta를 병합한다.

배경: LangGraph는 스키마에 선언 안 된 top-level 키를 조용히 버리고, dotted
키는 TypedDict 필드가 될 수 없다. data 버킷 방식이라 **새 워크플로우를
추가해도 state.py 수정이 필요 없다.** 상세: `agent/docs/agent-sheet-v2-review.md`.

시스템/업무 키 분리는 엔진(`subgraph_builder._split_updates`)이 담당한다 —
tool은 flat dict를 반환하면 되고, 시스템 키만 top-level로 가고 나머지는
data 버킷에 저장된다.

### tool 구현 방법

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

### wf_external_transfer 현황

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
송금 정책 검사(1천만 차단/100만 경고) → 승인 카드(수정 루프 포함) →
본인 인증(mock) → **실행 직전 재검사**(승인 요약 `transfer.approval`과
실행 내용 대조 + 잔액 재확인) → 실행(원장 실차감) → 감사 로그.

시나리오별 동작은 `agent/notebooks/03_external_transfer.ipynb`와
`agent/tests/test_transfer_flow.py`(10종) 참조.

### config 동기화 (시트 → YAML)

```bash
uv run python agent/scripts/sync_config_from_sheets.py --dry-run  # 경고 검토
uv run python agent/scripts/sync_config_from_sheets.py           # 재생성
```

시트가 source of truth다. 경고는 전부 advisory이며 시트 정리 요청 목록을
겸한다. config를 재생성했으면 서버/테스트를 재시작해야 반영된다
(YAML 캐시가 프로세스 수명). 상세: `agent/docs/agent-sheet-v2-review.md` 4절.

## 6. 실행과 검증

```bash
# agent 단독 실행 (OPENAI_API_KEY 없어도 키워드 폴백으로 동작)
uv run uvicorn agent.main:app --reload --host 0.0.0.0 --port 8001

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

- `LLM_PROVIDER`: `openai`(기본) | `vertex` — LLM 제공자 선택
- `LLM_MODEL`: 모델 지정 (미지정 시 openai=gpt-4o-mini, vertex=gemini-2.5-flash)
- `OPENAI_API_KEY`: openai 사용 시 필요 (없으면 규칙 기반 폴백으로 완주)
- `GOOGLE_CLOUD_PROJECT` / `VERTEX_LOCATION`: vertex 사용 시. 인증은 로컬
  ADC(`gcloud auth application-default login`) 또는
  `GOOGLE_APPLICATION_CREDENTIALS`(서비스 계정 JSON — 컨테이너용)
- `AGENT_SERVICE_URL`: backend가 agent를 찾는 주소
- `BANK_CLIENT`: `local`(기본) | `http` — 은행 원장 접근 방식

## 7. 향후 과제

- [x] `wf_external_transfer` tool을 Tool_v2 계약대로 구현 — 완료 (5절)
- [ ] 송금 답변 파싱(승인/금액 등)을 키워드에서 LLM 보강으로 확장
- [ ] `data/mock_bank.py` → `mock-financial-service`(8002) HTTP 연동으로 교체
- [ ] MemorySaver → persistent checkpointer (Redis/Postgres)
- [x] `LLM_PROVIDER` 환경변수 지원 — 완료 (openai/vertex 전환, 6절)
- [ ] frontend 채팅 UI를 `useAgentChat` 훅에 연결 (fe_example의 카드형 채팅 UI
      참고 — 현재는 API 계층만 존재)
- [ ] 가드레일 `expression` 조건 타입 구현 (현재 `contains_any`만 평가됨)
