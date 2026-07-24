# Agent Runtime

이 디렉터리는 관리시트 V3 계약을 실행하는 LangGraph 금융 Agent입니다.
Frontend는 Agent를 직접 호출하지 않고 Backend의 채팅·입력·승인·인증 API를
사용합니다.

## 실행 경로

```text
Frontend
  -> Backend POST /api/v1/chat
  -> Agent POST /internal/v1/executions
  -> 계약 기반 상위 Graph
  -> 업무별 workflows/*.py
  -> Backend /api/v1/agent-tools/*
  -> Agent Webhook
  -> Backend Redis/SSE
  -> Frontend
```

사용자 입력·승인·인증으로 중단된 실행은 Backend가 검증한 뒤 다음 API로
재개합니다.

```text
POST /internal/v1/executions/{agent_thread_id}/resume
```

Agent 서버가 제공하는 엔드포인트는 다음과 같습니다.

- `GET /health`
- `POST /internal/v1/executions`
- `POST /internal/v1/executions/{agent_thread_id}/resume`

구형 Agent 직접 채팅 `POST /chat`은 제공하지 않습니다. 금융 데이터는 내장
mock 원장이 아니라 Backend Tool API를 통해서만 조회하거나 변경합니다.

## 현재 구조

```text
src/agent/
├── main.py                    # FastAPI와 Runtime lifespan
├── application_runtime.py     # 계약 Store, Tool Registry, Graph 조립
├── internal_execution_api.py  # Backend 전용 Start/Resume API
├── workflow_contracts.py      # 생성된 V3 Manifest 조회
├── workflow_matcher.py        # Manifest catalog 기반 업무 분류
├── runtime/                   # 실행, Resume, 완료·실패 Webhook 경계
├── clients/backend/           # Backend Tool/Webhook HTTP Client
├── contracts/                 # Agent Tool과 Webhook Schema
├── tools/                     # contract_id와 Tool 구현 연결
├── workflows/                 # 업무별 명시적 LangGraph
└── testing/                   # Mock Backend 기반 Workflow Testbed
```

Workflow 구조와 State Mapping의 정본은
`docs/agent-management-sheet-v3.xlsx`이며 생성 결과는
`contracts/workflow-contracts.json`입니다. 생성 파일을 직접 수정하지 않습니다.

## 실행

Agent Runtime 필수 환경변수:

```dotenv
BACKEND_BASE_URL=http://localhost:8000
AGENT_SERVICE_TOKEN=
AGENT_WEBHOOK_SECRET=
```

저장소 루트에서:

```bash
uv sync --all-groups
uv run uvicorn agent.main:app --host 0.0.0.0 --port 8001
```

필수 검증:

```bash
cd agent
uv run python scripts/export_workflow_contracts.py --check
uv run pytest
uv run ruff check src tests
uv run pyright src tests
```

구현 규칙과 계약 우선순위는 [AGENTS.md](AGENTS.md), 문서 위치는
[docs/README.md](docs/README.md)를 참고합니다. 레거시 제거로 다른 팀이
조정해야 할 항목은
[legacy-agent-cross-team-handoff.md](docs/legacy-agent-cross-team-handoff.md)에
정리합니다.
