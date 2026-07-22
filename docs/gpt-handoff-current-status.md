# GPT handoff current status

이 문서는 Codex 없이 일반 GPT 대화만으로도 현재 프로젝트 상태를 빠르게 이어받을 수
있도록 핵심만 정리한 인계 문서다. 기준 시점은 `2026-07-22`이다.

## 현재 브랜치와 PR

- 레드팀 작업 브랜치: `feat/adaptive-redteam-agent-30`
- 레드팀 PR: `#31`
- AWS 상태 공유 PR: `#45`

## 이번에 막 처리한 CI 이슈

- `Python quality checks`:
  예전 실패 로그 기준 원인은 두 가지였다.
  - `reference_evidence_manifest.yaml`의 `agent_source_commit`이 이전 값으로 남아 있던 시점
  - 정책 차단(reference policy block) 케이스 기대값이 이전 Agent 동작과 맞지 않던 시점
  현재 로컬 HEAD에서는 아래 두 테스트가 통과한다.
  - `security/redteam/tests/test_agent_reference_integration.py::test_all_reference_cases_have_reproducible_agent_outcomes`
  - `security/redteam/tests/test_workflow_coverage.py::test_completed_reference_manifest_matches_the_exact_case_set`

- `Trivy filesystem scan`:
  `uv.lock` 안의 `pyasn1 0.6.3`가
  `CVE-2026-59885`, `CVE-2026-59886`로 걸렸다.
  이번 수정에서 `pyasn1 0.6.4`로 올렸다.

## 이번에 실제로 바꾼 것

- `security/redteam/runner/agent_reference.py`
  - adaptive generation 실패 시 보고서 `error_reason`에 실제 예외 상세를 남기도록 수정
  - 목적: `input generation failed`만 보이던 상태에서 실제 실패 원인 추적 가능하게 함

- `uv.lock`
  - `pyasn1 0.6.3 -> 0.6.4`
  - 목적: Trivy HIGH 취약점 2건 해소

- `docs/gpt-handoff-current-status.md`
  - 현재 상태 인계용 문서 추가

## 레드팀 현재 상태

- 로컬 reference runner / testbed 기반 구조는 이미 존재한다.
- 대표 실행 위치:
  - `security/redteam/README.md`
  - `security/redteam/reference_cases/`
  - `security/redteam/reference_evidence_manifest.yaml`
  - `security/redteam/tests/`

- 최근 보완 완료:
  - adaptive generation 실패 원인 가시화
  - 보고서에서 단순 `input generation failed` 대신 상세 이유 확인 가능

- 아직 남아 있는 제품 수준 미완료:
  - Backend 제품 채팅 경로는 아직 `mock_agent_driver` 사용
  - 즉, `frontend -> backend` 실서비스 경로는 아직 실제 Agent `/chat`으로 완전 연결되지 않음
  - 현재 Agent 컨테이너는 독립 실행/검증은 되지만 제품 chat path의 최종 연결은 Backend/AI 계약 작업이 더 필요함

## AWS 현재 상태

- App EC2:
  - instance: `i-07d75abca7ba7a423`
  - public: `15.164.26.234`
  - private: `172.31.0.184`

- Model EC2:
  - instance: `i-029d4908457de6d7c`
  - public: `43.203.215.16`
  - private: `172.31.15.220`
  - Ollama + `exaone3.5:2.4b` 설치 완료

- RDS:
  - `kdt-team3-postgres`

- 현재 확인된 것:
  - `http://15.164.26.234/` frontend 응답
  - `http://15.164.26.234/health` backend health 응답
  - `http://15.164.26.234/backendApi/` backend root 응답
  - App EC2 -> Model EC2 private Ollama 연결 확인
  - Agent 컨테이너 환경변수에서
    `LLM_PROVIDER=ollama`
    `OLLAMA_BASE_URL=http://172.31.15.220:11434`
    `OLLAMA_MODEL=exaone3.5:2.4b`
    반영 확인

## AWS 쪽에서 중요한 제한

- 외부 공개는 nginx `80`만
- backend/agent/postgres/redis는 loopback 바인딩
- Agent API는 외부 공개하지 않음
- 현재 제품 backend chat path는 mock 기반이라,
  AWS에서 "Agent가 모델을 실제 호출하는가"와
  "제품 frontend/backend path가 실제 Agent로 연결되는가"는 다른 문제다

## 다음에 누가 이어서 보면 좋은 순서

1. PR `#31`의 최신 CI 상태 확인
2. `uv.lock` 변경이 Trivy를 실제로 통과시키는지 확인
3. 필요하면 `gh pr checks 31` 또는 해당 run rerun
4. Backend의 `mock_agent_driver`를 실제 Agent 중계 경로로 교체할지 결정
5. 제품 chat path 연결 작업은 Backend/AI 계약 기준으로 진행

## 빠른 확인 명령

```bash
git status -sb
gh pr checks 31 --repo siliincer/kdt-ai-2-hands-on-experience
uv run pytest security/redteam/tests/test_agent_reference_integration.py::test_all_reference_cases_have_reproducible_agent_outcomes -q
uv run pytest security/redteam/tests/test_workflow_coverage.py::test_completed_reference_manifest_matches_the_exact_case_set -q
```
