# KDT AI 2 Hands-on Experience

KDT 생성형 AI 2기 실무 프로젝트 저장소입니다.

현재 README는 `기본 구조 개발` 단계 기준으로 작성되었습니다. 각 담당자는 본인 파트의 기술 스택, 실행 방법, 주요 기능, 테스트 방법을 정리해 주세요.

## 프로젝트 개요

AI Financial Copilot Sandbox는 실제 금융 거래가 아닌 Fake Money 환경에서 동작하는 금융 AI Agent 플랫폼입니다.

기본 목표는 사용자의 자연어 금융 요청을 받아 Backend Gateway, AI Agent, Mock Financial Service가 협력하여 안전하게 처리하는 구조를 만드는 것입니다.

## 현재 개발 단계

현재 단계에서는 비즈니스 기능 완성보다 프로젝트 기본 구조를 우선 구성합니다.

- 서비스 디렉터리 구조 정의
- 환경변수 템플릿 정리
- uv 기반 Python workspace 구성
- Docker Compose 기반 실행 구조 준비
- GitHub Issue/PR 템플릿 구성
- DevSecOps 보안 규칙 문서화

## 디렉터리 구조

```text
.
├── frontend/
├── backend/
├── agent/
├── mock-financial-service/
├── db/
│   ├── init/
│   └── migrations/
├── docs/
├── nginx/
├── .github/
│   ├── ISSUE_TEMPLATE/
│   └── workflows/
├── pyproject.toml
├── uv.lock
├── docker-compose.yml
├── docker-compose.override.yml
├── .env.example
└── README.md
```

## 담당 영역

### Frontend

담당자 작성 예정

### Backend

담당자 작성 예정

### AI Agent

담당자 작성 예정

### Mock Financial Service

담당자 작성 예정

### DevSecOps

DevSecOps는 팀 전체가 동일한 방식으로 개발, 실행, 검증할 수 있도록 기본 실행 환경과 운영 규칙을 관리합니다.

담당한 부분:

- `.env.example` 환경변수 템플릿
- `docs/security-rules.md` 보안 규칙
- `docs/local-development.md` 로컬 실행 명령 초안
- `.dockerignore` Docker 빌드 제외 규칙
- 루트 `uv` workspace 및 Python 서비스 의존성 관리 기준
- Conda, uv, pre-commit 기반 개발환경 세팅
- 서비스별 기본 디렉터리 README
- GitHub Issue/PR 템플릿 구조
- Docker Compose, CI, 보안 스캔, 모니터링 확장 기반 관리

## 환경변수

로컬 개발 시 `.env.example`을 복사해 `.env`를 생성합니다.

```bash
cp .env.example .env
```

실제 API key, 토큰, 비밀번호는 Git에 커밋하지 않습니다.

자세한 규칙은 `docs/security-rules.md`를 참고합니다.

## 로컬 실행

현재는 기본 구조 개발 단계이므로 전체 서비스 실행은 아직 준비 중입니다.

Python 서비스 의존성은 `uv`로 관리합니다.

```bash
conda env create -f environment.yml
conda activate kdt-ai-2-hands-on-experience
uv sync
uv run pre-commit install
```

Docker Compose 실행 명령 초안:

```bash
docker compose up -d --build
docker compose ps
```

각 서비스 코드와 Dockerfile이 추가된 뒤 실행 가능하도록 구성할 예정입니다.

## Docker 구성 계획

현재는 Docker Compose 파일과 서비스 디렉터리 구조를 먼저 준비합니다. 각 서비스 코드가 들어온 뒤 서비스별 Dockerfile과 실행 명령을 확정합니다.

## 문서

- `docs/security-rules.md`: 보안 규칙
- `docs/local-development.md`: 로컬 개발 명령 초안
- `docs/README.md`: 문서 디렉터리 안내

팀원별 상세 문서는 각 담당자가 추가 작성해 주세요.

## 협업 규칙

### Issue

이슈는 `.github/ISSUE_TEMPLATE/`의 템플릿을 사용합니다.

- Bug
- Feature
- Refactor
- Test

### Pull Request

PR은 `.github/pull_request_template.md` 양식을 사용합니다.

작업 내용, 실제 걸린 시간, 테스트 여부, 리뷰 요청 사항을 작성합니다.

### Commit Message

커밋 메시지는 아래 형식을 따릅니다.

```text
type: 제목 (#이슈번호)

- 본문
```

사용 가능한 type:

- `feat`: 새로운 기능 추가
- `fix`: 버그 수정
- `refactor`: 코드 구조 개선
- `chore`: 설정/빌드 수정
- `test`: 테스트 코드
- `docs`: 문서
- `style`: 코드 포매팅/스타일 변경

예시:

```text
docs: 기본 README 작성 (#1)

- 기본 구조 개발 단계 기준 README 작성
- DevSecOps 담당 범위와 팀원 작성 예정 영역 구분
```

## 팀원 작성 요청

각 담당자는 아래 내용을 본인 파트에 맞게 채워 주세요.

- 사용 기술 스택
- 주요 기능
- 실행 방법
- 환경변수
- 테스트 방법
- 현재 진행 상황
- DevSecOps와 협의가 필요한 포트, Health Check, 외부 API 의존성

.
