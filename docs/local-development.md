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

Agent 앱 진입점은 AI 담당자가 코드 구조를 확정한 뒤 업데이트합니다. 현재 Docker Compose 기본 실행에서는 `agent` 서비스를 profile로 분리합니다.

예상 실행 형식:

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

Agent는 `agent.main:app`이 추가된 뒤 profile을 지정해 실행합니다.

```bash
docker compose --profile agent up -d --build agent
```

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
uv run pytest
```

패키지를 추가할 때:

```bash
uv add --package backend <package-name>
uv add --package agent <package-name>
```

패키지 변경 후에는 `pyproject.toml`과 `uv.lock`을 함께 커밋합니다.
