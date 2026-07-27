# 관측(Observability) — Grafana + Tempo + Prometheus

Backend 의 **트레이스는 Tempo**, **메트릭은 Prometheus**, **화면은 Grafana** 한 곳으로 모은다.
설정 근거: [Tempo single-binary 예제](https://github.com/grafana/tempo/tree/main/example/docker-compose/single-binary),
[Prometheus getting started](https://prometheus.io/docs/prometheus/latest/getting_started/).

```
backend(host, fastapi dev) --OTLP gRPC :4317--> Tempo :3200 --+
                                                               +--> Grafana :3000
Prometheus :9090 --scrape host.docker.internal:8000/metrics ---+
```

## 1. 켜기

```bash
# 1) 관측 스택 기동
docker compose -f docker-compose.dev.yml up -d tempo prometheus grafana

# 2) OTel 파이썬 패키지 설치(선택 의존성)
uv sync --group otel

# 3) 백엔드를 추적 켜고 기동
OTEL_ENABLED=true uv run fastapi dev backend/src/backend/main.py
```

끄기: `OTEL_ENABLED=false`(기본값) → 계측이 **완전 no-op**. 패키지를 되돌리려면 `uv sync`.

| 서비스 | 주소 | 용도 |
| --- | --- | --- |
| Grafana | http://localhost:3000 | 대시보드/Explore (익명 Admin, 로컬 전용) |
| Tempo | http://localhost:3200 | 트레이스 조회 API |
| Prometheus | http://localhost:9090 | 메트릭 |
| OTLP 수신 | localhost:4317(gRPC) / 4318(HTTP) | backend → Tempo |

## 2. 트레이스 조회 (CLI — AI 디버깅용)

Grafana UI 없이 `curl` 만으로 스팬 트리를 읽을 수 있다. **이게 이 스택의 핵심 목적**이다.

```bash
# 수집된 서비스 확인
curl -s "http://localhost:3200/api/search/tag/service.name/values"

# 최근 트레이스 검색(TraceQL)
curl -s --get "http://localhost:3200/api/search" \
  --data-urlencode 'q={ resource.service.name="backend-gateway" }' \
  --data-urlencode 'limit=10'

# 특정 엔드포인트만
curl -s --get "http://localhost:3200/api/search" \
  --data-urlencode 'q={ name="POST /api/v1/chat" }'

# 단일 트레이스 상세(스팬 트리 + 속성)
curl -s "http://localhost:3200/api/traces/<traceID>"
```

실제 `POST /api/v1/chat` 트레이스에서 보이는 것(검증 완료):
`POST /api/v1/chat`(root) → SQLAlchemy `SELECT users` / `INSERT chat_sessions` /
`INSERT execution_contexts` / `UPDATE execution_contexts(agent_thread_id)` →
httpx `POST http://localhost:8001/internal/v1/executions` (202).

> 2026-07-23 "기본계좌 미반영" 디버깅 때는 임시 파일 트레이스를 코드에 심고 서버를 리로드해야 했다.
> 이제 **코드 수정 없이** 위 명령만으로 같은 정보를 얻는다.

## 3. 로그 ↔ 트레이스 상관관계

로그 한 줄에 요청 id 와 트레이스 id 가 함께 남는다.

```
2026-07-24 11:39:02 INFO [backend.core.observability] [req=-] [trace=-] ...
```

`trace=` 값을 그대로 `/api/traces/<traceID>` 에 넣으면 해당 요청의 스팬 트리로 점프한다.
OTel 이 꺼져 있거나 활성 스팬이 없으면 `-` 로 남아 기존 동작과 같다.

## 4. 수집 대상과 제외

- 자동 계측: **FastAPI / httpx / SQLAlchemy / Redis**(비즈니스 코드 무수정).
- 제외 경로(`_EXCLUDED_URLS`): `health`, `metrics`, `api/v1/sse/connect`.
  SSE 는 장수명 스트림이라 스팬이 비정상적으로 커진다.
- 샘플링: 개발(`APP_ENV=local/dev`)은 전량 수집, 운영은 `OTEL_SAMPLE_RATIO` 비율 샘플링.

## 5. 민감정보 취급

- HTTP 바디·헤더는 캡처하지 않는다(`Authorization`, 서비스 토큰, 웹훅 시크릿 미수집).
- SQLAlchemy 는 **SQL 문만** 남기고 바인드 값은 `$1::UUID` 플레이스홀더로 남는다.
  → `users.password_hash` 같은 **컬럼명**은 보이지만 **값은 보이지 않는다**(실측 확인: 비밀번호 원문 0건).
- 스팬 속성에 계좌번호 원문·비밀번호·토큰을 직접 넣지 말 것(수동 스팬 추가 시 주의).

## 6. 보존/저장

- Tempo `compactor.compaction.block_retention: 24h`(결정 2026-07-24). 로컬 볼륨 `tempo-data`.
- ES/Cassandra 같은 인덱스 DB 불필요 — 로컬 디스크만 쓴다.

## 7. 다음 단계(선택)

- **OTel Collector 사이드카**: `profiles: [otel-collector]` 로 추가하면 배치·샘플링·PII 스크러빙·fan-out 을
  앱 밖에서 처리. 앱 코드 변경 없이 `OTEL_EXPORTER_OTLP_ENDPOINT` 만 컬렉터로 바꾸면 된다.
- **Tempo metrics_generator**: 서비스 그래프/스팬 메트릭. Prometheus remote-write receiver 활성화 필요.
- **Agent 계측**: httpx 가 `traceparent` 를 이미 실어 보내므로, Agent 팀이 OTel 을 켜면 양쪽 트레이스가
  자동으로 이어진다.
