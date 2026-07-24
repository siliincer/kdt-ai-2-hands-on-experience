# Agent 문서 안내

현재 Agent 구현은 관리시트 V3와 계약 기반 Runtime만 사용합니다.

## 계약 정본

1. `agent-management-sheet-v3.xlsx`
   - Workflow, Step, Route, State와 Step Data Mapping
2. `agent-tools-api-spec.md`
   - Agent가 호출하는 Backend Tool API
3. `agent-ui-hitl-contract.md`
   - Webhook UI와 입력·승인·인증 Resume Payload
4. `agent-backend-integration-contract.md`
   - Agent, Backend와 Frontend의 통신 및 책임 경계

기계 판독 계약은 `../contracts/workflow-contracts.json`이며 관리시트에서
생성합니다. JSON과 XLSX를 동시에 수동 수정하지 않습니다.

```bash
cd agent
uv run python scripts/export_workflow_contracts.py --check
uv run python scripts/export_workflow_contracts.py --workflow wf_balance_inquiry
```

## 구현 문서

- `agent-workflow-development-guide.md`
  - Workflow 구현 파일, 공용 파일, 테스트와 PR 기준
- `agent-team-integration-implementation-roadmap.md`
  - Workflow별 구현 결정과 전환 과정
- `agent-workflow-parallel-development-plan.md`
  - 역할 분담과 병렬 개발 방식
- `agent-demo-scenario.md`
  - 데모 데이터와 사용자 시나리오

## 연동 문서

- `agent-backend-integration-contract.md`
  - 실행 시작, Resume, Webhook, SSE와 종료 책임
- `agent-tools-api-spec.md`
  - Backend Tool API 요청·응답과 멱등성
- `agent-ui-hitl-contract.md`
  - UI Metadata와 입력·승인·인증 계약
- `legacy-agent-cross-team-handoff.md`
  - 레거시 Agent 제거로 DevSecOps와 공통 설정에서 조정할 항목

## 현재 실행 기준

```text
Backend POST /internal/v1/executions
  -> application_runtime.py
  -> workflows/contract_agent.py
  -> workflows/<workflow_name>.py
  -> Backend Tool API와 Webhook
```

결과와 상호작용 요청은 Agent가 Backend Webhook으로 발행하고 Backend가 SSE로
Frontend에 중계합니다. 구형 Agent 직접 `/chat`, YAML 자동 Graph Builder,
내장 mock 원장은 현재 Runtime에 포함되지 않습니다.
