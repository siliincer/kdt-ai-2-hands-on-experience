# DevSecOps handoff

이 문서는 현재 DevSecOps 관점에서 확인된 배포/연결 상태와 팀 공유 사항을 정리한다.
프로젝트는 아직 개발 중이며, 아래 내용은 "현재 존재하는 기능이 배포 환경에서
서로 붙을 수 있는지"를 확인한 결과다.

## 결론

- EC2 단일 서버 + Docker Compose 방식으로 시연 가능한 배포선을 확인했다.
- frontend, nginx, backend, agent, postgres, redis가 한 서버에서 함께 실행되는 것을
  확인했다.
- 외부 IP에서 frontend, backend, agent API 접근을 확인했다.
- 비용 최소화를 위해 현재 EC2는 `stopped` 상태로 둔다.
- 도메인은 구매하지 않는다. 시연 시에는 Elastic IP를 직접 사용한다.
- Ollama는 로컬 전용으로 실행한다. EC2에는 Ollama 서버/모델을 올리지 않는다.

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
- `443/tcp`: 전체 공개, 아직 HTTPS는 설정하지 않음

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
  -> EC2
    -> nginx:80
      -> /            frontend/dist
      -> /backendApi/ backend:8000
      -> /agent/      agent:8001
    -> postgres:5432  EC2 내부 컨테이너
    -> redis:6379     EC2 내부 컨테이너
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

## 확인한 연결

EC2를 켠 상태에서 아래를 확인했다.

```text
GET /                  -> frontend 정적 페이지 응답
GET /health            -> backend health 응답
GET /nginx-health      -> ok
GET /backendApi/       -> {"message":"안녕하세요!"}
GET /agent/health      -> {"status":"ok"}
POST /agent/chat       -> 잔액 조회 응답 성공
```

확인 명령:

```bash
curl http://15.164.26.234/health
curl http://15.164.26.234/nginx-health
curl http://15.164.26.234/backendApi/
curl http://15.164.26.234/agent/health
curl -X POST http://15.164.26.234/agent/chat \
  -H 'content-type: application/json' \
  -d '{"message":"생활비 통장 잔액 얼마야?"}'
```

## Ollama 정책

Ollama는 로컬 개발/실험 전용이다.

- 로컬 머신에는 Ollama 서버와 모델을 둘 수 있다.
- EC2에는 Ollama 서버나 모델을 설치하지 않는다.
- 코드와 환경변수에는 Ollama provider를 포함한다.
- EC2 데모는 `LLM_PROVIDER=openai` 또는 LLM 실패 시 규칙 기반 fallback 경로로 동작하게 둔다.

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

## 비용 관리

평소에는 EC2를 stop한다.

```bash
aws ec2 stop-instances \
  --instance-ids i-07d75abca7ba7a423 \
  --region ap-northeast-2 \
  --profile kdt-team3-infra
```

EC2를 stop해도 남을 수 있는 비용:

- EBS root volume: `vol-07152b79beb161283`
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
- 평소에는 비용 절감을 위해 EC2를 꺼둔다.
- EC2를 켜면 같은 Elastic IP로 다시 접근할 수 있다.
- Ollama는 로컬 전용이며, EC2 배포 런타임에는 포함하지 않는다.
