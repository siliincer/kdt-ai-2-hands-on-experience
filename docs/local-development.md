# Local Development

## 1. Prerequisites

- Git
- Conda 또는 Miniconda
- uv
- Docker Desktop

Conda는 Python 버전 고정에 사용하고, Python 패키지 설치와 실행은 `uv`로 관리합니다.

## 2. Conda Environment

최초 1회 루트 디렉터리에서 Conda 환경을 생성합니다.

```bash
conda env create -f environment.yml
conda activate kdt-ai-2-hands-on-experience
```

이미 환경이 만들어져 있다면 활성화만 합니다.

```bash
conda activate kdt-ai-2-hands-on-experience
```

## 3. Environment Variables

```bash
cp .env.example .env
```

실제 API key, 토큰, 비밀번호는 `.env`에만 작성하고 Git에 커밋하지 않습니다.

## 4. Python Workspace

Python 서비스는 `uv` workspace로 관리합니다.

최초 1회 루트 디렉터리에서 의존성을 동기화합니다.

```bash
uv venv --python "$(which python)"
uv sync
```

`uv.lock`은 팀원 간 동일한 의존성 버전을 맞추기 위해 Git에 커밋합니다. `.venv/`는 로컬 가상환경이므로 커밋하지 않습니다.

## 5. Pre-commit

커밋 전 기본 파일 검사와 Ruff lint/format을 자동 실행합니다.

최초 1회 설치합니다.

```bash
uv run pre-commit install
```

전체 파일 대상으로 수동 확인할 때는 아래 명령을 사용합니다.

```bash
uv run pre-commit run --all-files
```

pre-commit이 파일을 자동 수정하면 다시 `git add` 후 커밋을 재시도합니다.

## 6. Backend

Backend 앱 진입점은 `backend.main:app`입니다.

```bash
cd backend
uv run uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

## 7. Agent

Agent 앱 진입점은 `agent.main:app`입니다. 현재 Docker Compose 기본 실행에서는
`agent` 서비스를 profile로 분리합니다.

호스트에서 직접 실행:

```bash
cd agent
uv run uvicorn agent.main:app --reload --host 0.0.0.0 --port 8001
```

## 8. Docker Compose

### 통합 실행

기본 Compose는 PostgreSQL, Redis, Backend, Nginx를 함께 실행합니다.

```bash
docker compose up -d --build
docker compose ps
```

### Backend 개발용 인프라 실행

Backend를 호스트에서 `uvicorn --reload`로 실행하면서 PostgreSQL과 Redis만 컨테이너로 사용할 때는 개발용 Compose를 사용합니다.

```bash
docker compose -f docker-compose.dev.yml up -d
cd backend
uv run uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

`docker-compose.dev.yml`은 `postgres`, `redis_cache`, `redis_stream` 인프라만 실행합니다. 기존 통합 실행 컨테이너가 같은 포트(`5432`, `6379`)를 사용 중이면 먼저 중지합니다.

```bash
docker compose down
```

Agent를 포함하려면 profile을 지정해 실행합니다.

```bash
docker compose --profile agent up -d --build agent
```

현재 Backend 채팅 경로는 `mock_agent_driver`를 사용하며 Agent HTTP API를 직접
호출하지 않습니다. Agent 컨테이너는 독립 개발·검증용이고, 제품 흐름 연결은
Backend/AI 담당자가 내부 API와 SSE/webhook 계약을 확정한 뒤 진행합니다.

## 9. Daily Workflow

작업 시작 시:

```bash
conda activate kdt-ai-2-hands-on-experience
uv sync
```

커밋 전 확인:

```bash
uv run ruff check --fix .
uv run ruff format .
uv run pytest backend
uv run pytest agent
uv run pytest mock-financial-service
uv run pytest security/redteam/tests
uv run pytest scripts/test_validate_ec2_env.py
```

저장소 루트에서 모든 테스트를 한 번에 수집하면 패키지별 동일한 테스트 파일명 때문에
충돌하므로 패키지별 명령을 사용합니다.

패키지를 추가할 때:

```bash
uv add --package backend <package-name>
uv add --package agent <package-name>
```

패키지 변경 후에는 `pyproject.toml`과 `uv.lock`을 함께 커밋합니다.
