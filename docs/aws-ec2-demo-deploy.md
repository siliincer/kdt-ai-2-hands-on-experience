# AWS EC2 demo deploy

이 문서는 **최종 시연 당시** AWS EC2 배포 구조와 재현·검증 절차를 정리한다.
Production 운영 구성이 아니며, Fake Money 기반 금융 AI Agent 데모를 위한 환경이다.
프로젝트 종료 후 실제 AWS 리소스가 삭제되어도 본 문서는 최종 시연 아키텍처 기록으로 유지한다.

## 최종 구조

### App EC2

- Private IP: `172.31.0.184`
- Elastic IP: `15.164.26.234`
- Security Group: `sg-01b29ee586e77a107`
- App path: `/opt/kdt-team3/app`
- Compose: `docker-compose.yml` + `docker-compose.ec2.yml`
- Nginx config: `nginx/ec2.conf`

App EC2는 frontend, nginx, backend, agent, postgres, redis, mock-financial-service를 Docker Compose로 실행한다.

### Model EC2

- Private IP: `172.31.15.220`
- Ollama port: `11434`
- 최종 확인 모델: `exaone3.5:2.4b`
- Ollama metadata: 약 `2.7B`, `Q4_K_M`
- 확인 당시: 2 vCPU, 약 3.7 GiB RAM, NVIDIA GPU 없음

Agent는 App EC2에서 사설망을 통해 Model EC2의 Ollama를 호출한다.

## Routing

- `/`: frontend 정적 빌드 (`frontend/dist`)
- `/health`: backend health (`backend:8000/health`)
- `/nginx-health`: nginx 자체 health
- `/backendApi/`: backend (`backend:8000`)
- `/backendApi/api/v1/sse/`: backend SSE (buffering disabled)

EC2에서는 `docker-compose.ec2.yml`로 nginx의 `80/tcp`를 공개한다.
Backend/Agent/PostgreSQL/Mock Financial Service는 외부 인터넷에 직접 공개하지 않는 것을 기본 경계로 한다.

Backend 내부 서비스 연결:

```text
backend -> http://agent-service:8001
backend -> http://mock-financial-service:8002
agent   -> http://172.31.15.220:11434 (Ollama)
```

Backend → Mock Financial Service는 실제 EC2 Compose 환경에서 HTTP 200 응답까지 확인했다.

## Database boundary

레포의 EC2 Compose에는 PostgreSQL 컨테이너가 포함되어 있고, AWS에는 별도 RDS PostgreSQL 리소스도 구성됐다.
Backend는 둘을 동시에 사용하는 것이 아니라 `DATABASE_URL` 한 개의 대상만 사용한다.
EC2 override에서는 `COMPOSE_DATABASE_URL` 값을 Backend의 `DATABASE_URL`로 전달한다.

최종 실행 DB host 확인:

```bash
sudo docker exec kdt-backend \
  python -c 'import os; from urllib.parse import urlsplit; print(urlsplit(os.environ["DATABASE_URL"]).hostname)'
```

- `postgres`이면 EC2 Compose PostgreSQL
- RDS hostname이면 RDS PostgreSQL

DB target을 확인하지 않은 상태에서 아키텍처 문서에 두 DB를 동시에 실사용 DB처럼 표시하지 않는다.

## Required EC2 environment

EC2의 `/opt/kdt-team3/app/.env`에는 실제 값을 별도로 설정하고 Git에 커밋하지 않는다.

```env
POSTGRES_PASSWORD=
COMPOSE_DATABASE_URL=
JWT_SECRET_KEY=
AGENT_WEBHOOK_SECRET=
AGENT_SERVICE_TOKEN=
BACKEND_SERVICE_TOKEN=
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://172.31.15.220:11434
OLLAMA_MODEL=exaone3.5:2.4b
```

배포 전 검증:

```bash
python3 scripts/validate_ec2_env.py --env-file .env
sudo docker compose --env-file .env --profile agent \
  -f docker-compose.yml -f docker-compose.ec2.yml config --quiet
```

## LLM / Ollama

최종 AWS 데모는 Ollama를 로컬 전용으로 제한하지 않고 **별도 Model EC2**에 배치해 사용했다.
App EC2 Agent 환경에서 다음 값을 확인했다.

```text
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://172.31.15.220:11434
OLLAMA_MODEL=exaone3.5:2.4b
```

설치 모델 확인:

```bash
curl -s http://172.31.15.220:11434/api/tags | python3 -m json.tool
```

메모리에 현재 로드된 모델 확인:

```bash
curl -s http://172.31.15.220:11434/api/ps | python3 -m json.tool
```

`/api/ps`의 `models: []`는 설치 모델이 없다는 의미가 아니라 현재 메모리에 로드된 모델이 없다는 의미다.
설치 여부는 `/api/tags`로 확인한다.

### 모델 크기 제약

확인 당시 Model EC2는 약 3.7 GiB RAM, GPU 없음이었다.
따라서 `exaone3.5:2.4b`보다 큰 7B급 모델은 단순 교체 전에 EC2 메모리/CPU 또는 GPU 사양을 먼저 검토해야 한다.
로컬에서 더 큰 모델이 잘 동작하더라도 동일한 성능이 현재 Model EC2에서 보장되는 것은 아니다.

## Deploy / restart

레포를 갱신한 뒤 Compose 설정을 검증하고 필요한 서비스를 재빌드한다.

```bash
cd /opt/kdt-team3/app
git pull --ff-only origin main

python3 scripts/validate_ec2_env.py --env-file .env
sudo docker compose --env-file .env --profile agent \
  -f docker-compose.yml -f docker-compose.ec2.yml config --quiet

sudo docker compose --env-file .env --profile agent \
  -f docker-compose.yml -f docker-compose.ec2.yml \
  up -d --build mock-financial-service backend agent nginx
```

상태 확인:

```bash
sudo docker compose --env-file .env --profile agent \
  -f docker-compose.yml -f docker-compose.ec2.yml ps

curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8001/health
curl http://127.0.0.1:8002/openapi.json
```

Backend → Mock Financial Service 확인:

```bash
sudo docker exec kdt-backend python - <<'PY'
import os
import urllib.request
url = os.environ["MOCK_FINANCIAL_SERVICE_URL"].rstrip("/") + "/openapi.json"
with urllib.request.urlopen(url, timeout=5) as response:
    print(response.status)
PY
```

## Security boundary

- Agent API는 Backend 인증·승인 경계를 우회하는 외부 공개 API로 사용하지 않는다.
- Model EC2 Ollama는 인터넷 공개 endpoint가 아니라 App EC2 사설망에서만 사용한다.
- SSH key는 로컬 개발자 머신에만 보관한다.
- 실제 Secret은 `.env.example`에 넣지 않는다.
- 실제 사용자 금융정보 대신 Fake Money/Test data만 사용한다.
- Security Group의 `All TCP 0.0.0.0/0`, `SSH 0.0.0.0/0` 같은 광범위 규칙은 제거하고 필요한 source/port만 허용한다.

## Red Team verification

Red Team 자체는 AWS 외부 공격이 아니라 `security/redteam/`의 승인된 로컬 Fake Money/Testbed 경계에서 실행한다.
최신 Agent를 기준으로 Adaptive LLM과 Reference Case를 사용해 Prompt Injection, 민감정보 공개 요구,
승인·인증·소유권 우회, Tool Governance, 대화 상태·감사 로그·다중 턴 공격을 검증한다.

실모델 캠페인에서 확인된 복합 요청 원자적 차단 문제는 Agent PR #60의 Intent Gate로 보완됐다.
로컬 검증에서는 Intent Gate 35개, 핵심 복합 공격/정상 요청 8개, 전체 Agent 280개 테스트가 통과했다.

## Project shutdown / cost

프로젝트가 종료된 뒤에는 EC2를 단순 Stop 상태로 장기간 유지하지 않는다.
아래 항목을 순서대로 확인한다.

1. App EC2 / Model EC2 Terminate
2. 남은 EBS `available` volume 삭제 여부 확인
3. Elastic IP disassociate + release
4. RDS 삭제, manual snapshot / retained backup 확인
5. NAT Gateway / Load Balancer 존재 여부 확인
6. ECR / S3 / CloudWatch Logs / AWS Backup recovery point 확인
7. Cost Explorer에서 사용 기간 `Unblended cost`를 `Service` 기준으로 집계

Cost Explorer 반영에는 지연이 있을 수 있으므로 최종 삭제 직후 금액과 다음 날 금액이 다를 수 있다.

## Final demo summary

```text
Internet
   -> App EC2 / Nginx
       -> Backend
           -> Agent
               -> Model EC2 / Ollama / exaone3.5:2.4b
           -> Mock Financial Service
           -> PostgreSQL target selected by DATABASE_URL
           -> Redis cache / stream
```
