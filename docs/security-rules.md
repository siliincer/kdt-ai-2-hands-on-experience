# Security Rules

이 문서는 MVP 개발 단계에서 지켜야 할 기본 보안 규칙을 정리한다.

## Secret 관리

- 실제 secret은 Git에 커밋하지 않는다.
- `.env`는 로컬 전용 파일로 사용하고, 저장소에는 `.env.example`만 커밋한다.
- GitHub Actions에서 필요한 secret은 GitHub Secrets에 저장한다.
- `OPENAI_API_KEY`, `HF_TOKEN`, `JWT_SECRET_KEY`, `DISCORD_WEBHOOK_URL`, DB 비밀번호는 코드와 문서에 실제 값으로 남기지 않는다.
- secret이 커밋된 경우 즉시 키를 폐기하고 재발급한다.

## 환경변수 규칙

- 새 환경변수가 필요하면 `.env.example`에 placeholder와 함께 추가한다.
- 환경변수 이름은 대문자와 `_`를 사용한다.
- 로컬 기본값은 개발 편의를 위한 값만 사용하고, 운영/시연 secret은 별도로 관리한다.

## 로그 규칙

- 토큰, API key, 비밀번호, Authorization header는 로그에 남기지 않는다.
- 계좌번호, 이메일, 사용자 입력 등 민감할 수 있는 값은 마스킹하거나 내부 ID만 기록한다.
- 모든 요청 로그에는 가능하면 `request_id`를 포함한다.

## PR 체크 기준

- `.env` 또는 실제 secret이 포함되지 않았는지 확인한다.
- 새 포트, 새 환경변수, 새 외부 API 의존성이 있으면 PR 본문에 적는다.
- DB 스키마나 seed data 변경이 있으면 실행 방법을 함께 남긴다.
- 보안에 영향이 있는 변경은 리뷰 요청 사항에 명시한다.
