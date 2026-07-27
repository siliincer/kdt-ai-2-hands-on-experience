# Docs

프로젝트 문서와 운영 가이드를 관리하는 디렉터리입니다.

## 서비스별 문서

- **frontend**: [`frontend/README.md`](../frontend/README.md) — React 채팅 UI 실행·개발 가이드
- **backend**: [`backend/README.md`](../backend/README.md) — Backend Gateway 실행·API 가이드
- **agent**: [`agent/README.md`](../agent/README.md) — Agent 실행·구조 가이드
- **agent 상세 문서**: [`agent/docs/`](../agent/docs/) — 에이전트 아키텍처, 가드레일·워크플로우 관련 문서
- **mock financial service**: [`mock-financial-service/README.md`](../mock-financial-service/README.md) — Fake Money 계정계/정보계
- **red team**: [`security/redteam/README.md`](../security/redteam/README.md) — Adaptive LLM 기반 보안 회귀와 Reference Campaign
- **observability**: [`observability/README.md`](../observability/README.md) — 트레이스·메트릭·대시보드

## 운영 문서

- [`local-development.md`](./local-development.md): 로컬 개발 환경과 Docker Compose 실행 방법
- [`security-rules.md`](./security-rules.md): Secret, 로그, PR 보안 규칙
- [`aws-ec2-demo-deploy.md`](./aws-ec2-demo-deploy.md): 최종 EC2 시연 배포 구조와 재현·검증 절차
- [`devsecops-handoff.md`](./devsecops-handoff.md): 최종 배포·연결·보안 상태와 프로젝트 종료 정리 기준
- [`aws-ec2-deploy.md`](./aws-ec2-deploy.md): ECR/자동 배포 확장 방향을 기록한 이전 초안
- 장애 대응 Runbook

현재 실제 코드와 다른 과거 설계안은 삭제하지 않고 `초안` 또는 `Archive` 여부를 문서 상단에 표시합니다.
실제 Secret, 계좌번호, 인증값, API Key는 문서에 기록하지 않습니다.
