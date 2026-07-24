# Agent 레거시 제거 후 타 팀 조정 항목

> 기준일: 2026-07-23
>
> 목적: Agent V3 Runtime에서 사용하지 않는 구형 코드를 제거한 뒤, Agent 범위
> 밖에서 남은 직접 참조와 설정을 각 담당 팀이 정리할 수 있도록 전달한다.

## 1. Agent 변경 범위

이 정리 브랜치는 Agent 직접 `/chat`을 닫고 V3 Manifest로 분류 기준을 바꾸는
선행 변경을 전제로 한다. 따라서 해당 변경이 먼저 병합되어야 한다.

Agent의 서비스 실행 경로는 다음으로 고정된다.

```text
Backend POST /internal/v1/executions
  -> Agent ExecutionRuntime
  -> workflows/contract_agent.py
  -> workflows/<workflow_name>.py
  -> Backend Tool API와 Webhook
```

다음 구형 경로는 제거된다.

```text
Agent POST /chat
  -> service.py
  -> graph.py
  -> subgraph_builder.py
  -> tools/registry.py
  -> tools/bank_tools.py
  -> bank_client.py
  -> data/mock_bank.py
```

구형 `config/workflows.yaml`, `tasks.yaml`, `tools.yaml`,
`risk_levels.yaml`과 동기화 스크립트도 제거된다. 관리시트 V3의 기계 판독
산출물은 `contracts/workflow-contracts.json`이다.

## 2. DevSecOps 영향

### 2.1 직접 깨지는 파일

다음 파일은 제거된 Agent 모듈을 직접 import하거나 구형 `/chat`을 실행한다.

| 파일 | 현재 의존성 | 영향 |
| --- | --- | --- |
| `security/redteam/runner/local_agent_app.py` | `agent.schemas`, `agent.service`, `agent.tools.bank_tools`, `agent.data.mock_bank` | import와 로컬 App 시작 실패 |
| `security/redteam/tests/test_agent_integration.py` | `agent.schemas.ChatRequest`, `ChatResponse` | 테스트 수집 단계 실패 |
| `security/redteam/runner/managed_agent.py` | `local_agent_app`, `BANK_CLIENT=local` | 관리 프로세스 시작 실패 |
| `security/redteam/config.py` | 기본 `chat_path=/chat` | 현재 Agent API와 불일치 |
| `security/redteam/config.example.yaml` | `chat_path: /chat` | 실행 예시 불일치 |

단순히 `/chat`을 `/internal/v1/executions`로 바꾸는 것만으로는 해결되지 않는다.
최신 API는 실행을 접수한 뒤 결과·입력·승인·인증을 Webhook과 Resume으로
처리하므로 동기 `ChatResponse` 계약이 없다.

### 2.2 권장 전환 경계

- 결정적 Workflow 보안 검증은 현재
  `security.redteam.runner.agent_reference`와 Agent의 계약 기반 Testbed를 사용한다.
- 실제 서비스 경계 검증은 Backend의 `/api/v1/chat`에서 실행을 시작하고
  Webhook에서 SSE로 전달되는 이벤트를 관찰한다.
- 입력·승인·인증은 Backend 검증 API를 거쳐 Agent Resume으로 전달한다.
- 원장 변경 증거는 Agent의 내장 `mock_bank`가 아니라 Backend 또는
  mock-financial-service의 테스트 경계에서 수집한다.
- LLM 호출 증거가 필요하면 구형 Agent App 전체를 복원하지 말고 현재 `agent.llm`
  경계에 한정한 추적 Adapter를 사용한다.

### 2.3 보안 증거 revision

`security/redteam/reference_evidence_manifest.yaml`과
`security/redteam/workflow_coverage.yaml`은 검증된 Agent commit을 고정한다.
Agent 정리 PR이 병합된 뒤 현재 계약 기반 Reference Case를 다시 실행하고, 결과가
동일하다는 것을 확인한 commit으로 두 파일의 revision을 함께 갱신해야 한다.

### 2.4 현재 브랜치에서 확인한 실패

다음 명령은 `agent.schemas` 직접 import 때문에 테스트 수집 단계에서 실패한다.

```bash
uv run pytest security/redteam/tests/test_agent_integration.py --collect-only -q
```

저장소 전체 `uv run pyright`에서도 다음 두 파일에 `reportMissingImports`가
추가로 발생한다.

- `security/redteam/runner/local_agent_app.py`
- `security/redteam/tests/test_agent_integration.py`

Agent 정리 PR에서는 타 팀 파일을 함께 고치지 않는다. DevSecOps 전환 PR이 준비되기
전에는 저장소 전체 Security 테스트와 Pyright를 병합 조건으로 통과할 수 없다.

## 3. 공통 설정과 배포 영향

다음 설정은 Agent가 더 이상 읽지 않는다.

| 위치 | 정리 후보 | 주의사항 |
| --- | --- | --- |
| `docker-compose.yml`의 `agent.environment` | `BANK_CLIENT`, `MOCK_FINANCIAL_SERVICE_URL` | Agent 컨테이너에서만 제거 |
| `.env.example` | `BANK_CLIENT` | DevSecOps 구형 실행기 전환 후 제거 |
| Security 실행 환경 | `BANK_CLIENT=local` 강제 | 계약 기반 Testbed 또는 통합 경로로 교체 |

`MOCK_FINANCIAL_SERVICE_URL`은 Backend의 금융 Client가 계속 사용하므로 저장소
전체 환경변수에서 삭제하면 안 된다. Agent 컨테이너로 전달하는 항목만 제거한다.

## 4. Backend와 Frontend 영향

Backend와 Frontend는 제거된 Python 모듈을 직접 import하지 않으므로 소스 컴파일
영향은 없다.

- Frontend는 계속 Backend의 `/api/v1/chat`을 호출한다.
- Backend는 `services/agent_client.py`에서 Agent의
  `/internal/v1/executions`와 Resume API를 호출한다.
- Backend의 `/api/v1/chat`은 구형 Agent `/chat`과 이름만 비슷하며 제거 대상이
  아니다.
- Backend에 남아 있는 Mock Agent 파일과 오래된 설명 문서는 Backend 담당 범위로
  별도 정리한다.

## 5. 문서와 E2E 정리 후보

다음 Agent 외부 문서는 구형 동기 `/chat` 또는 내장 원장을 설명할 수 있으므로
각 담당자가 최신 통합 경로 기준으로 확인한다.

- `security/redteam/AGENT_INTEGRATION.md`
- `security/redteam/README.md`
- `security/redteam/READ_WORKFLOW_CASES.md`
- `security/redteam/WORKFLOW_COVERAGE.md`
- `e2e/README.md`
- 저장소 루트의 배포·로컬 개발 문서

Backend의 `/api/v1/chat`을 가리키는 E2E 설명은 유효하다. Agent 서버의 직접
`/chat` 또는 `BANK_CLIENT=local`을 가리키는 설명만 구형이다.

## 6. 권장 적용 순서

1. 최신 Workflow 진입을 강제하는 Agent PR을 먼저 병합한다.
2. Agent 레거시 제거 PR의 삭제 목록을 DevSecOps 담당자에게 공유한다.
3. DevSecOps가 로컬 `/chat` 실행기와 관련 테스트를 계약 기반 경계로 전환한다.
4. 공통 Compose와 `.env.example`에서 Agent 전용 구형 변수를 제거한다.
5. 보안 Reference Case를 재실행하고 Agent revision을 갱신한다.
6. FE-BE-Agent 통합테스트와 Security 테스트를 함께 통과시킨 뒤 레거시 제거를
   최종 병합한다.
