# Backend

FastAPI 기반 Backend Gateway를 개발하는 디렉터리입니다.

## 현재 역할

- Frontend 요청 처리
- 채팅과 Agent 연동 계약 제공
- PostgreSQL/Redis 연결
- 금융 서비스 HTTP 연동
- Health API 제공

## 개발 환경

Python 의존성은 루트 `uv` workspace에서 관리합니다.

```bash
uv sync --all-packages
cd backend
uv run uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

앱 진입점은 `backend.main:app`이며 소스는 `backend/src/backend/`에 있습니다.
