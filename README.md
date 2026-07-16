# KDT AI 2 Hands-on Experience

KDT 생성형 AI 2기 실무 프로젝트 저장소입니다.

현재 코드는 Frontend, Backend, Agent, Mock Financial Service를 로컬 Compose와 EC2 데모
구성에서 함께 실행할 수 있는 단계입니다. Backend 채팅은 아직 `mock_agent_driver`를
사용하며 Agent는 독립 검증 경로입니다. 상세 설계와 실행법은 각 서비스 README와
`docs/`를 기준으로 합니다.

## 프로젝트 개요

AI Financial Copilot Sandbox는 실제 금융 거래가 아닌 Fake Money 환경에서 동작하는 금융 AI Agent 플랫폼입니다.

기본 목표는 사용자의 자연어 금융 요청을 받아 Backend Gateway, AI Agent, Mock Financial Service가 협력하여 안전하게 처리하는 구조를 만드는 것입니다.

## 현재 개발 단계

현재는 서비스별 기능 개발과 통합 계약 검증을 병행합니다.

- React/Vite Frontend와 FastAPI Backend/Agent 개발
- Fake Money 원장과 Backend HTTP 연동, Agent 독립 실행 검증
- uv workspace와 Docker Compose 통합 실행
- CI 품질 검사, 테스트, 이미지 취약점 및 secret 검사
- EC2 데모 배포와 로컬 red-team 회귀 검증

## 디렉터리 구조

```text
.
├── frontend/
├── backend/
├── agent/
├── mock-financial-service/
├── docs/
├── nginx/
├── .github/
│   ├── ISSUE_TEMPLATE/
│   └── workflows/
├── pyproject.toml
├── uv.lock
├── docker-compose.yml
├── docker-compose.dev.yml
├── docker-compose.ec2.yml
├── docker-compose.prod.yml
├── .env.example
└── README.md
```

## 담당 영역

### Frontend

React/Vite 기반 사용자 화면입니다. API URL은 `VITE_API_BASE_URL`로 주입하며 정적 build는
EC2 Nginx에서 제공합니다.

### Backend

FastAPI Gateway로 인증, 채팅, UI/SSE API와 PostgreSQL·Redis·금융 서비스 연동을
담당합니다.

### AI Agent

FastAPI와 LangGraph 기반 금융 업무 Agent입니다. OpenAI, Vertex, Ollama provider를
지원하며 현재 Compose에서는 독립 local 원장을 사용합니다. HTTP 원장 adapter는 현재
Fake Money `/api/v1` 계약과 호환되지 않아 배포에서 사용하지 않습니다.

### Mock Financial Service

FastAPI, SQLAlchemy, SQLite 기반 Fake Money 원장입니다. 계좌·송금·카드·정보계 API와
감사 로그를 제공합니다.

### DevSecOps

DevSecOps는 팀 전체가 동일한 방식으로 개발, 실행, 검증할 수 있도록 기본 실행 환경과 운영 규칙을 관리합니다.

담당한 부분:

- `.env.example` 환경변수 템플릿
- `docs/security-rules.md` 보안 규칙
- `docs/local-development.md` 로컬 실행 기준
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

Python 서비스 의존성은 `uv`로 관리합니다.

```bash
conda env create -f environment.yml
conda activate kdt-ai-2-hands-on-experience
uv sync
uv run pre-commit install
```

Backend, PostgreSQL, Redis 2개, mock financial service, Nginx를 실행합니다.

```bash
docker compose up -d --build
docker compose ps
```

Agent까지 포함할 때는 profile을 사용합니다.

```bash
docker compose --profile agent up -d --build --wait
```

Frontend Vite 개발 서버와 host 기반 Backend 개발 방식은
`docs/local-development.md`를 따릅니다. EC2 데모는 frontend 정적 build를 포함하므로
`docs/aws-ec2-demo-deploy.md`의 canonical 절차를 사용합니다.

## Docker 구성

- 세 Python 서비스는 non-root runtime image로 실행합니다.
- 내부 서비스 host 포트는 loopback에만 bind합니다.
- Docker json log는 서비스마다 최대 `10m` 파일 3개로 회전합니다.
- EC2에서는 Nginx 80만 외부 공개하고 독립 Agent API는 loopback에만 둡니다.

## 문서

- `docs/security-rules.md`: 보안 규칙
- `docs/local-development.md`: 로컬 개발 명령
- `docs/aws-ec2-demo-deploy.md`: EC2 데모 배포 및 재기동 기준
- `docs/README.md`: 문서 디렉터리 안내

서비스별 상세 내용은 `frontend/README.md`, `backend/README.md`, `agent/README.md`,
`mock-financial-service/README.md`를 기준으로 합니다.

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
docs: 배포 실행 기준 갱신 (#1)

- EC2 재기동 명령 갱신
- health 확인 절차 정리
```
