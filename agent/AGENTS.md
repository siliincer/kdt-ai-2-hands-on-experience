# Agent 구현 공통 규칙

> 적용 범위: `agent/` 아래의 모든 문서, 코드와 테스트
>
> 목적: 여러 개발자와 개발 에이전트가 동일한 계약과 구현 경계를 사용한다.

## 1. 작업 전 확인 순서

다음 파일을 순서대로 확인한다.

1. `docs/agent-management-sheet-v3.xlsx`
   - Workflow, Step, Route, State와 Step Data Mapping의 정본
2. `docs/agent-tools-api-spec.md`
   - Agent가 호출하는 Backend Tool API 계약
3. `docs/agent-ui-hitl-contract.md`
   - Webhook UI Payload와 사용자 입력·승인·인증 Resume 계약
4. `docs/agent-backend-integration-contract.md`
   - Agent, Backend와 Frontend의 책임 경계
5. `docs/agent-team-integration-implementation-roadmap.md`
   - Workflow별 구현 결정과 전환 계획
6. `docs/agent-workflow-parallel-development-plan.md`
   - 역할 분담, 브랜치와 병렬 개발 방식
7. `docs/agent-workflow-development-guide.md`
   - 사람과 AI 에이전트가 따르는 파일 소유권, 구현 순서와 완료 기준

개발 에이전트는 전체 XLSX를 임의로 해석하지 않는다. 먼저 다음 명령으로 생성된 기계 판독 계약이 최신인지 확인한다.

```bash
cd agent
uv run python scripts/export_workflow_contracts.py --check
uv run python scripts/export_workflow_contracts.py --workflow wf_balance_inquiry
```

생성 파일은 `contracts/workflow-contracts.json`이다. 이 파일은 직접 수정하지 않는다.

## 2. 계약 우선순위

문서가 다르게 보이면 다음 기준을 적용한다.

1. Workflow 구조와 State Mapping은 관리시트
2. Backend 요청·응답은 Agent Tool API 명세
3. UI와 Resume Payload는 UI·HITL 계약
4. 시스템 책임과 통신 방향은 Agent·Backend 연동 계약

계약 사이에 실제 충돌이 있으면 임의로 필드나 Route를 선택하지 않는다. 충돌 위치, 관련 Workflow와 Step을 기록하고 작업을 중단한 뒤 팀에 확인한다.

## 3. 구현 경계

Agent가 담당한다.

- 사용자 의도 분류와 Workflow 선택
- 사용자 발화의 힌트와 Slot 추출
- 관리시트에 정의된 Step과 Route 실행
- Backend Tool 요청값 구성과 결과 Route 선택
- Webhook 이벤트 발행
- Backend가 검증한 Resume 값의 State 반영

Agent가 담당하지 않는다.

- 금융 원장 또는 Backend DB 직접 접근
- Frontend 직접 호출
- 계좌 소유권, 잔액 충분 여부, 한도와 정책 자체 판정
- 승인 또는 추가 인증 결과 자체 판정
- 별도 Audit API 호출
- 전체 계좌번호, 인증 원문과 민감정보의 State 저장
- 인증이나 Confirmation 상태 Polling

## 4. State와 Resume 규칙

- State 필드는 관리시트의 Workflow Data Schema에 선언된 이름을 그대로 사용한다.
- 업무 State 이름에 임의의 점 구분 접두어를 추가하지 않는다.
- Step 입력과 출력은 Step Data Mapping을 따른다.
- 일반 입력은 `input_request_id`와 `ui_contract_id`로 연결한다.
- `prompt_for`는 새 Webhook, Resume과 State 계약에 사용하지 않는다.
- Backend가 검증한 Resume 값을 Agent가 다시 Backend에 검증 요청하지 않는다.
- 신규 수취 계좌 원문은 저장하지 않고 `to_recipient_candidate_id`만 사용한다.
- 취소 결과가 정의된 Step은 추가 이벤트를 중복 전송하지 않고 계약 Route로 종료한다.

## 5. Step 구현 규칙

관리시트의 `interaction_mode`에 따라 구현 경계를 고정한다.

| interaction_mode | 구현 방식 |
| --- | --- |
| `agent_internal` | Agent 내부 Node 또는 Route 함수만 실행 |
| `backend_tool_api` | 공통 Backend Tool Client를 통해 계약 API 호출 |
| `webhook` | 공통 Webhook Adapter로 이벤트를 전송하고 계속 진행 또는 종료 |
| `webhook_then_resume` | Webhook 전송 후 중단하고 Backend의 검증된 Resume으로 재개 |

- Workflow Node에서 `httpx`를 직접 사용하지 않는다.
- 하나의 `contract_id`는 하나의 Tool 구현만 가진다.
- Tool ID 중복은 애플리케이션 시작 또는 테스트 단계에서 실패해야 한다.
- 두 개 이상의 Workflow에서 반복되는 처리만 공통 함수 또는 Subgraph로 분리한다.
- 공통 코드를 먼저 변경해야 하면 작은 선행 PR로 분리한다.

## 6. Backend Tool Client 규칙

- 공통 인증 Header, Request ID, Timeout과 오류 변환은 Base Client가 담당한다.
- 재시도는 계약에서 허용한 오류에 한해 최대 1회 수행한다.
- 같은 논리 요청의 통신 재시도는 같은 Body와 멱등성 키를 유지한다.
- 사용자 수정이나 재인증처럼 새로운 논리 요청은 새로운 멱등성 키를 사용한다.
- Workflow는 HTTP 상태 코드가 아니라 정규화된 업무 결과로 Route를 선택한다.
- 실제 Backend가 준비되지 않은 API는 같은 요청·응답 Schema를 사용하는 Mock Transport로 테스트한다.

## 7. 공용 파일과 기능 파일

다음 파일은 여러 Workflow가 공유하므로 지정된 통합 담당자만 최종 수정한다.

- 공통 State와 Schema
- Graph Builder와 Workflow Loader
- Backend Base Client
- Webhook과 HITL Adapter
- Tool과 Workflow Registry
- 계약 추출·검증 스크립트

Workflow 담당자는 자신의 Workflow 모듈과 테스트를 우선 수정한다. 공용 파일 변경이 필요하면 변경 목적과 영향을 먼저 공유한다.

Workflow별 Testbed Factory는 `testing/<workflow_name>.py`에 둔다. 공통 `testing/workflow_testbed.py`와 `testing/mock_backend.py`는 통합 담당자가 관리한다. 신규 Workflow를 위해 공통 Harness에 Workflow별 분기를 추가하지 않는다.

신규 계약 기반 Workflow는 다음 파일을 기본 작업 단위로 사용한다.

```text
workflows/<workflow_name>.py
testing/<workflow_name>.py
tests/test_<workflow_name>_reference_workflow.py
notebooks/testbed/<number>_<workflow_name>_testbed.ipynb
```

## 8. 금지된 우회 구현

- 기존 `bank_client.py` 또는 Mock 원장을 신규 Workflow의 금융 처리 경로로 사용
- `bank_tools.py`에 신규 Workflow 기능을 계속 누적
- API 명세와 다른 임시 필드명 추가
- Backend 미구현을 이유로 Workflow 내부에 금융 판단 로직 추가
- UI Payload를 자유 형식 `dict`로만 처리하고 계약 검증 생략
- 오류를 일반 `Exception` 문자열로만 반환
- 계약 파일과 생성 Manifest를 동시에 수동 수정

## 9. 필수 테스트

Workflow별로 다음을 검증한다.

- 모든 Step과 Route 도달 가능 여부
- 정상, 취소, 수정, 차단과 오류 Route
- Tool 요청·응답 Schema
- Interrupt와 Resume
- Timeout과 허용된 1회 재시도
- 변경 API의 멱등성
- 민감정보가 State와 로그에 남지 않는지 여부
- Mock Backend 기반 End-to-End 흐름

Python 변경 후 최소한 다음 검증을 실행한다.

```bash
cd agent
uv run python scripts/export_workflow_contracts.py --check
uv run pytest
uv run ruff check <변경한 Python 파일>
uv run pyright <변경한 Python 파일>
```

전체 Pyright에는 기존 Demo 코드의 선행 오류가 남아 있다. 신규·변경 파일은 0건을 유지하고 전체 오류 수를 증가시키지 않는다.

## 10. 완료 보고

다음 내용을 함께 보고한다.

- 구현한 Workflow와 Step
- 사용한 API·UI `contract_id`
- 변경한 공용 파일
- 실행한 테스트와 결과
- 실제 Backend 미연동 항목
- 확인이 필요한 계약 충돌 또는 가정

문서나 관리시트 변경이 필요하지 않다면 구현 편의를 이유로 계약 문서를 수정하지 않는다.
