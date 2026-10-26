# 현준수 담당 범위 · 금융 AI 에이전트

kt cloud TECH UP 생성형 AI 과정의 팀 프로젝트입니다. 실제 금융망 대신 가상 자금과 모의 금융 서비스를 사용하는 검증 환경을 만들었습니다.

## 담당한 영역

| 영역 | 작업 |
| --- | --- |
| 배포·연결 | Docker Compose, AWS EC2 시연 구성, RDS·Nginx 관련 연결 문제 대응 |
| 개발 검증 | GitHub Actions와 보안 검사, 배포 환경 검증 관련 작업 |
| 레드팀 | 로컬 Agent Testbed를 대상으로 적응형 공격 생성·판정·보고 흐름 구현·보완 |

개인 기여는 배포·검증 영역에 해당하며, 팀이 구현한 금융 기능과 연결해 작업했습니다.

## 기술 작업을 보는 위치

- [레드팀 실행·판정 구조](../security/redteam/README.md)
- [검증 범위](../security/redteam/WORKFLOW_COVERAGE.md)
- [AWS 최종 시연 구조](aws-ec2-demo-deploy.md)
- [최종 배포·연결·보안 인계 기록](devsecops-handoff.md)

## 검증 결과를 해석하는 기준

레드팀 결과는 로컬 가상 자금·Agent Testbed 범위의 검증입니다. 테스트 실패가 곧 취약점 하나를 의미하지는 않으며, 호출 계약 불일치와 실제 보안 경계 위반을 나눠 봅니다. 최종 시연의 연결 확인과 장기 운영 안정성도 별개입니다.
