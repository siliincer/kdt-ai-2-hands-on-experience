# Docs

프로젝트의 현재 실행, 배포, 보안 기준을 관리합니다.

## 실행과 배포

- [`local-development.md`](./local-development.md): host 및 Docker 기반 로컬 개발
- [`aws-ec2-demo-deploy.md`](./aws-ec2-demo-deploy.md): 현재 EC2 데모 배포와 재기동 기준
- [`aws-ec2-deploy.md`](./aws-ec2-deploy.md): canonical 경로와 과거 prod 호환 파일의 경계
- [`devsecops-handoff.md`](./devsecops-handoff.md): 배포 검증, 비용, 후속 운영 작업

## 보안

- [`security-rules.md`](./security-rules.md): secret, 로그, PR 보안 규칙
- [`security-scenarios.md`](./security-scenarios.md): 제품 보안 시나리오
- [`redteam-architecture.md`](./redteam-architecture.md): 로컬 자동화 red-team 구조

## 서비스별 문서

- [Agent 문서](../agent/docs/): Agent 아키텍처, 실행 계약, workflow 자료
- [Backend 문서](../backend/docs/): Backend API와 데이터 흐름 자료
- [Mock financial service 문서](../mock-financial-service/docs/): Fake Money 원장 구조

실제 코드와 문서가 다르면 실제 코드가 우선하지만, 같은 변경에서 문서도 함께 갱신합니다.
