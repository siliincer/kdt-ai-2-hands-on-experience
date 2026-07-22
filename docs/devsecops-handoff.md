# DevSecOps handoff

이 문서는 현재 DevSecOps 관점에서 확인된 배포/연결 상태와 팀 공유 사항을 정리한다.
프로젝트는 아직 개발 중이며, 아래 내용은 "현재 존재하는 기능이 배포 환경에서
서로 붙을 수 있는지"를 확인한 결과다.

## 결론

- 애플리케이션 EC2 + Docker Compose 방식으로 시연 가능한 배포선을 확인했다.
- frontend, nginx, backend, agent, postgres, redis가 한 서버에서 함께 실행되는 것을
  확인했다.
- 현재 Backend 채팅은 `mock_agent_driver`를 사용한다. Agent 컨테이너는 독립
  실행되지만 frontend -> backend 제품 요청 경로에는 아직 연결되지 않았다.
- 외부 IP에서는 frontend와 backend만 공개한다. Agent API는 EC2 내부에서만
  접근한다.
- 비용 최소화를 위해 현재 EC2는 `stopped` 상태로 둔다.
- 도메인은 구매하지 않는다. 시연 시에는 Elastic IP를 직접 사용한다.
- 배포용 Ollama는 같은 VPC의 별도 모델 EC2에 두는 구조로 정했다. 임시 모델은
  `exaone3.5:7.8b`이며 인스턴스는 아직 생성 전이다.

## AWS 리소스

### EC2

- Instance ID: `i-07d75abca7ba7a423`
- Type: `t4g.small`
- OS: Amazon Linux 2023 ARM64
- State: 평소에는 `stopped`
- Elastic IP: `15.164.26.234`
- Security Group: `sg-01b29ee586e77a107`
- SSH key: `~/.ssh/kdt-team3-ec2`
- App path: `/opt/kdt-team3/app`

### Security group

- `22/tcp`: 현재 관리자 IP만 허용
- `80/tcp`: 전체 공개
- `443/tcp`: HTTPS 미적용 상태이므로 인바운드 규칙 제거 완료

### Model EC2 (planned)

- 애플리케이션 EC2와 같은 VPC에 생성한다.
- Ollama `11434/tcp`는 애플리케이션 EC2 Security Group에서 오는 연결만 허용한다.
- Ollama API는 Nginx나 인터넷에 공개하지 않는다.
- 임시 모델은 `exaone3.5:7.8b`이고 환경변수로 교체 가능하게 유지한다.
- 인스턴스 유형과 사설 주소는 모델 부하 시험 후 기록한다.
- 현재 `t4g.small` 애플리케이션 EC2에는 모델을 함께 배치하지 않는다.

### RDS

- DB instance: `kdt-team3-postgres`
- Status: `stopped`
- 현재 EC2 데모 배포에서는 RDS를 사용하지 않고, EC2 내부 PostgreSQL 컨테이너를 사용한다.
- RDS는 `2026-07-15 10:45:02 KST`쯤 자동 재시작 예정이므로 사용하지 않으면 그 전에
  다시 stop하거나 삭제 여부를 결정한다.

### ECS/Fargate

- 이전에 Fargate 배포 가능성 검증은 완료했다.
- 현재 실행 중인 ECS task는 없다.
- 현재 시연 기준은 ECS가 아니라 EC2 + Docker Compose다.

## EC2 배포 구조

```text
Elastic IP: 15.164.26.234
  -> Application EC2
    -> nginx:80
      -> /            frontend/dist
      -> /backendApi/ backend:8000
    -> agent:8001     EC2 loopback/Docker 내부에서만 접근
    -> postgres:5432  EC2 내부 컨테이너
    -> redis:6379     EC2 내부 컨테이너

Private VPC traffic
  Application EC2 agent -> Model EC2 Ollama:11434
```

서버 안의 주요 파일:

- `/opt/kdt-team3/app/docker-compose.yml`
- `/opt/kdt-team3/app/docker-compose.ec2.yml`
- `/opt/kdt-team3/app/nginx/ec2.conf`
- `/opt/kdt-team3/app/.env`
- `/opt/kdt-team3/app/frontend/dist`

`docker-compose.ec2.yml`과 `nginx/ec2.conf`는 레포에 포함한다. EC2에서는 nginx
`80/tcp`를 공개한다. backend/agent/postgres/redis 포트는 `127.0.0.1` 바인딩이라
외부에는 열리지 않는다.

현재 Backend 채팅은 `mock_agent_driver`로 UI/SSE 흐름을 만든다. 실제 LangGraph
Agent 연결은 Backend가 Docker 내부의 `http://agent-service:8001`을 호출하고
기존 SSE/webhook 흐름으로 결과를 중계하는 계약이 확정된 뒤 적용한다.

EC2 재배포 전에 `/opt/kdt-team3/app/.env`에 `POSTGRES_PASSWORD`,
`COMPOSE_DATABASE_URL`, `JWT_SECRET_KEY`, `AGENT_WEBHOOK_SECRET`, `LLM_PROVIDER`,
`OLLAMA_BASE_URL`, `OLLAMA_MODEL`을 설정해야 한다.
EC2 Compose는 이 값이 비어 있으면 알려진 로컬 기본값으로 기동하지 않고 실패한다.
`python3 scripts/validate_ec2_env.py --env-file .env`는 빈 값뿐 아니라 알려진
placeholder, 짧은 secret, DB 비밀번호 불일치도 거부한다. 실제 EC2 `.env` 갱신은
중지된 인스턴스를 다음 재배포 때 시작한 후 수행한다.

## 확인한 연결

EC2를 켠 상태에서 아래를 확인했다.

```text
GET /                  -> frontend 정적 페이지 응답
GET /health            -> backend health 응답
GET /nginx-health      -> ok
GET /backendApi/       -> {"message":"안녕하세요!"}
GET 127.0.0.1:8001/health -> Agent 내부 health 응답
```

확인 명령:

```bash
curl http://15.164.26.234/health
curl http://15.164.26.234/nginx-health
curl http://15.164.26.234/backendApi/
curl http://127.0.0.1:8001/health
```

## Ollama 정책

로컬 개발과 AWS 배포는 서로 다른 endpoint를 사용한다.

- 로컬 개발에서는 개발자 머신의 Ollama를 사용한다.
- AWS 배포에서는 같은 VPC의 별도 모델 EC2를 사용한다.
- AWS 임시 모델은 `exaone3.5:7.8b`이며 `OLLAMA_MODEL`로 교체할 수 있다.
- 모델 EC2의 `11434/tcp`는 애플리케이션 EC2 Security Group만 접근할 수 있다.
- 레드팀 검증용 생성/판정 모델은 제품 Agent 배포 모델과 별도이며 AWS 제품 스택에
  함께 배포하지 않는다.

AWS 배포 환경:

```env
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://<MODEL_EC2_PRIVATE_IP_OR_DNS>:11434
OLLAMA_MODEL=exaone3.5:7.8b
```

로컬 직접 실행:

```env
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:3b
```

로컬 Docker 컨테이너에서 호스트 Ollama 사용:

```env
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://host.docker.internal:11434
OLLAMA_MODEL=qwen2.5:3b
```

## 의도적으로 보류한 항목

- 실제 Agent 제품 연결: Backend가 아직 `mock_agent_driver`를 사용하므로
  Backend/AI 담당자가 내부 API와 SSE/webhook 계약을 확정할 때까지 구현하지 않는다.
- readiness endpoint: `/health`는 liveness로 유지한다. DB/Redis 및 Agent provider
  준비 상태 계약은 Backend/AI 담당자가 정한 뒤 `/ready`로 분리한다.
- HTTPS: Fake Money와 테스트 계정만 사용하는 현재 데모에서는 HTTP 위험을
  수용한다. 실제 사용자 인증을 공개하기 전에 CloudFront HTTPS, API/SSE 전달,
  cache 비활성화와 origin 제한을 함께 검증한다.
- 실제 EC2 `.env` 갱신: 비용 절감을 위해 인스턴스가 중지되어 있어 지금 시작하지
  않는다. 다음 재배포 시작 시 secret 생성, 검증기 통과, Compose 기동 순서로 한다.

## 비용 관리

평소에는 EC2를 stop한다.

```bash
aws ec2 stop-instances \
  --instance-ids i-07d75abca7ba7a423 \
  --region ap-northeast-2 \
  --profile kdt-team3-infra
```

모델 EC2 생성 후에는 실제 ID를 사용해 함께 중지한다.

```bash
aws ec2 stop-instances \
  --instance-ids "$MODEL_EC2_INSTANCE_ID" \
  --region ap-northeast-2 \
  --profile kdt-team3-infra
```

EC2를 stop해도 남을 수 있는 비용:

- EBS root volume: `vol-07152b79beb161283`
- 모델 EC2의 인스턴스 실행 비용과 EBS(생성 후 식별자 기록)
- Elastic IP / public IPv4: `15.164.26.234`
- RDS stopped 상태의 스토리지/백업/Secret

## 시연 전 재기동

```bash
aws ec2 start-instances \
  --instance-ids i-07d75abca7ba7a423 \
  --region ap-northeast-2 \
  --profile kdt-team3-infra
```

SSH 접속:

```bash
ssh -i ~/.ssh/kdt-team3-ec2 ec2-user@15.164.26.234
```

컨테이너 상태 확인:

```bash
cd /opt/kdt-team3/app
sudo docker compose --profile agent -f docker-compose.yml -f docker-compose.ec2.yml ps
```

필요 시 재빌드/재기동:

```bash
cd /opt/kdt-team3/app
git pull
python3 scripts/validate_ec2_env.py --env-file .env
sudo docker run --rm -v "$PWD/frontend":/app -w /app node:24-alpine \
  sh -c "npm ci && npm run build"
sudo docker compose --profile agent -f docker-compose.yml -f docker-compose.ec2.yml up -d --build
```

frontend만 다시 빌드해야 할 때:

```bash
cd /opt/kdt-team3/app/frontend
sudo docker run --rm -v "$PWD":/app -w /app node:24-alpine sh -c "npm ci && npm run build"
cd /opt/kdt-team3/app
sudo docker compose --profile agent -f docker-compose.yml -f docker-compose.ec2.yml up -d nginx
```

## 팀 공유 요약

- 시연 주소는 EC2가 켜져 있을 때 `http://15.164.26.234`다.
- HTTPS 적용 전에는 Fake Money와 테스트 계정만 사용하고 실제 자격증명은
  입력하지 않는다.
- Agent `8001` API는 외부에 공개하지 않는다.
- 평소에는 비용 절감을 위해 EC2를 꺼둔다.
- EC2를 켜면 같은 Elastic IP로 다시 접근할 수 있다.
- 배포 시 모델 EC2도 함께 시작하고 종료하며, Agent는 사설 주소로만 Ollama에 접근한다.
