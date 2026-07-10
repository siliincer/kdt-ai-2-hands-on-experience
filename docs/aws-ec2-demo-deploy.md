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
- `/agent/`: agent (`agent:8001`)

EC2에서는 `docker-compose.ec2.yml`로 nginx의 `80/tcp`를 공개한다. 기본 compose의
backend/agent/postgres/redis 포트는 `127.0.0.1`에만 바인딩되어 외부에는 열리지
않는다.

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
```

외부 검증:

```bash
curl http://15.164.26.234/health
curl http://15.164.26.234/nginx-health
curl http://15.164.26.234/backendApi/
curl http://15.164.26.234/agent/health
curl -X POST http://15.164.26.234/agent/chat \
  -H 'content-type: application/json' \
  -d '{"message":"생활비 통장 잔액 얼마야?"}'
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

RDS는 `2026-07-15 10:45:02 KST`쯤 자동 재시작 예정이므로, 사용하지 않으면 그 전에
다시 stop하거나 삭제 여부를 결정한다.
