# Agent Workflow 병렬 개발 실행 계획

> 상태: 공동개발 운영 기준
>
> 대상: Agent, Backend, Frontend 개발자
>
> 목적: 확정된 Agent 연동 계약과 관리시트를 기준으로 여러 개발자가 Workflow를 병렬 구현하면서 중복 개발, 공용 파일 충돌과 Backend 연동 병목을 줄인다.
>
> 구체적인 파일 소유권, 구현 순서, 테스트 명령과 AI 에이전트 작업 규칙은 `agent-workflow-development-guide.md`를 따른다.

## 1. 목표

이번 개발의 일차 목표는 새로운 Workflow를 설계하는 것이 아니라 이미 확정한 계약을 코드로 구현하는 것이다.

- 관리시트의 Workflow, Step, Route와 State Mapping 구현
- `agent-tools-api-spec.md` 기준 Backend Tool 연동
- `agent-ui-hitl-contract.md` 기준 Webhook과 HITL Resume 구현
- Agent의 금융 원장 직접 접근 제거
- Mock Backend 기반 독립 테스트 후 실제 Backend 통합

계약 변경이 필요한 경우를 제외하고 구현 과정에서 문서와 변수명을 임의로 변경하지 않는다.

### 1.1 공통 개발 진입점

모든 Agent 개발자와 개발 에이전트는 작업 전에 `agent/AGENTS.md`를 읽는다. 관리시트는 다음 명령으로 검증하고, 자신이 담당한 Workflow 계약만 조회한다.

```bash
cd agent
uv run python scripts/export_workflow_contracts.py --check
uv run python scripts/export_workflow_contracts.py --workflow <workflow_id>
```

`agent/contracts/workflow-contracts.json`은 관리시트에서 자동 생성하는 기계 판독 계약이다. 직접 수정하지 않으며 관리시트와 불일치하면 Workflow 구현을 시작하지 않는다.

## 2. 구현 범위 확인

현재 관리시트의 Workflow Catalog에는 다음 Workflow가 정의되어 있다.

| 구분 | Workflow |
| --- | --- |
| 공통 진입 | `wf_global_agent_entry` |
| 조회 | `wf_account_list` |
| 조회 | `wf_balance_inquiry` |
| 조회 | `wf_transaction_history` |
| 조회 | `wf_period_amount_summary` |
| 설정 | `wf_set_default_account` |
| 설정 | `wf_set_account_alias` |
| 송금 | `wf_internal_transfer` |
| 송금 | `wf_external_transfer` |

개발 착수 전 기존 구현을 유지할 Workflow, 다시 구현할 Workflow와 이번 범위에서 제외할 Workflow를 표시한다. 팀에서 인식하는 대상 수와 관리시트의 Workflow 수가 다르면 이 목록을 기준으로 먼저 범위를 확정한다.

## 3. 병렬 개발 시 예상 문제

Workflow를 개발자별로 단순 배분하면 다음 문제가 발생할 수 있다.

- 같은 Backend API를 호출하는 Tool을 여러 방식으로 구현
- 인증 Header, Timeout, 재시도와 멱등성 정책 불일치
- 동일한 계좌 선택, 승인과 인증 흐름을 Workflow마다 중복 구현
- 공용 `workflows.yaml`, `bank_tools.py`, `registry.py` 동시 수정으로 충돌 발생
- Agent 개발자 세 명이 Backend·Frontend 담당자에게 각각 다른 요청 전달
- Backend API가 준비될 때까지 Agent 개발 전체가 대기

따라서 공통 실행 기반을 먼저 고정하고, 이후 기능군 단위로 병렬 개발한다.

## 4. 개발 전략

### 4.1 공통 기반 선행

Workflow 구현 전에 다음 공통 기능을 먼저 만든다.

| 공통 영역 | 제공 기능 |
| --- | --- |
| Workflow Runtime | 공통 State, Graph 생성, Workflow 등록과 Route 실행 |
| Backend Tool Client | 서비스 인증, 공통 Header, Timeout, 재시도, 멱등성, 오류 변환 |
| Webhook Adapter | Agent 이벤트와 UI Payload를 Backend Webhook으로 전송 |
| HITL Adapter | `input_request_id`, `ui_contract_id` 기반 중단과 Resume 처리 |
| 공통 Schema | Tool 요청·응답, Webhook, Resume과 업무 오류 모델 |
| Mock Backend | API별 정상·오류·Timeout 응답 제공 |
| Test Helper | Node, Route, Interrupt, Resume과 API 계약 테스트 지원 |

공통 기반이 합의되기 전에는 각 Workflow에서 별도의 HTTP Client, Resume 처리 또는 오류 체계를 만들지 않는다.

### 4.2 기능군별 병렬 구현

공통 기반이 병합된 뒤 공유 기능이 많은 Workflow끼리 묶어 개발한다.

| 담당 | 주요 구현 범위 | 함께 관리할 공통 기능 |
| --- | --- | --- |
| Agent 개발자 A | 글로벌 진입, 계좌 목록, 잔액, 거래내역, 기간 합계 | Workflow Runtime, 조회 공통 처리, 전체 통합 |
| Agent 개발자 B | 기본계좌 변경, 계좌 별칭 변경 | Confirmation 공통 처리와 설정 변경 오류 처리 |
| Agent 개발자 C | 본인송금, 타인송금 | 인증, Prepare·Execute, 수정과 재인증 공통 처리 |

송금 기능군의 작업량이 가장 크므로 설정 기능군이 먼저 완료되면 개발자 B가 Confirmation·Execute 통합 테스트와 송금 오류 분기 구현을 지원한다.

담당자는 해당 기능군의 구현과 테스트를 책임지지만 공통 계약을 단독으로 변경하지 않는다.

## 5. 구현 경계

### 5.1 Workflow가 담당하는 것

- 사용자 발화에서 필요한 힌트와 Slot 추출
- 누락된 입력 확인
- Backend Tool 요청값 구성
- Backend 결과에 따른 Route 선택
- UI 요청과 최종 결과 Webhook 발행
- 중단된 Workflow의 Resume 결과 반영

### 5.2 공통 Tool 계층이 담당하는 것

- Backend API 호출
- 서비스 인증과 공통 Header
- Timeout과 제한된 재시도
- 멱등성 키 생성과 유지
- 공통 응답 해석과 오류 변환
- 민감정보가 로그와 State에 남지 않도록 제한

### 5.3 Workflow에서 하지 않는 것

- 금융 원장 또는 Backend DB 직접 접근
- Frontend 직접 호출
- Workflow별 HTTP Client 재구현
- 잔액, 계좌 소유권, 승인과 인증 결과 자체 판정
- 사용자 입력 원문을 Backend 검증 없이 업무 State에 저장
- 별도 Audit API 호출

## 6. 중복 구현 방지 규칙

1. 하나의 `contract_id`는 하나의 Tool 함수와 연결한다.
2. Workflow Node에서 직접 HTTP 요청을 작성하지 않는다.
3. 공통 Header, 재시도와 멱등성은 Backend Tool Client에서만 처리한다.
4. Tool ID가 중복 등록되면 애플리케이션 시작 단계에서 실패시킨다.
5. 두 개 이상의 Workflow에서 반복되는 흐름만 공통 모듈 또는 Subgraph로 분리한다.
6. Workflow별 State는 관리시트의 Workflow Data Schema를 따른다.
7. Step의 입력과 출력 매핑은 Step Data Mapping을 따른다.
8. 공용 Registry와 Loader는 지정된 통합 담당자만 최종 수정한다.
9. 공통 계약 변경은 관련 담당자 리뷰 후 반영한다.

## 7. 권장 코드 구조

현재의 단일 `workflows.yaml`, `bank_tools.py`와 Registry에 변경이 집중되지 않도록 기능별 파일로 분리한다.

```text
agent/src/agent/
├── clients/
│   └── backend/
│       ├── base.py
│       ├── accounts.py
│       ├── transactions.py
│       ├── settings.py
│       └── transfers.py
├── runtime/
│   ├── graph_builder.py
│   ├── webhook.py
│   └── hitl.py
├── schemas/
│   ├── common.py
│   ├── agent_tools.py
│   └── webhook.py
├── workflows/
│   ├── account_list/
│   ├── balance_inquiry/
│   ├── transaction_history/
│   ├── period_amount_summary/
│   ├── set_default_account/
│   ├── set_account_alias/
│   ├── internal_transfer/
│   └── external_transfer/
└── tests/
```

실제 디렉터리 구조는 기존 코드와 패키지 의존성을 확인한 뒤 결정한다. 중요한 기준은 공통 계층과 Workflow 구현을 분리하여 서로 다른 담당자가 같은 파일을 반복 수정하지 않도록 하는 것이다.

## 8. Backend·Frontend 협업 방식

Backend·Frontend 담당자는 한 명이므로 Agent 팀의 요청 창구를 한 명으로 통일한다.

### 8.1 요청 단위

요청은 설명 문장보다 계약 ID를 기준으로 전달한다.

```text
계약 ID
요청·응답 예시
필수 오류 코드
사용 Workflow와 Step
Agent Mock 테스트 결과
통합이 필요한 시점
```

각 Agent 개발자가 Backend 담당자에게 개별적으로 다른 Payload나 Endpoint를 요청하지 않는다.

### 8.2 제공 순서

Backend·Frontend 연동은 다음 순서로 요청한다.

1. 조회 Tool API와 조회 결과 UI
2. 공통 사용자 입력 제출과 Agent Resume
3. 설정 변경 Prepare·Confirmation·Execute
4. 수취인 처리, 송금 Prepare, 추가 인증과 Execute

Agent 팀은 실제 API가 준비되기 전까지 Mock Backend를 사용한다. Backend가 제공되면 같은 계약 테스트를 실제 API에 적용한다.

## 9. 브랜치와 PR 운영

문서 브랜치를 기준으로 통합 브랜치를 만들고, 기능 브랜치는 통합 브랜치를 대상으로 PR을 생성한다.

```text
docs/agent-integration-specs-20260716
└── integration/agent-workflows
    ├── feat/agent-runtime-foundation
    ├── feat/agent-inquiry-workflows
    ├── feat/agent-setting-workflows
    └── feat/agent-transfer-workflows
```

권장 병합 순서는 다음과 같다.

1. 공통 Runtime과 Backend Client
2. Mock Backend와 공통 테스트 도구
3. 조회와 설정 Workflow
4. 송금 공통 처리와 본인송금
5. 타인송금
6. 전체 Workflow 통합 테스트

기능 브랜치끼리 직접 병합하지 않는다. 공통 변경은 통합 브랜치에 먼저 반영한 뒤 각 기능 브랜치가 다시 받아 사용한다.

## 10. 개발 단계

### 단계 0. 범위와 담당 확정

- 이번 구현 대상 Workflow 확정
- 공통 파일별 담당자 확정
- Backend·Frontend 단일 연락 담당자 지정
- API 제공 우선순위 확인

### 단계 1. 공통 기반 구현

- 기존 `prompt_for` 기반 중단 흐름 제거
- `input_request_id`, `ui_contract_id` 기반 Resume 구현
- Backend Tool Client와 공통 오류 모델 구현
- Webhook Adapter 구현
- Mock Backend와 테스트 Fixture 구현
- 잔액 조회를 기준 Workflow로 연결
- [x] Agent 서버 시작 시 모든 Workflow의 `contract_id` 등록 여부를 검증하고, 누락된 계약이 있으면 서버 시작을 실패 처리한다.
- [ ] TODO: MVP에서는 FastAPI `BackgroundTasks`를 사용하고, 작업 보존이나 부하 분산이 필요해지면 Redis Task Queue와 Celery 또는 Taskiq 전환을 검토한다.

### 단계 2. 기능군 병렬 개발

- 조회 Workflow 구현
- 설정 Workflow 구현
- 송금 Workflow 구현
- 각 기능군의 Node와 Route 테스트 작성

### 단계 3. 통합

- Workflow Registry 통합
- 공통 State와 Mapping 검증
- Workflow 간 Tool 중복 검사
- Mock Backend 기반 전체 시나리오 실행

### 단계 4. 실제 Backend 연동

- API 계약 테스트
- Webhook과 SSE 확인
- 입력, 승인과 인증 Resume 확인
- Timeout, 재시도와 멱등성 확인
- 민감정보와 로그 점검

## 11. Workflow 완료 기준

각 Workflow는 다음 조건을 모두 만족해야 완료로 본다.

- 관리시트의 모든 Step과 Route 구현
- State 필드와 Step Data Mapping 일치
- Backend Tool 요청·응답 Schema 일치
- 정상, 취소, 수정, 차단과 오류 Route 테스트
- HITL Workflow의 Interrupt와 Resume 테스트
- 변경 API의 멱등성과 1회 통신 재시도 테스트
- 민감정보가 Agent State와 로그에 저장되지 않음
- Mock Backend 기반 End-to-End 테스트 통과
- 실제 Backend가 제공된 경우 계약 테스트 통과

## 12. 협업 원칙

- 관리시트와 계약 문서를 구현의 기준으로 사용한다.
- Workflow별 편의를 위해 공통 변수명이나 Tool 계약을 바꾸지 않는다.
- 공통 코드 변경은 작은 PR로 먼저 공유한다.
- 기능 PR에는 구현한 Workflow, 사용한 계약 ID와 테스트한 Route를 명시한다.
- Backend 내부 구현 방식을 지정하지 않고 Agent에 필요한 입력·출력과 보장만 전달한다.
- 계약상 판단이 필요한 문제와 단순 구현 문제를 구분한다.

## 13. 착수 전 확정할 항목

- [ ] 이번 구현 대상 Workflow 목록
- [ ] Agent 개발자 A, B, C의 실제 담당자
- [ ] 공통 Runtime과 Registry 최종 담당자
- [ ] Backend·Frontend 연락 담당자
- [ ] 기능별 API 제공 우선순위
- [ ] Mock Backend 실행 방식
- [ ] 기능 PR의 대상 통합 브랜치
- [ ] 공통 테스트 명령과 CI 기준

이 항목을 확정한 뒤 공통 기반 PR부터 개발을 시작한다.
