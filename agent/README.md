# Agent

AI Agent 런타임을 개발하는 디렉터리입니다.

## 예정 작업

- 사용자 자연어 의도 분석
- 등록 업무 분류
- Guardrail 및 Human-in-the-Loop 연동
- Backend API 도구 호출
- YAML 기반 Workflow 정의 로드

## 개발 환경

Python 의존성은 루트 `uv` workspace에서 관리합니다.

```bash
uv sync
cd agent
uv run uvicorn agent.main:app --reload --host 0.0.0.0 --port 8001
```

앱 진입점은 Agent 코드 구조가 확정되면 업데이트합니다.
