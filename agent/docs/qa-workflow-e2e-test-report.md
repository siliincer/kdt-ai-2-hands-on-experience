# Agent Workflow 전수 QA 테스트 보고서

- 테스트일: 2026-07-22
- 대상 브랜치: `feat/erase_backend_agent_mocking`
- 테스트 대상: `agent/src/agent/config/workflows.yaml`에 정의된 전체 8개 업무 Workflow
  (전체 목록·스코프 근거: `agent/docs/agent-workflow-parallel-development-plan.md` 41~49행)
- 테스트 방식: 브라우저 대신 실 스택(backend:8000 + agent:8001 + mock-financial-service:8002
  + Postgres + Redis)에 직접 발화를 `POST /api/v1/chat`으로 보내고, `agent:stream:{chat_session_id}`
  Redis Stream(SSE 소스)의 결과 이벤트를 확인하는 방식으로 진행. 완료 기준은
  `agent-workflow-parallel-development-plan.md` 11절("Workflow 완료 기준")을 참고.

## 0. [심각] 프론트 — 실 Agent 이벤트 대부분이 화면에 렌더링 안 됨 (component/need_approval)

**증상**: "송금 승인 모달이 출력 안 됨". 재현: 잔액/계좌 조회 등 `component` 이벤트, 송금 등
`need_approval` 이벤트가 backend→SSE까지는 정상 발행되는데(redis stream에서 데이터 직접 확인함,
누락·오류 없음) 브라우저엔 아예 안 뜨거나 빈 화면으로 보일 가능성이 높음.

**원인**: `frontend/src/features/agent_chat/model/chatMessage.ts`의 SSE→UI 컴포넌트 라우팅이
일부 이벤트 타입에서 옛날 mock 계약 방식(`metadata.tool`, `metadata.component` 같은 평평한
필드)을 아직 그대로 씀 — 그런데 실제 agent(`feat/erase_backend_agent_mocking`)는
`metadata.ui.type` / `metadata.ui_contract_id` 중첩 구조로 보냄(계약이 바뀜, mock 제거 작업 때
프론트가 못 따라간 것).

- `need_input`(41행)·`authentication_required`(103행)는 이미 `metadata.ui.type` 읽도록 돼있어 정상
- **`component`(56행)**: `metadata?.component` 읽음 → 실 이벤트엔 그 필드 없음(`metadata.ui.type`에
  있음, 예: `"ui":{"type":"account_list",...}`) → `component` 값이 `undefined`라 `toolName`이
  `render_unknown`이 됨 → registry(`componentRegistry.ts`)에 없는 키라 렌더러 못 찾음 → 화면 무반응.
  잔액조회·계좌목록 등 읽기전용 카드 전부 영향권.
- **`need_approval`(89행)**: `metadata?.tool` 읽음(구 계약 `{"tool":"transfer","args":{...}}` 기준)
  → 실 이벤트엔 없고 `metadata.ui.type`(예: `"confirm_modal"`)에 있음 → `tool`이 `'action'`으로
  폴백돼 `toolName`이 `confirm_action`이 됨 → registry에 없는 키 → **승인 모달 자체가 렌더 안 됨**.
  송금·계좌별칭변경·기본계좌변경 등 모든 승인 흐름 영향권.

**부가 발견**: `need_approval` 라우팅을 고치더라도, `ConfirmModalUI.tsx`(`buildRows`, 24행)가
`args.purpose`(`"external_transfer"` 등) 값으로 어떤 행을 보여줄지 분기하는데, 실제
`wf_external_transfer`(`agent/src/agent/workflows/external_transfer.py:412` 부근)가 보내는
payload엔 `purpose` 키가 아예 없음 — 라우팅만 고치면 모달은 뜨겠지만 내용(보내는 계좌/받는 분 등)이
빈 채로 뜰 가능성 있음. 확인은 라우팅 fix 이후 재검증 필요.

**판정**: backend/agent는 계약대로 정상 발행 중 — **프론트가 mock→실 연동 전환 때 이 두 이벤트
타입의 매핑을 안 옮긴 것**. 이번 세션에서 "정상"으로 판정했던 조회 결과들(§1 표의 ✅ 항목 다수)도
사실은 backend/redis 데이터만 검증한 것이고 실제 화면 렌더링은 미확인 상태였음 — **재검증 필요**.

**영향 범위(8개 workflow 코드 경로 전수 대조, 2026-07-22 추가)**: 이 버그는 workflow별 개별
버그가 아니라 이벤트 타입(`component`/`need_approval`) 자체에 걸린 공통 버그라, 8개 전부
예외 없이 영향받음. `need_input`(폼 입력)·`error`·`done`(순수 텍스트)만 정상 라우팅됨 —
assistant-ui가 미등록 tool에 `argsText`를 텍스트로 fallback 표시하는 것으로 보여, 지금까지
채팅에 문구 자체는 계속 보였던 것(카드/버튼 없이 텍스트만).

| workflow | 사용 이벤트 | 프론트 상태 |
|---|---|---|
| wf_balance_inquiry | component(balance_result) | ❌ 카드 미표시(문구만) |
| wf_account_list | component(account_list) | ❌ 카드 미표시(실증 확인) |
| wf_transaction_history | component(추정)/error | ❌(에러는 텍스트라 표시는 됨) |
| wf_period_amount_summary | component(amount_summary) | ❌ 카드 미표시 |
| wf_set_default_account | component(setting_result) | ❌ 카드 미표시 |
| wf_set_account_alias | component(setting_result/account_card_list) | ❌ 카드 미표시 |
| wf_external_transfer | need_input(정상) + need_approval(confirm_modal) + component(빈계좌) | 입력폼 ✅ / 승인모달·빈계좌카드 ❌ |
| wf_internal_transfer | need_input(정상) + need_approval + component(빈계좌) | 입력폼 ✅ / 승인모달·빈계좌카드 ❌ |

**수정 범위(미적용, 요청 시 진행)**: `chatMessage.ts`의 `component`/`need_approval` case에서
`metadata?.ui?.type`을 우선 읽고 구 필드로 폴백하도록 변경 + agent 쪽 confirm_modal payload에
`purpose` 채우기(다수 workflow 파일 영향).

## 1. 결과 요약

| Workflow | 발화 예시 | 결과 | 비고 |
|---|---|---|---|
| `wf_balance_inquiry` | "잔액 얼마야?" | ✅ 정상 | mock-financial-service 연동 확인 |
| `wf_account_list` | "내 계좌를 보여줘" | ✅ 정상 | 키워드 폴백 보강 후 정상(§3 참고) |
| `wf_transaction_history` | "지난주 결제 내역 보여줘" | ❌ 버그 | §2-1 |
| `wf_period_amount_summary` | "이번 달 얼마 썼어?" | ✅ 정상 | |
| `wf_set_default_account` | "KDT은행을 기본 출금 계좌로 해줘" | ✅ 정상 | 단, 공식 예시 발화는 §3 이슈로 오분류됨 |
| `wf_set_account_alias` | "KDT은행을 생활비통장이라 해줘" | ❌ 버그 2건 | §2-2(hint 정규식), §2-3(request_id 컬럼 길이) |
| `wf_external_transfer` | "철수에게 5만원 보내줘" | ✅ 정상(단, 승인취소 후 §2-6 버그) | HITL 수취인 선택으로 정상 정지, 전체 승인·인증 흐름 API로 완주 확인. 승인모달에서 취소 시 §2-6 |
| `wf_internal_transfer` | "KDT은행에서 신한은행으로 5만원 옮겨줘" | ✅ 정상(제약) | 테스트 계좌가 1개뿐이라 "출금 가능 계좌 없음"으로 정상 차단 — 버그 아님, 재테스트 시 계좌 2개 이상 필요 |

8/8 실행 완료. 버그 4건(§2-1, §2-2, §2-3, §2-6) + 프론트 렌더링 버그 1건(§0) + 키워드/슬롯 추출
좁은 패턴 문제 2건(§2-5, §3) 발견.

## 2. 버그

### 2-1. `wf_transaction_history` — TransactionType Enum 불일치 (backend 미구현)

**증상**: "카드" 또는 "결제" 단어가 들어간 발화(예: "지난주 결제 내역 보여줘")에서 거래내역 조회가
항상 실패하고 "거래내역을 확인하지 못했습니다. 잠시 후 다시 시도해 주세요." 에러로 종료됨.

**원인**: 공식 계약 스펙과 backend 실제 구현의 `TransactionType` Enum이 다름.

| 위치 | 값 |
|---|---|
| 스펙(정본) — `agent/docs/agent-tools-api-spec.md:648-655` | `deposit, withdrawal, transfer, card_payment, atm_withdrawal, fee, interest` (7개) |
| agent 구현 — `agent/src/agent/contracts/agent_tools/read.py:14-20` | 7개, 스펙과 일치 |
| **backend 구현** — `backend/src/backend/schemas/agent_tools/transaction.py:16-20` | `deposit, withdrawal, transfer` — **3개뿐** |

**트리거 지점**: `agent/src/agent/workflows/inquiry_support.py:134-149`의 `extract_transaction_type()`이
발화에 "카드"/"결제"/"ATM"/"현금인출"/"수수료"/"이자" 중 하나라도 있으면 세부 타입으로 매핑함
("카드"·"결제"는 `card_payment`로 매핑되며, 이 둘은 OR 조건이라 "결제"만 있어도 걸림 — 오탐 폭이 넓음).

**흐름**: agent가 스펙대로 `transaction_type: "card_payment"`를 담아
`POST /api/v1/agent-tools/transactions:query` 호출 → backend Pydantic Enum에 없는 값이라
`422 Unprocessable Entity` → `wf_transaction_history`의 에러 핸들러가 catch해 일반 에러 메시지로 응답.

**판정**: agent 쪽 구현은 스펙 준수. **backend `TransactionType` Enum이 계약 스펙 대비 미완성** —
완료 기준 3번째 항목("Backend Tool 요청·응답 Schema 일치") 위반.

**제안 수정**: `backend/src/backend/schemas/agent_tools/transaction.py`의 `TransactionType`에
`card_payment`, `atm_withdrawal`, `fee`, `interest` 4개 값 추가.

### 2-2. `wf_set_account_alias` — `account_hint` 추출 정규식 그리디 매칭 버그

**증상**: 테스트 계좌(bank_name="KDT은행", active=true)가 존재하는데도 "KDT은행을 생활비통장이라
해줘" 발화 시 `emit_account_alias_selection_empty` Step으로 빠져 "별칭을 변경할 수 있는 계좌가
없습니다"로 응답함. 은행명을 "신한은행"으로 바꿔도 동일 증상 — 은행명 문제가 아님을 확인.

**원인**: `agent/src/agent/workflows/setting_slot_extraction.py:27`의 `_ACCOUNT_HINT` 정규식
(`([가-힣A-Za-z0-9]+(?:\s+[가-힣A-Za-z0-9]+)?\s*(?:은행|통장|계좌))`)이 그리디 매칭이라,
"X은행을 Y통장이라"처럼 계좌 관련 명사("은행"/"통장"/"계좌")가 사이 단어 1개 이하로 근접해
2번 등장하면 첫 번째에서 멈추지 않고 두 번째까지 통째로 삼킴.

재현(Python `re` 직접 실행):

```text
'KDT은행을 생활비통장이라 해줘'  -> account_hint = 'KDT은행을 생활비통장'   (버그: 두 단어가 뭉개짐)
'신한은행을 생활비통장이라 해줘' -> account_hint = '신한은행을 생활비통장'  (버그: 은행명 무관하게 동일 증상)
'KDT은행을 기본 출금 계좌로 해줘' -> account_hint = 'KDT은행'             (정상: 사이 단어 2개라 그리디가 못 뻗음)
```

`wf_set_default_account`가 통과한 건 "기본 출금"처럼 사이 단어가 2개라 정규식의 optional 그룹
(1개 단어까지만 허용)이 못 뻗어서 우연히 첫 키워드에서 멈춘 것뿐 — 근본은 같은 정규식을 쓰므로
같은 버그를 안고 있음(사이 단어 수에 따라 우연히 회피됐을 뿐).

뭉개진 hint("kdt은행을 생활비통장")는 실제 계좌의 `bank_name`("kdt은행")·`alias`·`account_type`
어디에도 부분 문자열로 포함되지 않아 `backend/src/backend/services/agent_tools/account_service.py`의
`_matches_hint()`가 전부 실패시키고, 후보 0개 → `no_accounts` → "변경할 계좌 없음" 오탐으로 이어짐.

**제안 수정**: `_ACCOUNT_HINT`를 non-greedy(`+?`)로 바꾸거나, `(?:은행|통장|계좌)` 뒤에 조사/어미
경계(예: 부정 lookahead)를 추가해 첫 매칭에서 확정되도록 수정. `agent/src/agent/workflows/inquiry_support.py`의
동일 패턴(`_ACCOUNT_HINT`)도 같은 결함 가능성 있어 같이 점검 필요.

**참고— 위 버그를 우회하는 표현**: "KDT은행 별칭을 생활비로 바꿔줘"(계좌 관련 명사가 문장에 1번만
등장) 형태면 `account_hint`/`route`/`alias` 추출이 모두 정상 동작함을 확인. QA 재현·데모 시 사용 가능.

### 2-3. `wf_set_account_alias` — `request_id` 컬럼 길이 초과로 DB 에러

위 2-2 우회 표현으로 실제 진행시켜보니(계좌는 정상 해소됨) 다음 단계(Confirmation 생성)에서
새로운 에러 발생.

**증상**: `POST /api/v1/webhooks/agent`에서 `emit_account_alias_error`로 종료, backend 로그에
`sqlalchemy.exc.DBAPIError: StringDataRightTruncationError: value too long for type character
varying(64)`.

**원인**: `agent/src/agent/workflows/workflow_support.py:62-65`의 `step_request_id()`가
`f"{parent_request_id}:{step_id}"`로 request_id를 이어붙임. `parent_request_id`(`req_start_`+32자
hex=42자)에 `step_id`가 긴 경우(`prepare_account_alias_change`=29자)를 합치면 71자가 되어,
backend `financial_audit_log.request_id` 컬럼(`backend/src/backend/models/financial_audit_log.py:31`,
`String(64)`)의 64자 제한을 넘음 → INSERT 실패.

**판정**: agent가 만드는 합성 request_id에 길이 상한이 없고, backend 컬럼 길이와 계약이 안 맞음.
`step_id`가 짧은 다른 workflow는 우연히 안 걸렸을 뿐 — step_id 길이에 따라 다른 workflow에서도
재현 가능성 있음(예: step_id 25자 이상인 곳 전수 점검 필요).

**제안 수정**: `financial_audit_log.request_id` 컬럼을 넉넉히(예: 128~255) 늘리거나, agent 쪽에서
합성 request_id를 컬럼 길이에 맞게 해시/축약.

**추가 확인 + 수정 완료**: `wf_external_transfer`(`prepare_external_transfer` 단계)에서도 동일 에러
재현됨 — workflow 하나에 국한된 문제 아님을 확인. `request_id` 컬럼을 64→128자로 넓히는 마이그레이션
(`backend/migrations/versions/f1a2b3c4d5e6_widen_financial_audit_log_request_id.py`) 추가·적용,
모델(`backend/src/backend/models/financial_audit_log.py:31`)도 `String(128)`로 갱신함. 재검증 결과
정상 진행 확인.

### 2-4. 수취 계좌번호 검증 — 하이픈 포맷 불일치로 항상 404 (수정 완료)

**증상**: 실존하는 수취 계좌번호(예: `110-002-000002`)를 정확히 입력해도
"수취 계좌를 확인할 수 없습니다"(404)로 항상 실패함.

**원인**: 프론트 계좌번호 입력 필드가 입력할 때마다 숫자만 남김(의도된 입력 마스크,
`frontend/src/features/agent_chat/ui/RecipientSelectUI.tsx:164`
`.replace(/[^\d]/g, '')`) — 서버로는 항상 하이픈 없이(`110002000002`) 전달됨. 반면
backend `accounts.account_number` 컬럼엔 하이픈 포함 표기(`110-002-000002`)로 저장돼있고,
`get_account_by_number()`(`backend/src/backend/repository/account_repository.py:99`, 수정 전)는
`==` 정확 일치라서 항상 불일치 → 404.

사용자가 계좌번호를 잘못 입력한 게 아니라(입력 마스크는 의도된 정상 UX), backend가 저장·조회
포맷을 정규화하지 않은 게 원인.

**수정**: `get_account_by_number()`를 양쪽 다 숫자만 남기고(`re.sub(r"\D", "", ...)` / SQL
`regexp_replace`) 비교하도록 변경. backend 재기동 후 하이픈 없는 입력으로 재검증 완료
(`recipient_candidate_id` 정상 발급 확인).

### 2-5. 수취인 이름 자동 확정 — `recipient_name_hint` 추출이 "OO에게/OO한테"만 인식

**증상**: 과거 완료된 타인송금 이력이 있는 상대(예: 박서연)한테 다시 보낼 때도 "박서연 송금"처럼
치면 이름을 못 찾고 "최근 송금한 수취인이 없어요"(수취인 선택 화면)로 빠짐. `필요한 조건`(이력
있음, 이름 정확 일치)을 다 만족시켜도 재현됨.

**원인**: `agent/src/agent/workflows/transfer_slot_extraction.py:28`의 이름 추출 정규식
`_RECIPIENT_HINT = re.compile(r"([가-힣]{2,4})\s*(?:에게|한테)")`가 이름 뒤에 반드시 "에게"·"한테"
조사가 붙어야만 인식함. `workflow_matcher.py`의 workflow 라우팅 자체는 "송금"만으로도
`wf_external_transfer`로 잘 잡히지만(§3 키워드 폴백), 그 안의 이름 슬롯 추출은 별도의 더 좁은
패턴이라 "OO 송금"·"OO한테 말고 OO" 같은 변형은 못 잡음 — 워크플로우 라우팅과 슬롯 추출의
커버리지가 서로 다른 문제.

**재현 vs 정상**: "박서연 송금" → 이름 추출 실패(no_match) / "박서연에게 5만원 보내줘" → "박서연"
정상 추출, 과거 이력 있으면 자동 확정(resolved)까지 확인.

**판정**: LLM 경로(`extract_external_transfer_slots_llm_first`)가 살아있으면 이런 변형도 잡아낼
가능성 높음 — 이 역시 §3와 동일하게 `OPENAI_API_KEY` 부재로 인한 좁은 규칙 기반 폴백의 한계.

### 2-6. [심각] `wf_external_transfer` — 승인 모달에서 "취소" 시 최종 응답(done)이 안 옴 → 채팅 입력창 영구 잠김

**증상**: 송금 승인 모달에서 취소하면 그 직후 채팅 입력 버튼이 비활성 상태로 안 풀림(재현 보고).

**재현(API 직접 호출로 확정)**:
1. "박서연에게 5만원 보내줘" → 수취인 확인 → 승인 모달(`need_approval`)까지 정상 도달
2. `POST /api/v1/agent/approve` `decision:"cancelled"` 호출 → **200 성공 응답**, `confirmations.status`도
   `INVALIDATED`로 정상 반영됨
3. 그런데 `agent:stream:{chat_session_id}` Redis Stream엔 **그 이후 이벤트가 단 하나도 안 쌓임**
   (done도, error도, 아무것도). backend 로그에도 `POST /api/v1/webhooks/agent` 호출 자체가 없음 —
   backend→agent `resume` 요청은 202 Accepted로 잘 갔는데 agent가 콜백을 아예 안 보냄.

**원인**: `agent/src/agent/workflows/external_transfer.py:933-943`(`request_external_transfer_approval`
노드의 conditional edge 맵)에서 `"cancelled": END`로 그래프가 곧장 종료됨. `"error"`는
`emit_external_transfer_error`(응답 발행 노드)를 거쳐 END로 가는데, `"cancelled"`만 발행 노드 없이
바로 END. `agent/src/agent/runtime/execution.py`의 `_finish_invocation`이 정상 종료 시
`WebhookExecutionCompletionReporter.report_completion()`으로 `done` 웹훅을 보내야 하는데, 이 경로에서
그게 발생하지 않음(정확한 내부 실패 지점은 미조사 — `_interrupt_payload_from_result` 오탐 또는
백그라운드 태스크 예외 삼킴 둘 중 하나로 추정).

프론트는 `agent.status`가 `'done'`/`'error'` 이벤트를 받아야 `isRunning`이 꺼지는 구조
(`frontend/src/features/agent_transfer/model/useAgentStream.ts`, `useChatRuntime.ts:190-193`)라,
종료 이벤트 자체가 안 오면 `isRunning`이 영원히 `true`로 남아 입력창이 잠긴 채 유지됨 — 새로고침
전까진 못 풂.

**영향 범위(코드 정적 확인, 4개 workflow 전수 대조, 2026-07-22 확정)**: 동일하게 응답 발행 노드 없이
`"cancelled": END`로 바로 끝나는 지점이 `wf_external_transfer` 6곳, `wf_internal_transfer` 7곳,
`wf_set_account_alias` 3곳, `wf_set_default_account` 2곳 — **총 18곳, 4개 workflow 전부** 동일 결함.
수취인선택 취소·계좌선택 취소·승인 취소·재인증 취소 등 "취소" 액션 전반이 영향권.

**심각도 정정**: 단순히 결과 카드가 안 보이는 §0과 달리, 이 버그는 `done`/`error` 이벤트 자체가
영원히 안 와서 `isRunning`이 꺼지지 않고 **채팅 입력창(버튼)이 통째로 비활성 잠김** — 새로고침 전엔
그 세션에서 아무 것도 못 침. §0보다 사용자 영향이 큼.

**판정**: backend는 계약대로 처리(Confirmation invalidate, agent resume 호출)했고, **agent 쪽
"cancelled" 종료 경로에 최종 응답 발행이 빠진 게 근본 원인**.

**근본 원인 확정 + 수정 완료(2026-07-22)**: `agent/src/agent/runtime/execution.py:447`의
`_report_completion()`에 `result.get("route_key") == "cancelled"`이면 완료 웹훅 자체를 스킵하는
조건이 있었음(의도적으로 작성된 코드, 실수형 버그 아님 — 아마 "취소는 별도 처리하겠지" 하고
작성 후 그 별도 처리를 안 넣은 케이스). 4개 workflow 18개 취소 지점이 전부 이 공통 런타임 함수를
거치므로 여기 한 곳만 고치면 전체 해결됨. `result.get("route_key") == "cancelled"` 조건 제거로
수정.

기존 테스트(`test_cancelled_completion_does_not_publish_duplicate_done`)가 이 버그 동작을 "의도된
것"으로 고정하고 있었음 — 실제로는 `_cancel_node`가 자체적으로 아무 웹훅도 안 보내 "중복 방지"라는
근거가 성립하지 않아, 취소 시에도 done이 발행돼야 함을 검증하도록 갱신
(`test_cancelled_completion_still_publishes_done`). agent 전체 테스트 375개 통과, 라이브
API(`POST /agent/approve` `decision:"cancelled"`) 재현으로 `done` 이벤트 정상 수신 확인.

## 3. 키워드 폴백 순서 이슈 (버그는 아니나 주의 필요)

**증상**: `wf_set_default_account`의 공식 예시 발화(workflows.yaml `example_utterance`)인
"앞으로 송금은 카카오뱅크로 나가게 해줘"를 그대로 입력하면 `wf_external_transfer`(타인 송금)로
잘못 라우팅됨.

**원인**: `agent/src/agent/workflow_matcher.py`의 `_KEYWORD_RULES`는 LLM 의도 분류 실패 시(예:
`OPENAI_API_KEY` 미설정) 사용하는 순서 기반 폴백 규칙. "송금" 키워드가 `wf_external_transfer` 규칙에
있고 리스트 맨 앞이라, "송금"이라는 단어가 들어간 모든 발화(공식 예시 발화 포함)가 실제 의도와
무관하게 먼저 걸림.

**근본 원인**: 로컬 환경에 `OPENAI_API_KEY`가 비어 있어(`.env:20`) LLM 분류 경로 자체가 항상
예외로 빠지고, 좁은 키워드 폴백만 상시 작동 중임(`agent/src/agent/llm.py:99` 참고). §2-5의
`recipient_name_hint` 추출 실패도 근본 원인은 동일함.

**임시 조치(적용됨)**: `wf_account_list` 관련 폴백 키워드에 "계좌 확인", "계좌를 보여", "계좌 보여",
"내 계좌" 추가(`agent/src/agent/workflow_matcher.py:40-52`) — "계좌 확인"류 발화 무응답 문제 해결.
`wf_set_default_account` vs `wf_external_transfer` 순서 문제, §2-5 이름 추출 문제는 **미해결** —
근본 해결은 키워드/정규식 폴백 땜빵이 아니라 `OPENAI_API_KEY` 설정으로 LLM 경로를 살리는 것.

## 4. 참고 — 로컬(비-docker) 실행 시 필요했던 env override

문서화 범위는 아니나 재현 시 참고: `.env`가 docker 컨테이너 hostname(`postgres`, `redis`,
`agent-service`, `mock-financial-service`, `backend-gateway`) 기준이라, 로컬에서 각 서비스를
직접 실행할 땐 `DATABASE_URL`, `REDIS_CACHE_URL`, `REDIS_STREAM_URL`, `AGENT_SERVICE_URL`,
`MOCK_FINANCIAL_SERVICE_URL`, `BACKEND_SERVICE_TOKEN`을 `localhost` 기준으로 override 필요.
또한 `main`↔`feat/erase_backend_agent_mocking` 브랜치 전환 시 Postgres `alembic_version` 스탬프가
두 브랜치의 서로 다른 migration head와 어긋나(317ff87f3f12 vs 2ea0ff81f9c5) 재스탬프가 필요했음.
