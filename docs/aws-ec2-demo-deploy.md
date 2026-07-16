# AWS EC2 demo deploy

이 문서는 시연용 EC2 배포 상태와 재기동 절차를 정리한다. Production 운영 구성이
아니며, 팀 데모를 위해 단일 EC2에서 Docker Compose로 전체 스택을 실행한다.

## 현재 구조

- EC2: `i-07d75abca7ba7a423` (`t4g.small`, Amazon Linux 2023 ARM64)
- Elastic IP: `15.164.26.234`
- Security Group: `sg-01b29ee586e77a107`
- SSH key: `~/.ssh/kdt-team3-ec2`
- App path: `/opt/kdt-team3/app`
- Compose override: `docker-compose.ec2.yml`
- Nginx config: `nginx/ec2.conf`

## Routing

- `/`: frontend 정적 빌드 (`frontend/dist`)
- `/health`: backend health (`backend:8000/health`)
- `/nginx-health`: nginx 자체 health
- `/backendApi/`: backend (`backend:8000`)
- `/backendApi/api/v1/sse/`: backend SSE (buffering disabled)

EC2에서는 `docker-compose.ec2.yml`로 nginx의 `80/tcp`를 공개한다. 기본 compose의
backend/agent/postgres/redis 포트는 `127.0.0.1`에만 바인딩되어 외부에는 열리지
않는다.

Agent API는 인증을 제공하는 backend를 우회하지 않도록 Nginx에서 외부로
공개하지 않는다. 직접 상태 확인이 필요하면 EC2 내부에서
`curl http://127.0.0.1:8001/health`를 실행한다.

현재 Backend 채팅은 `mock_agent_driver`를 사용하므로 Agent 컨테이너는 제품 요청
경로와 아직 연결되지 않았다. Backend/AI 담당자가 내부 Agent API와 SSE/webhook
중계 계약을 확정하기 전까지 Agent는 독립 실행·검증 상태로 취급한다.
현재 canonical 명령이 `--profile agent`를 포함하는 것은 제품 연동 완료를 뜻하지 않고,
동일 EC2에서 독립 Agent까지 배포 가능한지 함께 시연·검증하려는 선택이다.

## Required EC2 environment

EC2의 `/opt/kdt-team3/app/.env`에는 아래 값을 반드시 설정한다. 실제 값은 Git에
커밋하지 않는다. 하나라도 비어 있으면 EC2 Compose는 기본 secret으로 실행하지
않고 즉시 실패한다.

```env
POSTGRES_PASSWORD=
COMPOSE_DATABASE_URL=postgresql://app:<POSTGRES_PASSWORD>@postgres:5432/financial_agent
JWT_SECRET_KEY=
AGENT_WEBHOOK_SECRET=
```

현재 Backend는 `DATABASE_URL`을 사용하므로 DB 비밀번호가 URL에도 들어간다.
`POSTGRES_PASSWORD`와 URL의 비밀번호는 같은 값이어야 한다.

EC2 override는 Backend의 `APP_ENV=prod`를 강제한다. 로컬 `.env`에
`APP_ENV=local`이 남아 있어도 배포 컨테이너에서는 SQLAlchemy SQL 및 bind 값 로깅을
활성화하지 않는다. 렌더링된 Compose 계약 검사가 이 설정을 CI에서 확인한다.

각 secret은 `openssl rand -hex 32` 등으로 별도 생성하고, 재배포 전에 값 자체를
출력하지 않는 검증기를 실행한다.

```bash
python3 scripts/validate_ec2_env.py --env-file .env
sudo docker compose --profile agent -f docker-compose.yml -f docker-compose.ec2.yml \
  config --quiet
sudo docker compose --profile agent -f docker-compose.yml -f docker-compose.ec2.yml \
  config --format json | python3 scripts/validate_compose_exposure.py
sudo docker compose --profile agent -f docker-compose.yml -f docker-compose.ec2.yml \
  config --format json | python3 scripts/validate_compose_contract.py
```

현재 EC2는 비용 절감을 위해 중지한 상태이므로 실제 서버 `.env` 갱신은 다음
재배포 시작 시 수행한다. 검증기 통과 전에는 서비스를 기동하지 않는다.

## HTTP demo boundary

현재 Elastic IP 진입점은 HTTP 전용이다. HTTPS를 적용하기 전까지는 테스트
계정과 Fake Money 데이터만 사용하고, 실제 비밀번호·토큰·개인정보를 입력하지
않는다. 외부 시연에서 실제 인증 흐름을 사용하기 전에 CloudFront 기본
도메인과 HTTPS를 적용한다.

## Ollama policy

Ollama는 로컬 개발 머신에서만 실행한다. EC2에는 Ollama 서버나 모델을 올리지 않는다.

다만 배포 가능한 코드와 환경변수에는 Ollama provider를 포함한다. 즉,
`LLM_PROVIDER=ollama`, `OLLAMA_BASE_URL`, `OLLAMA_MODEL` 설정은 레포에 남기되,
EC2 데모 환경에서는 기본적으로 `LLM_PROVIDER=openai` 또는 LLM 실패 시 규칙 기반
fallback 경로로 동작하게 둔다.

로컬 Docker 컨테이너에서 호스트 Ollama를 사용할 때:

```env
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://host.docker.internal:11434
OLLAMA_MODEL=qwen2.5:3b
```

로컬에서 직접 실행할 때:

```env
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:3b
```

## Restart for demo

EC2는 비용 절감을 위해 평소에는 `stopped` 상태로 둔다.

```bash
aws ec2 start-instances \
  --instance-ids i-07d75abca7ba7a423 \
  --region ap-northeast-2 \
  --profile kdt-team3-infra
```

기동 후 확인:

```bash
ssh -i ~/.ssh/kdt-team3-ec2 ec2-user@15.164.26.234
cd /opt/kdt-team3/app
sudo docker compose --profile agent -f docker-compose.yml -f docker-compose.ec2.yml ps
curl http://127.0.0.1:8001/health
```

코드를 갱신하거나 컨테이너를 재생성할 때는 frontend를 먼저 빌드한다.
과거 root builder를 사용한 EC2에서 새 non-root builder로 처음 전환할 때만 기존
`dist` 소유권을 현재 배포 사용자로 이관한다. 범위는 frontend 산출물로 제한한다.

```bash
cd /opt/kdt-team3/app
if [ -d frontend/dist ]; then
  sudo find frontend/dist -xdev ! -user "$(id -u)" -print
  sudo chown -R "$(id -u):$(id -g)" frontend/dist
fi
sudo docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp \
  -v "$PWD/frontend":/app --tmpfs /app/node_modules:rw,exec,mode=1777 -w /app \
  node:24-alpine@sha256:a0b9bf06e4e6193cf7a0f58816cc935ff8c2a908f81e6f1a95432d679c54fbfd \
  sh -c "npm ci && npm run build"
test -s frontend/dist/index.html
sudo docker compose -f docker-compose.yml -f docker-compose.ec2.yml \
  build mock-financial-service
sudo docker compose --profile maintenance -f docker-compose.yml -f docker-compose.ec2.yml \
  run --rm financial-volume-migrate
sudo docker compose --profile agent -f docker-compose.yml -f docker-compose.ec2.yml \
  up -d --build --wait --wait-timeout 180
```

non-root 금융 image로 처음 갱신하기 전에는 EBS snapshot 등으로 기존 Fake Money 원장을
백업한다. `financial-volume-migrate`는 기존 root 소유 파일을 UID/GID `10001:10001`로
이관하며 반복 실행해도 안전하다. 원장 보존을 위해 `docker compose down -v`는 사용하지
않는다.

외부 검증:

```bash
curl http://15.164.26.234/health
curl http://15.164.26.234/nginx-health
curl http://15.164.26.234/backendApi/
```

## Stop after demo

```bash
aws ec2 stop-instances \
  --instance-ids i-07d75abca7ba7a423 \
  --region ap-northeast-2 \
  --profile kdt-team3-infra
```

## Cost notes

EC2를 stop하면 인스턴스 실행 비용은 멈춘다. 남을 수 있는 비용은 다음과 같다.

- EBS root volume: `vol-07152b79beb161283`
- Elastic IP / public IPv4: `15.164.26.234`
- RDS `kdt-team3-postgres` stopped 상태의 스토리지/백업/Secret

RDS 상태와 자동 재시작 시각은 변경될 수 있으므로 비용 확인 전에 직접 조회한다.

```bash
aws rds describe-db-instances \
  --db-instance-identifier kdt-team3-postgres \
  --query 'DBInstances[0].{Status:DBInstanceStatus,AutomaticRestartTime:AutomaticRestartTime}' \
  --region ap-northeast-2 \
  --profile kdt-team3-infra
```
