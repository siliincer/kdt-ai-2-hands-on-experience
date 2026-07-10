# AWS EC2 Deploy

> 현재 실제 시연 배포 상태와 재기동 절차는
> [`docs/aws-ec2-demo-deploy.md`](./aws-ec2-demo-deploy.md)를 기준으로 한다.
> 이 문서는 ECR/자동 배포까지 확장할 때 참고할 방향성 초안이다.

이 문서는 AWS EC2에서 Docker Compose 기반으로 프로젝트를 시연/운영할 수 있도록 만들기 위한 배포 방향을 정리합니다.

현재 기준은 AWS App Runner나 Amplify 중심 배포가 아니라, EC2 한 대에서 ECR 이미지, Docker Compose, Nginx를 조합하는 구조입니다.

## Target Architecture

```text
GitHub Actions
  -> Docker build
  -> Amazon ECR push
  -> EC2 SSH deploy
  -> docker compose -f docker-compose.prod.yml up -d

User
  -> Nginx
  -> Frontend static files
  -> Backend API
```

## Planned Components

- `backend`: FastAPI backend gateway
- `agent`: AI Agent service, 진입점 확정 후 별도 서비스 또는 backend 연동
- `mock-financial-service`: PM 담당 계정계 별도 서버 예정
- `nginx`: frontend 정적 파일 서빙과 backend reverse proxy
- `postgres`: 로컬/개발은 컨테이너, EC2 배포에서는 RDS 또는 외부 PostgreSQL 검토
- `redis`: 필요 시 EC2 compose 서비스로 포함

## Compose Files

| File | Purpose |
| --- | --- |
| `docker-compose.yml` | 로컬 통합 실행 |
| `docker-compose.dev.yml` | Backend를 호스트에서 실행할 때 필요한 개발 인프라 |
| `docker-compose.prod.yml` | EC2 배포용 Compose 파일 초안 |

`docker-compose.prod.yml`은 현재 backend와 nginx를 우선 포함합니다. DB/Redis는 팀 결정에 따라 컨테이너 또는 외부 관리형 서비스로 분리합니다. Prometheus, Grafana, node-exporter는 후속 모니터링 단계에서 추가합니다.

## Required Environment Variables

EC2에는 `.env`를 직접 배치하고, 실제 secret은 Git에 커밋하지 않습니다.

```env
APP_ENV=prod
LOG_LEVEL=INFO

DATABASE_URL=
REDIS_URL=

JWT_SECRET_KEY=
OPENAI_API_KEY=
HF_TOKEN=

VITE_API_BASE_URL=

DISCORD_ALERT_ENABLED=false
DISCORD_WEBHOOK_URL=
METRICS_ENABLED=false
```

## Deployment Flow

1. GitHub Actions에서 backend Docker image를 빌드합니다.
2. 이미지를 Amazon ECR에 push합니다.
3. frontend는 `npm run build`로 정적 파일을 생성합니다.
4. EC2에 frontend build output과 compose/nginx 설정을 배치합니다.
5. EC2에서 ECR image를 pull하고 `docker-compose.prod.yml`로 서비스를 재시작합니다.

예상 실행 명령:

```bash
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml ps
```

## Health Check

Backend에는 배포와 모니터링 기준점으로 `/health` endpoint를 둡니다.

```bash
curl http://localhost:8000/health
curl http://<ec2-public-host>/backendApi/health
```

예상 응답:

```json
{
  "status": "ok",
  "service": "backend",
  "version": "0.1.0"
}
```

Backend 컨테이너의 내부 포트는 현재 `8000`으로 고정합니다. EC2에서 외부 노출 포트를 바꿔야 할 때는 컨테이너 내부 포트가 아니라 Compose의 host port mapping을 조정합니다.

## Nginx Direction

Nginx는 다음 역할을 담당합니다.

- frontend 정적 파일 서빙
- `/backendApi/` 요청을 backend container로 proxy

초기에는 HTTP 기준으로 구성하고, HTTPS, Route53, 인증서 자동 갱신은 후속 단계에서 다룹니다.

## Monitoring Direction

Prometheus, Grafana, node-exporter는 현재 `docker-compose.prod.yml`에 포함하지 않습니다. 우선 `/health`로 backend 생존 여부를 확인하고, 추후 `/metrics` endpoint와 dashboard 요구사항이 정리되면 모니터링 스택을 추가합니다.

## CI/CD Direction

현재 기본 CI는 lint, test, frontend build, Docker build, secret scan, Trivy scan을 담당합니다.

EC2 배포 자동화는 다음 단계에서 별도 workflow로 확장합니다.

- `deploy` branch 또는 tag push 시 실행
- AWS credential은 GitHub Secrets/Variables 사용
- ECR login
- backend image build/push
- frontend build artifact 전송
- EC2 SSH 접속 후 compose 재시작

## Out of Current Scope

- Kubernetes, EKS
- Terraform 기반 IaC
- Route53과 HTTPS 자동화
- RDS/ElastiCache 고도화
- Blue/Green 또는 Canary 배포
- 고가용성 구성

위 항목은 시연 가능한 EC2 compose 배포가 안정화된 뒤 확장합니다.
