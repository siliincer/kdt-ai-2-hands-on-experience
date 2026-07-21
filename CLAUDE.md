# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

**AI Financial Copilot Sandbox** — a fake-money financial AI agent platform (KDT 생성형 AI 2기 team project). A user's natural-language financial request flows through a Backend Gateway (FastAPI), an AI Agent (LangGraph), and a Mock Financial Service. Documentation, commit messages, and issues are written in Korean.

## Agent rules (binding — see AGENTS.md)

`AGENTS.md` at the repo root defines rules for AI agents; follow them:

- **Never run `git commit` / `git push` / create PRs on the user's behalf** unless explicitly told to. After work, report only: changed files, verification results, next steps.
- **Verify before reporting.** Frontend TS changes: `npm run lint` (0 warnings) and `npm run build` (`✓ built`) must pass. (AGENTS.md mentions `npm run typecheck`, but no such script exists — `tsc -b` runs as part of `npm run build`.) Python changes: at minimum a syntax check.
- **Korean + English + digits only** — no Chinese/Japanese characters anywhere (check with `rg '[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff]'` per AGENTS.md — must return 0 hits).
- Work in small cycles: ≤5–6 files per change, then verify and report.
- Commit/PR tone is collaborative, no emoji in PR titles/bodies; PRs use the 8-section template in `.github/pull_request_template.md`.
- Security (`.github/copilot-instructions.md`, `.claudeignore`): never read `.env*`, `*.tfvars`, `*.pem`/keys; no hardcoded secrets; mask PII.

## Repository layout: real vs. placeholder

- `backend/` — **real**: FastAPI Backend Gateway (`backend.main:app`, port 8000).
- `frontend/` — **real**: the official React app (npm, Feature-Sliced Design).
- `fe_example/` — legacy Figma-exported prototype, kept for reference (separate from `frontend/`).
- `agent/` — **real**: LangGraph financial agent (ported from fin-ai) behind FastAPI (`agent.main:app`, port 8001). YAML-driven workflows (`src/agent/config/`, regenerated from the team's Google Sheet via `agent/scripts/sync_config_from_sheets.py`), `interrupt()`-based human-in-the-loop over HTTP (`POST /chat`; echo `thread_id` back only on `waiting_input`), MemorySaver checkpointer (single worker only), keyword fallbacks so it runs without `OPENAI_API_KEY`. State = fixed system fields + a single `data` dict channel keyed by namespaced dotted keys (`balance.account_hint`) — LangGraph drops undeclared top-level keys, so business data must go through `data`; tools return flat deltas and the engine splits system vs. data keys (`subgraph_builder.SYSTEM_KEYS`). Both `wf_balance_inquiry` and `wf_external_transfer` work end-to-end (transfer's approval/auth/warning tools call `interrupt()` themselves — idempotent pre-interrupt code, one interrupt per node execution, ambiguous approval replies cancel conservatively). Walkthrough notebooks with baked outputs live in `agent/notebooks/`; see `agent/docs/README.md` (the single consolidated doc — architecture, contracts, change routines).
- `app/` — planned Capacitor mobile app (README only). `mock-financial-service/`, — placeholders.

## Python workspace (backend + agent)

A `uv` workspace rooted at `pyproject.toml` with members `agent` and `backend`; Python pinned to `>=3.11,<3.12`.

```bash
conda env create -f environment.yml && conda activate kdt-ai-2-hands-on-experience
uv sync
uv run pre-commit install

uv run ruff check .              # lint (CI gate); isort known-first-party=["backend"]
uv run ruff format .             # CI runs `ruff format --check .`
uv lock --check                  # lockfile sync (CI gate)
uv run pytest backend            # per-service tests
uv run pytest backend/tests/test_exceptions_response.py::test_name   # single test
uv run uvicorn backend.src.backend.main:app --reload --host 0.0.0.0 --port 8000  # run backend
```

Each service pyproject sets `pythonpath = ["src"]`, `testpaths = ["tests"]`, `test_*.py` discovery. CI falls back to an import check when a service has no tests.

### Backend architecture

- Layered convention under `backend/src/backend/`: `api/` → `services/` → `repository/` → `models/`, with `schemas/` for Pydantic DTOs and `core/`, `db/`, `utils/` for infrastructure. Routers mount under `/api/v1` in `main.py`.
- **Dual response envelope** (mirrored by the frontend — keep both shapes intact):
  - Success: `{success, message, data}` via `CommonResponse[T]` (`schemas/response.py`) + `success_response()` (`utils/build_response.py`).
  - Error: `{success: false, error: {code, message, details}}` produced by the exception handlers in `core/exceptions.py` (HTTPException, validation errors, ValueError, RuntimeError). `tests/test_exceptions_response.py` covers this exhaustively.
- **Settings gotcha**: real env settings are in `core/load_environment_var.py` (pydantic-settings, `find_dotenv`); `core/config.py` is mostly commented out — only `CORS_OPTIONS` is live. `utils/is_dev.py` raises `ValueError` at import time for unrecognized `APP_ENV`.
- DB: async SQLAlchemy 2.0 (`db/base.py` engine + `Base`, `db/session.py` `get_db` dependency). Alembic is scaffolded (`alembic.ini`, `migrations/`)

## Frontend (`frontend/`)

React 19 + Vite + TypeScript + TanStack Query 5 + Zustand + Tailwind v4 + react-error-boundary. npm with `package-lock.json`.

```bash
cd frontend
npm ci
npm run dev        # dev server
npm run build      # tsc -b && vite build — this is also the typecheck
npm run lint       # eslint (prettier enforced via eslint rule)
```

- **Feature-Sliced Design**: `src/app/`, `src/pages/`, `src/features/<feature>/{api,ui}/`, `src/shared/{api,hooks,error}/` (`widgets/`, `entities/` planned). No path aliases — relative imports only.
- **Data-fetching pattern**: use `shared/hooks/useCustomTanstackQuery.ts` / `useCustomTanstackMutation.ts`, which go through `shared/api/customFetch.ts`. `customFetch` understands both backend envelopes (via `shared/api/api_exception_handler.ts`), returns `result.data` on success, and throws `APIError` (`shared/error/APIError.ts`) otherwise — including `success: false` on HTTP 200. QueryClient defaults are `throwOnError: true, retry: false`, so errors bubble to the `ErrorBoundary` → `pages/ErrorFallback.tsx`. Don't use raw `fetch` for API calls (the current `App.tsx` demo does — known inconsistency, not the pattern to copy).
- Vite (`vite.config.ts`): env is loaded from the **monorepo root** (`envDir: ../`); dev proxy maps `/backendApi/*` → `VITE_API_BASE_URL` (prefix stripped).

## `fe_example/` (legacy prototype)

Standalone Figma-exported chat UI (React 18, shadcn/ui, `createHashRouter` for Capacitor `file://`). Its ~1300-line `src/app/App.tsx` renders financial actions inline as typed chat cards; see `fe_example/ROUTER_SCAFFOLD.md`. Invariant if touched: money-moving actions must pass the `ConfirmBottomSheet` approval gate — an unconditional `setDone(true)` on a financial action is a bug (documented past regression).

## Docker Compose & nginx

```bash
cp .env.example .env
docker compose up -d --build
```

Services: `postgres` (16), `redis` (7), `backend` (8000, alias `backend-gateway`), `agent` (8001, alias `agent-service`), `nginx` (8080). Python images build with the **repo root as context**. `docker-compose.dev.yml` and `docker-compose.override.yml` are empty placeholders.

**Two nginx configs that disagree**: compose mounts `nginx/default.conf` (`/api/` → backend, `/agent/` → agent); `nginx/nginx.conf` is an unmounted production draft (SSL, rate limiting, `/backendApi/` → upstream `fastapi`, prometheus/grafana). Note the frontend dev proxy uses `/backendApi`, matching the draft, not the mounted config — a live inconsistency to be aware of when wiring API paths.

## CI & quality gates

- `.github/workflows/ci.yaml`: `python-quality` (ruff lint + format check, `uv lock --check`, per-service pytest/import, `.env.example` required-key validation), `frontend-build` (`npm ci && npm run build` in `frontend/`), `docker-check` (`docker compose config` + builds every `*/Dockerfile`).
- `.github/workflows/security.yaml`: gitleaks + Trivy on every PR/push to `main`.
- `.pre-commit-config.yaml`: ruff (`--fix`) + ruff-format, whitespace/EOF/yaml/toml checks, `detect-private-key`. Line length 88, double quotes, lint select `E,F,I,N,W`.

## Conventions

Commits follow `type: 제목 (#이슈번호)` with types `feat`, `fix`, `refactor`, `chore`, `test`, `docs`, `style`. Issues use `.github/ISSUE_TEMPLATE/`. Copy `.env.example` → `.env` (gitignored); see `docs/security-rules.md`.

## Code generation constraints

- Ensure all recommended external packages are safe from known CVE vulnerabilities.
- Filter out local network IPs and staging/production domain names from error logs.
