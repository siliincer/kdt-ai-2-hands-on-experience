# DevSecOps handoff

이 문서는 최종 시연 시점에 DevSecOps 관점에서 확인한 배포·연결·보안 상태와 프로젝트 종료 후 정리 기준을
기록한다. Production 운영 구성이 아니라 Fake Money 기반 팀 데모를 위한 검증 환경이다.

## 결론

- App EC2에서 frontend, nginx, backend, agent, postgres, redis, mock-financial-service를 Docker Compose로 실행했다.
- Backend는 Docker 내부 서비스 이름을 통해 Agent(`http://agent-service:8001`)와
  Mock Financial Service(`http://mock-financial-service:8002`)를 참조하도록 구성했다.
- Backend → Mock Financial Service 내부 호출은 HTTP 200 응답까지 확인했다.
- Agent의 LLM provider는 `ollama`로 구성했고, App EC2에서 사설망을 통해 별도 Model EC2의 Ollama를 호출했다.
- 최종 확인된 배포 모델은 `exaone3.5:2.4b`이며 Model EC2 Ollama API는 `172.31.15.220:11434`에서 제공됐다.
- 외부 진입점은 App EC2의 Nginx이며 Backend/Agent/Mock Financial/PostgreSQL 포트는 외부에 직접 공개하지 않는 것을 기준으로 한다.
- Red Team은 실제 금융망이 아니라 로컬 Fake Money/Agent Testbed에서 수행하며 결과에는 민감정보 원문을 저장하지 않는다.
- 프로젝트 종료 후 AWS 리소스는 재기동을 전제로 유지하지 않고 비용 발생 리소스부터 삭제·해제하는 것을 원칙으로 한다.

## AWS 리소스

### App EC2

최종 시연에서 확인한 App EC2 정보:

- Private IP: `172.31.0.184`
- Elastic IP: `15.164.26.234`
- Security Group: `sg-01b29ee586e77a107` (`kdt-team3-ec2-sg`)
- App path: `/opt/kdt-team3/app`
- Compose: `docker-compose.yml` + `docker-compose.ec2.yml`
- Nginx config: `nginx/ec2.conf`

SSH key의 실제 파일은 사용자 로컬에서만 보관하고 서버나 Git 저장소에 복사하지 않는다.

### Model EC2

최종 시연에서 확인한 Model EC2 정보:

- Private IP: `172.31.15.220`
- Ollama API: `11434/tcp`
- LLM provider: `ollama`
- Model: `exaone3.5:2.4b`
- Ollama metadata 기준 parameter size: 약 `2.7B`, quantization: `Q4_K_M`
- 확인 당시 사양: 2 vCPU, 약 3.7 GiB RAM, NVIDIA GPU 없음

Model EC2의 `22/tcp`는 점프 호스트 역할을 하는 App EC2의 Security Group에서만 접근하도록 제한하는 구성을 권장한다.
Ollama `11434/tcp`도 인터넷 전체가 아니라 App EC2에서 필요한 사설망 경로만 허용한다.

### PostgreSQL / RDS

레포에는 EC2 Docker Compose용 PostgreSQL과 별도로 AWS RDS PostgreSQL 리소스가 존재했다.
Backend가 실제로 사용하는 DB는 `DATABASE_URL`에 전달되는 `COMPOSE_DATABASE_URL` 값으로 결정된다.

따라서 문서에서 "Docker PostgreSQL과 RDS를 동시에 Backend가 사용한다"고 표현하지 않는다.
최종 시연 DB 대상을 확인해야 하는 경우 Backend 컨테이너에서 `DATABASE_URL`의 hostname을 확인한다.

```bash
sudo docker exec kdt-backend \
  python -c 'import os; from urllib.parse import urlsplit; print(urlsplit(os.environ["DATABASE_URL"]).hostname)'
```

- `postgres` → Docker Compose PostgreSQL
- `*.rds.amazonaws.com` → RDS PostgreSQL

RDS를 더 이상 사용하지 않는 프로젝트 종료 단계에서는 Stop만으로 끝내지 않고 DB, snapshot, retained backup을 확인해
보존 필요가 없는 비용 리소스를 삭제한다.

## 최종 시연 배포 구조

```text
Internet
   |
   v
App EC2 (172.31.0.184)
   |
   +-- nginx :80
   |     +-- /              -> frontend/dist
   |     +-- /backendApi/   -> backend:8000
   |
   +-- backend:8000
   |     +-- agent-service:8001
   |     +-- mock-financial-service:8002
   |     +-- postgres / RDS (DATABASE_URL에 따라 하나 선택)
   |     +-- redis_cache / redis_stream
   |
   +-- agent:8001
   |     +-- Ollama -> 172.31.15.220:11434
   |
   +-- mock-financial-service:8002
   +-- postgres:5432
   +-- redis_cache:6379
   +-- redis_stream:6379

Model EC2 (172.31.15.220)
   +-- Ollama :11434
       +-- exaone3.5:2.4b
```

## 확인한 연결

최종 시연 배포 과정에서 다음 항목을 확인했다.

```text
Nginx -> Backend health
Backend -> Agent service URL 설정
Backend -> Mock Financial Service HTTP 200
App EC2 -> Model EC2 Ollama /api/tags 응답
Agent container -> LLM_PROVIDER=ollama
Agent container -> OLLAMA_MODEL=exaone3.5:2.4b
```

App EC2의 Agent 환경 확인:

```bash
sudo docker exec kdt-agent \
  sh -c 'env | grep -E "^(LLM_PROVIDER|OLLAMA_BASE_URL|OLLAMA_MODEL|LLM_MODEL)="'
```

Model EC2 Ollama 설치 모델 확인:

```bash
curl -s http://172.31.15.220:11434/api/tags | python3 -m json.tool
```

## EC2 환경변수

EC2의 `/opt/kdt-team3/app/.env`에는 실제 Secret을 Git에 커밋하지 않고 별도로 배치한다.
Compose 배포 전 최소 다음 값을 검증한다.

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

검증:

```bash
python3 scripts/validate_ec2_env.py --env-file .env
sudo docker compose --env-file .env --profile agent \
  -f docker-compose.yml -f docker-compose.ec2.yml config --quiet
```

## Security boundary

- Secret은 `.env` 또는 AWS/GitHub의 Secret 저장 기능으로 관리하고 Git에 커밋하지 않는다.
- App EC2의 외부 공개 포트는 Nginx 진입점만 최소화한다.
- Backend, Agent, PostgreSQL, Redis, Mock Financial Service는 인터넷에 직접 공개하지 않는다.
- Model EC2는 Public API 서버로 사용하지 않고 App EC2에서 사설망으로 Ollama를 호출한다.
- 실제 금융 정보가 아닌 Fake Money와 테스트 계정만 사용한다.
- Red Team 결과에는 계좌번호·토큰·인증값 원문을 저장하지 않는다.
- `0.0.0.0/0`의 광범위한 `All TCP`/SSH 규칙은 데모 종료 전후 정리한다.

## Red Team / Guardrail 인계

Red Team 자동화는 `security/redteam/`에서 관리한다.

- 8개 Agent 업무 Workflow와 8개 보안 검사 방식을 분리해 관리한다.
- Adaptive LLM이 공격 표현을 생성하고 deterministic rule이 최종 PASS/FAIL을 결정한다.
- Reference Case는 실제 Tool 요청, Webhook, 상태, UI 계약을 비교한다.
- `FAIL`은 보안 취약점 수와 동일하지 않으며 계약 불일치와 실제 경계 위반을 분리해 해석한다.
- 실모델 캠페인에서 확인된 "정상 금융 요청 + 악성 지시"의 원자적 차단 실패는 Agent PR #60의 전역 Intent Gate로 보완됐다.
- PR #60 회귀 확인: Intent Gate 35개 테스트, 핵심 복합공격/정상요청 8개, 전체 Agent 280개 테스트를 로컬에서 통과했다.

관련 문서:

- `security/redteam/README.md`
- `security/redteam/WORKFLOW_COVERAGE.md`
- `security/redteam/SCENARIO_DESIGN.md`
- `agent/docs/guardrail-devsecops-handoff.md`

## 프로젝트 종료 후 비용 정리

프로젝트 종료 후 다음 리소스는 "중지"가 아니라 실제 과금 종료 여부를 확인한다.

1. EC2 App / Model 인스턴스 종료(Terminate)
2. EC2 종료 후 남은 EBS Volume 확인 및 불필요 볼륨 삭제
3. Elastic IP disassociate 후 release
4. RDS 삭제 및 manual snapshot / retained automated backup 확인
5. NAT Gateway, Load Balancer, ECR, S3, CloudWatch Logs, AWS Backup recovery point 존재 여부 확인
6. Cost Explorer에서 프로젝트 사용 기간을 `Service` 기준으로 집계

VPC, Subnet, Route Table, Security Group, IAM Role 자체는 존재만으로 일반적인 시간당 compute 비용이 발생하는 리소스는
아니지만, 다른 프로젝트와 공유하는지 확인한 뒤 정리한다.

## 팀 공유 요약

- 최종 시연은 App EC2와 Model EC2를 분리한 구조로 검증했다.
- 배포 Agent는 Ollama를 사용했고 최종 확인 모델은 `exaone3.5:2.4b`였다.
- Backend에서 Mock Financial Service 내부 연결은 HTTP 200까지 확인했다.
- Backend DB는 `DATABASE_URL` 하나로 선택되며 Docker PostgreSQL과 RDS를 동시에 사용하는 구조로 문서화하지 않는다.
- Automated Red Team은 로컬 Fake Money/Testbed 경계에서만 실행한다.
- 프로젝트 종료 후 AWS 문서는 재현용으로 남기되 실제 비용 리소스는 삭제·해제한다.
