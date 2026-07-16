# AWS EC2 Deployment Direction

> 이 문서는 과거 production 초안의 대체 안내다. 현재 실제 시연 배포와 재기동 절차는
> [`aws-ec2-demo-deploy.md`](./aws-ec2-demo-deploy.md)를 기준으로 한다.

## Canonical Deployment Path

현재 EC2 배포는 다음 두 Compose 파일만 기준으로 사용한다.

```bash
if [ -d frontend/dist ]; then
  sudo find frontend/dist -xdev ! -user "$(id -u)" -print
  sudo chown -R "$(id -u):$(id -g)" frontend/dist
fi
docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp \
  -v "$PWD/frontend":/app --tmpfs /app/node_modules:rw,exec,mode=1777 -w /app \
  node:24-alpine@sha256:a0b9bf06e4e6193cf7a0f58816cc935ff8c2a908f81e6f1a95432d679c54fbfd \
  sh -c "npm ci && npm run build"
docker compose -f docker-compose.yml -f docker-compose.ec2.yml \
  build mock-financial-service
docker compose --profile maintenance -f docker-compose.yml -f docker-compose.ec2.yml \
  run --rm financial-volume-migrate
docker compose --profile agent \
  -f docker-compose.yml \
  -f docker-compose.ec2.yml up -d --build --wait --wait-timeout 180
```

위 ownership 이관은 과거 root builder를 사용했던 EC2에서 최초 전환 시 한 번만
필요하다. `frontend/dist` 밖의 source나 dependency 소유권은 변경하지 않는다.

`frontend/dist/index.html` 생성은 선택 단계가 아니다. EC2 Nginx healthcheck는 정적
frontend의 `/` 응답까지 확인하므로 산출물이 없으면 배포가 healthy 상태가 되지 않는다.

`financial-volume-migrate`는 과거 root container가 만든 SQLite volume을 non-root
runtime UID/GID로 이관하는 반복 실행 가능한 maintenance 작업이다. 첫 실행 전에는 EBS
snapshot 등으로 원장을 백업하고, 데이터를 지우는 `down -v`를 migration 대신 사용하지
않는다.

이 경로는 PostgreSQL, Redis, Backend, Agent, mock financial service를 loopback에만
게시하고 nginx의 HTTP 80만 외부에 공개한다. 배포 전에는 EC2 환경변수 validator와
렌더링된 Compose 공개 포트 정책을 모두 통과해야 한다.

## Production Compatibility Override

`docker-compose.prod.yml`은 기존 파일 참조를 깨지 않기 위해 남겨 둔 호환 override다.
독립 배포 파일이 아니며 반드시 `docker-compose.yml`과 함께 사용한다. 신규 배포 문서나
자동화에서는 이 경로를 추가하지 않는다. 이 override는 base Compose의 loopback 포트만
유지하며 공개 80 포트와 장기 실행용 restart 정책을 추가하지 않는다.

```bash
docker compose --env-file .env.example --profile agent \
  -f docker-compose.yml \
  -f docker-compose.prod.yml config
```

CI는 이 조합의 구문과 내부 서비스 계약만 확인하며 외부 공개 배포 경로로 검증하지 않는다.
실제 배포에는 위 호환 경로가 아니라 canonical EC2 경로를 사용한다.

## Deferred Work

- HTTPS와 도메인
- ECR 기반 이미지 배포 자동화
- RDS/ElastiCache 전환
- Blue/Green 또는 Canary 배포
- 고가용성 구성

이 항목들은 현재 EC2 데모 흐름과 분리해 후속 단계에서 설계한다.
