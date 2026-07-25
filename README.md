# AI Financial Copilot Sandbox

사용자의 자연어 금융 요청("박서연에게 5만원 보내줘", "이번 달 소비 분석해줘")을 받아 **Backend
Gateway → AI Agent → Mock Financial Service** 가 협력해 처리하는 **가짜 돈(Fake Money) 금융 AI Agent
플랫폼**입니다. 실제 금융망 없이 생성형 AI 금융 에이전트의 대화형 UX·HITL 승인·안전장치를 실험하기 위해
만들었습니다. (KDT 생성형 AI 2기 팀 프로젝트)

> 문서·커밋·이슈는 한국어로 작성합니다.

## 주요 기능

- **자연어 금융 대화** — 단일 채팅 화면(assistant-ui)에서 잔액 조회·거래내역·소비 분석·카드·송금을
  말풍선 카드로 처리
- **타인송금 / 본인 계좌 간 이체** — 다단계 HITL(수취인 선택 → 승인 → 추가 인증)로 안전하게 실행
- **HITL 승인 게이트** — 돈이 움직이는 액션은 반드시 사용자 확인(승인/수정/취소)을 거침
- **실시간 스트리밍** — Agent 진행 이벤트를 SSE(Redis Streams 브리지)로 실시간 렌더
- **기본 출금 계좌 / 별칭 설정**, 슬래시 명령 `/add_account <은행명>` 으로 계좌 추가
- **장애 복구 인프라** — 외부 호출 재시도(Tenacity) + 실패 시 DLQ(Redis Stream), 멱등키로 중복 이체 방지
- **관측(Observability)** — OpenTelemetry 분산추적(Tempo) + 메트릭(Prometheus) + 대시보드(Grafana)
- **보안** — 보안 응답 헤더(secure), 서비스 간 토큰 인증, PII 마스킹, gitleaks/Trivy 스캔

<!-- 데모 화면/GIF: 준비되면 docs/assets/ 에 넣고 아래 주석을 해제하세요.
![데모](docs/assets/demo.gif)
-->

## 사용 기술 스택

| 영역 | 기술 |
| --- | --- |
| **Frontend** | React 19, Vite 8, TypeScript 6, TanStack Query 5, Zustand 5, Tailwind CSS v4, assistant-ui (Feature-Sliced Design) |
| **Backend Gateway** | Python 3.11, FastAPI 0.115, SQLAlchemy 2.0(async), Alembic, Pydantic v2, redis-py 5, secure 2, Tenacity |
| **AI Agent** | Python 3.11, LangGraph, LangChain(OpenAI·Vertex AI·Ollama), FastAPI |
| **Mock Financial Service** | Python 3.11, FastAPI, SQLAlchemy, SQLite (복식부기 원장) |
| **데이터/인프라** | PostgreSQL 16, Redis 7(cache·stream), nginx 1.27, Docker Compose, uv workspace |
| **관측** | OpenTelemetry, Grafana Tempo, Prometheus, Grafana |

서비스 포트: Backend `8000` · Agent `8001` · Mock Financial `8002` · Frontend(dev) `5173` · nginx `8080`.

## 시작 가이드 (설치 및 실행)

### 1. 공통 사전 준비

```bash
# 저장소 클론 후 루트에서
conda env create -f environment.yml
conda activate kdt-ai-2-hands-on-experience

uv sync                       # Python workspace(agent·backend·mock-financial-service) 의존성
uv run pre-commit install

cp .env.example .env          # 환경변수 템플릿 복사(실제 키/토큰은 커밋 금지)
```

### 2. 한 번에 실행 (Docker Compose)

```bash
docker compose up -d --build  # postgres·redis·backend·agent·mock-financial·nginx
docker compose ps
```

### 3. 개별 개발 실행

인프라(Postgres·Redis)만 컨테이너로 띄우고 각 서비스는 로컬에서 실행합니다.

```bash
docker compose -f docker-compose.dev.yml up -d   # postgres, redis (+관측 스택)

# 각 서비스 실행 명령·환경변수·테스트는 서브 README 참고
```

- Frontend → [`frontend/README.md`](frontend/README.md) (`npm ci && npm run dev`)
- Backend Gateway → [`backend/README.md`](backend/README.md)
- AI Agent → [`agent/README.md`](agent/README.md)
- Mock Financial Service → [`mock-financial-service/README.md`](mock-financial-service/README.md)
- 관측(트레이스/메트릭/대시보드) → [`observability/README.md`](observability/README.md)

## 디렉터리 구조

```text
.
├── frontend/                 # React 채팅 UI (실제 프론트엔드)
├── backend/                  # FastAPI Backend Gateway
├── agent/                    # LangGraph 금융 Agent
├── mock-financial-service/   # 계정계(원장) + 정보계(analytics)
├── observability/            # OpenTelemetry / Tempo / Prometheus / Grafana 설정
├── nginx/                    # 리버스 프록시 설정
├── docs/                     # 보안 규칙·운영 가이드 등 문서
├── AI_CONTEXT/               # 세션 로그·트러블슈팅 정리
├── docker-compose.yml        # 전체 서비스
├── docker-compose.dev.yml    # 개발용 인프라(+관측)
├── pyproject.toml            # uv workspace 루트
└── .env.example
```

## 협업 규칙 (요약)

- **커밋**: `type: 제목 (#이슈번호)` — `feat`·`fix`·`refactor`·`chore`·`test`·`docs`·`style`
- **PR**: `.github/pull_request_template.md` 8개 섹션 양식
- **이슈**: `.github/ISSUE_TEMPLATE/` (Bug·Feature·Refactor·Test)
- **AI 에이전트 규칙**: [`AGENTS.md`](AGENTS.md) — 커밋/PR 무단 실행 금지, 검증 후 보고, 한국어+영어+숫자만
- **보안 규칙**: [`docs/security-rules.md`](docs/security-rules.md) — `.env*`/키 커밋 금지, PII 마스킹

## 문서

- [`AGENTS.md`](AGENTS.md) · [`CLAUDE.md`](CLAUDE.md) — 저장소 규칙 / AI 코딩 가이드
- [`docs/`](docs/README.md) — 보안 규칙, 로컬 개발 가이드
