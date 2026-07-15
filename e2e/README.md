# E2E — 실제 API + 실제 브라우저

`pytest-playwright` 기반. mock 없음 — 실제로 떠 있는 backend(+postgres)와 frontend(vite dev)를 그대로 구동해서 검증한다.

각 테스트는 실행마다 backend `/api/v1/users/signup`을 직접 호출해 고유 이메일로 새 유저를 만들고(회원가입 시 계정계 계좌가 같이 프로비저닝됨 — `backend/src/backend/services/user_service.py`), 그 계정으로 실제 브라우저 로그인부터 검증한다. 시드 데이터/미리 만든 테스트 계정에 의존하지 않음.

## 사전 준비

세 가지가 실제로 떠 있어야 함:

```bash
# repo root — postgres, redis, backend, agent, mock-financial-service, nginx
docker compose up --build -d

# frontend — vite dev 서버 (VITE_API_BASE_URL은 .env에서 backend:8000을 가리킴)
cd frontend && npm run dev
```

## 실행

```bash
# repo root에서, 최초 1회 브라우저 바이너리 설치
uv run --package e2e playwright install --with-deps chromium

uv run --package e2e pytest e2e/tests/ --base-url http://localhost:5173
```

`--base-url`은 `page.goto("/")` 등 상대경로의 기준. backend 직접 호출 주소는 `API_BASE_URL` 환경변수로 override 가능(기본값 `http://localhost:8000`).

**디버깅용 실행 옵션**:
```bash
# 브라우저 창 띄워서 보면서 실행
uv run --package e2e pytest e2e/tests/ --base-url http://localhost:5173 --headed

# 실패 시점 스텝별로 브라우저 인스펙터 열기
uv run --package e2e pytest e2e/tests/ --base-url http://localhost:5173 --headed --slowmo 500

# 특정 테스트 하나만
uv run --package e2e pytest e2e/tests/test_login_balance_transfer.py::test_signup_then_login_shows_chat_screen \
  --base-url http://localhost:5173
```

## 파일 구조

```
e2e/
├── pyproject.toml
├── tests/
│   ├── conftest.py                       # api_base_url, api_request_context fixture
│   └── test_login_balance_transfer.py    # 회원가입→로그인→계좌조회→송금 4개 테스트
```

## 테스트 목록

| 테스트 | 검증 내용 |
|---|---|
| `test_signup_then_login_shows_chat_screen` | 실제 회원가입 → 실제 로그인 → 챗 화면 전환 |
| `test_login_wrong_password_shows_error` | 틀린 비밀번호 → 에러 메시지, 로그인 화면 유지 |
| `test_balance_inquiry_shows_provisioned_account` | "잔액 확인" 클릭 → 실제 agent가 잔액조회 tool 호출 → 실제 backend UI Data API가 프로비저닝된 계좌 반환 |
| `test_transfer_confirm_card_appears_with_real_agent_flow` | "송금하기" 클릭 → 실제 agent가 need_approval로 멈추거나 되묻는 응답을 보여줌 |

## 알려진 제약

이 코드는 실제 API 계약(backend `user_api.py`, `schemas/user.py` 등)을 직접 읽고 작성했지만, **로컬 환경에서 전체 스택을 끝까지 띄워 실행 검증은 못함** — 아래 두 가지 pre-existing 인프라 문제 때문:

1. `docker compose up`이 `mock-financial-service/Dockerfile`이 없어서 빌드 실패함 (`docker-compose.yml`은 그 경로를 참조하는데 파일 자체가 리포에 없음).
2. `docker compose` 없이 backend를 로컬에서 직접 띄우면(`uv run uvicorn backend.main:app`, DB/Redis 호스트만 `localhost`로 override) Alembic 마이그레이션 단계에서 멈춤 — 원인 미조사.

즉 테스트 코드/셀렉터는 실제 컴포넌트·API 스키마를 근거로 작성했지만, 스택이 정상적으로 뜨는 걸 직접 확인 못 한 상태 — 인프라 문제 해결 후 첫 실행에서 셀렉터 미스매치가 나올 수 있음.

## 관련 문서

- [`agent/README.md`](../agent/README.md) 4절 — 이 테스트가 검증하는 `/chat` 응답 계약(잔액조회 tool, 송금 need_approval 흐름)의 출처
- [`frontend/README.md`](../frontend/README.md) — 로그인 폼/챗 화면 컴포넌트 구조
- [`mock-financial-service/README.md`](../mock-financial-service/README.md) — agent가 http 모드에서 호출하는 계좌/송금 API, 에러 스키마
