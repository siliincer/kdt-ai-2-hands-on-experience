# E2E — 실제 API + 실제 브라우저

`pytest-playwright` 기반. mock 없음 — 실제로 떠 있는 backend(+postgres)와 frontend(vite dev)를 그대로 구동해서 검증한다.

각 테스트는 실행마다 backend `/api/v1/users/signup`을 직접 호출해 고유 이메일로 새 유저를 만들고(회원가입 시 계정계 계좌가 같이 프로비저닝됨 — `backend/src/backend/services/user_service.py`), 그 계정으로 실제 브라우저 로그인부터 검증한다. 시드 데이터/미리 만든 테스트 계정에 의존하지 않음.

## 사전 준비

**`docker compose up --build -d`(풀스택)는 아직 못 씀** — 아래 "알려진 제약" 1·2번 때문. 대신 이 조합으로 띄운다(2026-07-15 기준 실제로 검증됨, `1 failed, 8 passed`까지 도달):

```bash
# repo root — postgres/redis만 docker로 (mock-financial-service는 안 띄움 —
# agent가 기본 BANK_CLIENT=local이라 애초에 필요 없음, Dockerfile도 깨져있음)
docker compose up -d postgres redis_cache redis_stream

# backend — 로컬 직접 실행. host를 postgres/redis 컨테이너가 실제로 노출된
# localhost로 override(.env의 DATABASE_URL 등은 docker network용 호스트명
# postgres/redis라 로컬 프로세스에선 안 먹음)
DATABASE_URL="postgresql+asyncpg://app:change-me-in-local@localhost:5432/financial_agent" \
REDIS_CACHE_URL="redis://localhost:6379/0" \
REDIS_STREAM_URL="redis://localhost:6380/0" \
uv run --package backend uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

# agent — 로컬 직접 실행 (기본 BANK_CLIENT=local, 내장 mock 원장이라 추가 설정 불필요)
uv run --package agent uvicorn agent.main:app --reload --host 0.0.0.0 --port 8001

# frontend — vite dev 서버
cd frontend && npm run dev   # 5173
```

**주의**: `backend/migrations/env.py`에 sync 드라이버 치환 fix가 로컬에만 적용돼 있고 아직 커밋 안 됨(알려진 제약 2번). 이 fix 없이 backend를 실행하면 마이그레이션 단계에서 조용히 멈춰서 위 서버가 안 뜬다 — 최신 `env.py`가 `sync_url = settings.DATABASE_URL.replace("postgresql+asyncpg", "postgresql+psycopg2")`를 포함하는지 먼저 확인할 것.

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
│   └── test_login_balance_transfer.py    # 회원가입→로그인→계좌조회→송금 9개 테스트
```

## 테스트 목록

2026-07-15 기준 실제 실행 결과(`docker compose up -d postgres redis_cache redis_stream` + backend/agent 로컬 + frontend dev, 위 "사전 준비" 그대로). `1 failed, 8 passed in ~20s`.

| 테스트 | 검증 내용 | 결과 |
|---|---|---|
| `test_signup_then_login_shows_chat_screen` | 실제 회원가입 → 실제 로그인 → 챗 화면 전환 | PASS |
| `test_login_wrong_password_shows_error` | 틀린 비밀번호 → "이메일 또는 비밀번호가 잘못되었습니다." 표시 | **FAIL — 실앱 버그, 아래 "발견된 버그" 1번** |
| `test_balance_inquiry_shows_provisioned_account` | "잔액 확인" 클릭 → 실제 agent가 잔액조회 tool 호출 → 프로비저닝된 계좌 반환 | PASS |
| `test_transfer_confirm_card_appears_with_real_agent_flow` | "송금하기" 클릭 → 확인 카드 노출 | PASS |
| `test_transfer_completes_after_confirmation` | 확인 카드에서 승인 버튼까지 눌러 완료 응답까지 확인 (실 원장 반영은 `.env`에 `FINANCIAL_DEMO_RECEIVER_*` 미설정이라 
| `test_logout_returns_to_login_screen` | 로그아웃 → 로그인 화면 복귀 + `sessionStorage` 토큰 정리 확인 | PASS |
| `test_expired_session_redirects_to_login` | 유효하지 않은 토큰으로 인증 필요 요청 → 자동 로그아웃 + 로그인 화면 복귀 (안내 메시지는 안 뜸 — 아래 "발견된 버그" 2번) | PASS |
| `test_signup_duplicate_email_shows_error` | 중복 이메일 회원가입 → "이미 사용 중인 이메일입니다." 표시 | PASS |
| `test_session_persists_after_reload` | 로그인 상태에서 새로고침해도 챗 화면 유지 | PASS |

## 발견된 버그 (테스트 작성 중 실앱에서 재현·확인)

**1. 로그인 실패 시 엉뚱한 "세션 만료" 메시지** (`test_login_wrong_password_shows_error` FAIL 원인)

backend는 정상 — 틀린 비밀번호에 `401` + `{"error":{"message":"이메일 또는 비밀번호가 잘못되었습니다."}}` 반환(`backend/src/backend/services/user_service.py:37-41`). 문제는 frontend `frontend/src/shared/api/customFetch.ts:21-28`: `response.status === 401`이면 응답 바디를 읽지도 않고 무조건 `'세션이 만료되었습니다. 다시 로그인해 주세요.'`로 덮어쓰고 `emitUnauthorized()`까지 쏨. 이 분기는 "토큰 만료" 전용으로 만든 건데, 인증이 필요 없는 로그인 요청 자체에도 무차별 적용됨. `LoginFeature.tsx:48-53`는 받은 메시지를 그대로 보여줄 뿐이라 잘못 없음.

**2. 진짜 세션 만료 시엔 반대로 메시지가 아예 안 뜸**

`customFetch.ts:24`가 `'세션이 만료되었습니다...'`를 던지긴 하지만, 화면에 그걸 렌더링해주는 토스트/배너 컴포넌트가 코드베이스 어디에도 없다(이 문자열을 실제로 표시하는 곳은 위 1번 버그 경로인 `LoginFeature.tsx`의 로그인 실패 catch 하나뿐). `ChatThread`의 채팅 요청이 진짜 401을 받으면 `emitUnauthorized()` → `App.tsx`가 조용히 로그아웃 + 로그인 화면으로 돌려보내기만 하고, 왜 튕겼는지 사용자에게 알려주는 메시지는 없음.

**고치는 방향**: `customFetch.ts`의 401 분기가 로그인/회원가입처럼 인증이 필요 없는 엔드포인트는 건너뛰게 하고(백엔드가 준 실제 `error.message`를 그대로 보여주게), 반대로 `emitUnauthorized()` 경로엔 리다이렉트 후 표시할 토스트/배너를 추가해야 함. 아직 수정 안 함.


```
sqlalchemy.exc.MissingGreenlet: greenlet_spawn has not been called;
can't call await_only() here. Was IO attempted in an unexpected place?
```


```bash
# 터미널 1
uv run --package financial-service uvicorn financial_service.app:app \
  --app-dir mock-financial-service/src --port 8002

# 터미널 2
BANK_CLIENT=http MOCK_FINANCIAL_SERVICE_URL=http://localhost:8002 \
  uv run --package agent uvicorn agent.main:app --app-dir agent/src --port 8011

# 실제 호출
curl -X POST http://localhost:8011/chat -H "Content-Type: application/json" \
  -d '{"user_id": "user_001", "message": "잔액 확인해줘"}'
# → {"reply":"잔액 조회 중 문제가 발생했습니다.", ...}
```

## 관련 문서

- [`agent/README.md`](../agent/README.md) 4절 — 이 테스트가 검증하는 `/chat` 응답 계약(잔액조회 tool, 송금 need_approval 흐름)의 출처
- [`frontend/README.md`](../frontend/README.md) — 로그인 폼/챗 화면 컴포넌트 구조
- [`mock-financial-service/README.md`](../mock-financial-service/README.md) — agent가 http 모드에서 호출하는 계좌/송금 API, 에러 스키마
