# Backend

FastAPI 기반 Backend Gateway를 개발하는 디렉터리입니다.

## 예정 작업

- Frontend 요청 처리
- Agent Service 연동
- PostgreSQL/Redis 연결
- Health/Ready 운영 API 제공

## 개발 환경

Python 의존성은 루트 `uv` workspace에서 관리합니다.

```bash
uv sync
cd backend
uv run uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

앱 진입점은 백엔드 코드 구조가 확정되면 업데이트합니다.
