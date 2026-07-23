# Agent Workflow 공동개발 가이드

> 상태: 현재 구현 기준 운영 문서
>
> 대상: Agent 개발자와 개발에 사용하는 AI 에이전트
>
> 목적: 여러 담당자가 Workflow를 병렬 구현하면서 계약 불일치, 공통 파일 충돌과 Tool 중복을 방지한다.

## 1. 시작 원칙

신규 Workflow 개발은 관리시트 V3와 Agent·Backend 계약을 구현하는 작업이다.

모든 사람과 AI 에이전트는 작업 시작 전에 다음을 지킨다.

1. `agent/AGENTS.md`를 읽는다.
2. 이 문서에서 담당 파일과 금지 파일을 확인한다.
3. 담당 `workflow_id`의 생성 계약을 조회한다.
4. 계약 충돌이 없을 때만 코드를 수정한다.
5. 다른 담당자의 변경과 사용자 작업을 덮어쓰지 않는다.

## 2. 정본과 우선순위

| 영역 | 정본 |
| --- | --- |
| Workflow, Step, Route와 State Mapping | `agent-management-sheet-v3.xlsx` |
| Backend Tool API | `agent-tools-api-spec.md` |
| UI Payload와 Resume | `agent-ui-hitl-contract.md` |
| 시스템 책임과 통신 방향 | `agent-backend-integration-contract.md` |
| 기계 판독 Workflow 계약 | `contracts/workflow-contracts.json` |

`workflow-contracts.json`은 관리시트에서 생성하는 파일이므로 직접 수정하지 않는다.

```bash
cd agent
uv run python scripts/export_workflow_contracts.py --check
uv run python scripts/export_workflow_contracts.py --workflow <workflow_id>
```

계약이 서로 다르면 임의로 구현하지 않는다. Workflow ID, Step ID, Contract ID와 충돌 내용을 기록하고 통합 담당자에게 전달한다.

## 3. 현재 공동 기반

| 영역 | 경로 | 역할 |
| --- | --- | --- |
| Backend Client | `src/agent/clients/backend/` | 인증 Header, Timeout, 재시도와 오류 변환 |
| API Schema | `src/agent/contracts/` | Agent Tool, Webhook 요청·응답 검증 |
| Runtime | `src/agent/runtime/` | 실행 시작, Interrupt, 검증된 Resume과 State 반영 |
| Tool Registry | `src/agent/tools/` | Contract ID와 공통 Backend Tool 연결 |
| Contract Store | `src/agent/workflow_contracts.py` | 생성 Manifest 조회 |
| Testbed Harness | `src/agent/testing/workflow_testbed.py` | 공통 실행과 HTTP 이력 확인 |
| Mock Backend | `src/agent/testing/mock_backend.py` | 계약 기반 Mock 응답과 요청·응답 기록 |

`wf_balance_inquiry`가 기준 구현이다.

| 기준 산출물 | 경로 |
| --- | --- |
| Workflow | `src/agent/workflows/balance_inquiry.py` |
| Workflow 전용 Testbed Factory | `src/agent/testing/balance_inquiry.py` |
| 자동 테스트 | `tests/test_balance_reference_workflow.py` |
| 단계별 Notebook | `notebooks/testbed/01_balance_inquiry_testbed.ipynb` |

## 4. 파일 소유권

### 4.1 Workflow 담당자가 수정하는 파일

```text
src/agent/workflows/<workflow_name>.py
src/agent/testing/<workflow_name>.py
tests/test_<workflow_name>_reference_workflow.py
notebooks/testbed/<number>_<workflow_name>_testbed.ipynb
```

한 기능 브랜치는 원칙적으로 하나의 Workflow 또는 강하게 결합된 한 기능군만 포함한다.

### 4.2 통합 담당자가 관리하는 공통 파일

다음 파일은 여러 기능 브랜치가 동시에 수정하지 않는다.

```text
src/agent/clients/backend/
src/agent/contracts/
src/agent/runtime/
src/agent/testing/workflow_testbed.py
src/agent/testing/mock_backend.py
src/agent/testing/__init__.py
src/agent/tools/backend_agent_tools.py
src/agent/tools/contract_registry.py
src/agent/workflow_contracts.py
src/agent/workflows/__init__.py
src/agent/internal_execution_api.py
src/agent/main.py
scripts/export_workflow_contracts.py
contracts/workflow-contracts.json
pyproject.toml
../uv.lock
```

Workflow 구현에 공통 변경이 먼저 필요하면 기능 브랜치에서 우회 구현하지 않는다. 변경 요구를 통합 담당자에게 전달하고 공통 기반 PR을 먼저 병합한다.

### 4.3 제거된 구형 경로

```text
src/agent/bank_client.py
src/agent/data/mock_bank.py
src/agent/tools/bank_tools.py
src/agent/tools/registry.py
src/agent/graph.py
src/agent/subgraph_builder.py
```

이 파일과 Agent 직접 `POST /chat` 경로는 V3 Runtime 전환 후 삭제되었다.
신규 Workflow에서 같은 이름이나 역할의 호환 계층을 다시 만들지 않는다.

`src/agent/config/guardrail_rules.yaml`과 `contracts/workflow-contracts.json`도 직접
편집하지 않는다. 계약 생성 절차를 통해 갱신한다.

## 5. 브랜치와 PR

기능 브랜치는 최신 `main`에서 시작한다.

- 기능 브랜치의 PR 대상은 `main`이다.
- 기능 브랜치끼리 직접 병합하지 않는다.
- 공통 변경은 작은 선행 PR로 먼저 반영한 뒤 기능 브랜치가 다시 받는다.
- 계약 문서 변경과 Workflow 구현을 같은 PR에 섞지 않는다.
- 관련 없는 파일, 개인 IDE 설정과 Notebook 실행 출력은 커밋하지 않는다.
- 커밋, Push와 PR 생성은 담당 개발자가 변경 범위를 확인한 후 수행한다.

## 6. Workflow 구현 순서

### 6.1 계약을 작업 목록으로 변환

담당 Workflow의 생성 계약에서 다음을 정리한다.

- Step 순서와 `interaction_mode`
- 각 Step의 입력·출력 State Key
- Route와 종료 조건
- API·UI `contract_id`
- 취소, 오류, 수정과 재인증 Route

### 6.2 Workflow 모듈 작성

`src/agent/workflows/<workflow_name>.py`에 Graph를 작성한다.

- `agent_internal`: Slot 추출과 Route 입력만 수행한다.
- `backend_tool_api`: `ContractToolRegistry`를 통해 호출한다.
- `webhook`: 공통 Webhook Builder와 Client를 사용한다.
- `webhook_then_resume`: Webhook Envelope로 중단하고 검증된 Resume만 반영한다.
- Node에서 `httpx`를 직접 사용하지 않는다.
- Backend가 반환한 업무 Outcome을 다시 추론하지 않는다.

### 6.3 Workflow 전용 Testbed Factory 작성

`src/agent/testing/<workflow_name>.py`에서 공통 `create_workflow_testbed()`에 Graph Factory를 주입한다.

공통 `workflow_testbed.py`에 Workflow별 Factory를 계속 추가하지 않는다. 이 분리를 통해 병렬 개발자가 같은 파일을 수정하는 상황을 줄인다.

### 6.4 자동 테스트 작성

최소한 다음 Scenario를 검증한다.

- 정상 완료
- Backend 자동 확정과 사용자 선택 분기
- 취소와 종료
- Backend 업무 오류와 계약 오류
- Interrupt와 올바른 Resume
- 잘못된 ID와 오래된 Resume 거부
- 허용된 1회 재시도
- 변경 API의 멱등성
- 민감정보가 State와 일반 로그에 남지 않음
- 예상하지 않은 API가 호출되지 않음

### 6.5 단계별 Notebook 작성

Notebook은 자동 테스트를 대체하지 않는다. 사람이 다음 경계를 확인하는 실행 문서다.

```text
사용자 입력
→ Agent 내부 추출
→ Tool API 요청·응답
→ Webhook Payload
→ 중단 State
→ Backend 검증 후 Resume
→ 완료 State와 결과 Webhook
```

Notebook은 공통 Harness와 Workflow 전용 Testbed Factory를 import한다. Workflow 로직을 Notebook 안에 다시 구현하지 않는다.

### 6.6 통합 담당자에게 인계

기능 브랜치는 Workflow 모듈을 직접 import하는 테스트로 독립 검증한다. 공통 `__init__.py`, 애플리케이션 Workflow Registry와 최상위 Graph 등록은 기능 담당자가 각자 수정하지 않는다.

PR에 다음 등록 요청을 남기고 통합 담당자가 한 번에 반영한다.

```text
등록할 workflow_id:
Workflow Graph Factory:
사용 Tool ID:
사용 API/UI Contract ID:
진입 조건:
```

통합 담당자는 중복 Tool, 누락 Workflow와 전체 Route를 검사한 뒤 공통 Registry를 갱신한다.

## 7. Backend·Frontend 협업

Agent 팀은 Backend 내부 구조를 지정하지 않는다. 필요한 계약과 보장만 전달한다.

```text
contract_id
Method와 Path
요청·응답 예시
필수 업무 Outcome과 오류
사용 Workflow와 Step
Mock Backend 테스트 결과
통합이 필요한 시점
```

Backend·Frontend 연락 창구는 한 명으로 통일한다. 각 Workflow 담당자가 서로 다른 임시 필드나 Endpoint를 개별 요청하지 않는다.

## 8. 사람과 AI 에이전트의 작업 계약

AI 에이전트에게 작업을 맡길 때 다음 정보를 함께 제공한다.

```text
담당 workflow_id:
허용된 수정 파일:
사용할 API/UI contract_id:
구현할 Route:
이번 작업에서 제외할 공통 파일:
필수 테스트:
```

AI 에이전트는 다음 행동을 해야 한다.

1. `agent/AGENTS.md`와 이 문서를 먼저 읽는다.
2. Manifest에서 담당 Workflow만 조회한다.
3. 작업 시작 전에 수정할 파일을 보고한다.
4. 사용자와 다른 담당자의 변경을 보존한다.
5. 계약에 없는 필드, Route와 Endpoint를 만들지 않는다.
6. 공통 변경이 필요하면 기능 코드로 우회하지 않고 필요성을 보고한다.
7. 구현 후 계약 ID, 구현 Route와 테스트 결과를 보고한다.

다음 조건에서는 코드를 임의로 완성하지 않고 작업을 중단한다.

- 관리시트와 API·UI 명세의 필드가 충돌
- 필요한 Contract ID가 Manifest에 없음
- Backend 검증 책임을 Agent가 대신해야만 구현 가능
- 담당 범위를 넘어 공통 Runtime 계약을 바꿔야 함
- 다른 담당자의 변경을 덮어써야만 진행 가능

## 9. 필수 검증

레포 루트에서 환경을 준비한다.

```bash
uv sync
```

담당 Workflow 계약과 테스트를 확인한다.

```bash
cd agent
uv run python scripts/export_workflow_contracts.py --check
uv run python scripts/export_workflow_contracts.py --workflow <workflow_id>
uv run pytest tests/test_<workflow_name>_reference_workflow.py
```

변경한 Python 파일은 Ruff와 Pyright 오류가 없어야 한다.

```bash
uv run ruff check \
  src/agent/workflows/<workflow_name>.py \
  src/agent/testing/<workflow_name>.py \
  tests/test_<workflow_name>_reference_workflow.py

uv run pyright \
  src/agent/workflows/<workflow_name>.py \
  src/agent/testing/<workflow_name>.py \
  tests/test_<workflow_name>_reference_workflow.py
```

PR 전에는 전체 Agent 테스트를 실행한다.

```bash
uv run pytest
```

전체 프로젝트 Pyright에는 기존 Demo 코드의 선행 오류가 남아 있다. 신규·변경 파일은 0건을 유지하고 전체 오류 수를 증가시키지 않는다. 통합 담당자가 기존 오류 정리 범위를 별도 관리한다.

## 10. 완료 기준

- [ ] 담당 Workflow의 모든 Step과 Route가 구현됨
- [ ] State와 Step Data Mapping이 Manifest와 일치함
- [ ] API·UI Contract ID가 계약 문서와 일치함
- [ ] Backend 검증 책임을 Agent가 중복 수행하지 않음
- [ ] Mock Backend 정상·취소·오류 Scenario가 통과함
- [ ] Interrupt와 Resume 식별자 검증이 통과함
- [ ] 민감정보가 State와 로그에 남지 않음
- [ ] Workflow 전용 Testbed Factory가 공통 Harness와 분리됨
- [ ] 단계별 Notebook 또는 동등한 실행 자료가 있음
- [ ] 대상 Ruff와 Pyright가 0건임
- [ ] 전체 Agent pytest가 통과함
- [ ] 실제 Backend 미연동 범위가 PR에 명시됨

## 11. 작업 완료 보고 형식

```text
구현 Workflow:
구현 Step과 Route:
사용 API Contract:
사용 UI Contract:
변경한 Workflow 전용 파일:
변경한 공통 파일:
Mock 테스트:
실제 Backend 연동:
남은 계약 질문:
```

이 형식을 PR 설명과 담당자 인계에 함께 사용한다.
