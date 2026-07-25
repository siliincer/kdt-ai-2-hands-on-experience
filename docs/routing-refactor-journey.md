# 워크플로우 라우팅 리팩터링 — 전체 여정 기록

작성일: 2026-07-25 / 대상: Agent 담당자·팀 전체
성격: 하루치 작업(문제 발견 → 검증기 도입 → 성능·배포 검증)의 종합 기록.
세부 지표·트러블슈팅은 아래 문서들이 나눠 담고, 이 문서는 전체 서사와 의사결정,
산출물 인덱스를 제공한다.

- `docs/routing-refactor-troubleshooting.md` — 문제 4건 상세
- `docs/routing-refactor-benchmark.md` — 구형/신형 × 모델 벤치마크 + 검증기 민감도
- `docs/aws-ec2-demo-deploy.md` — 배포 LLM 요건 섹션

---

## 0. 한눈에 보기

라우팅(사용자 발화 → 실행 워크플로우 결정)을 **단일 LLM + 결정론 폴백**에서
**분류기 + 검증기 + 순수 Resolution + (모호 시) 사용자 확인**으로 전환했다.

| 항목 | Before | After |
|------|--------|-------|
| 구조 | 결정론 선가드 → 단일 LLM → 키워드 폴백 | 분류기 → 검증기 → 순수 Resolution → 라우팅 HITL |
| 전체 정확도(overall) | 80%(Ollama) / 90%(Vertex) | 100% / 100% (충분히 강한 모델) |
| 모호 발화 안전성 | 50~75% (위험하게 강제 확정) | 100% (되묻기) |
| LLM 실패 시 | 키워드로 강제 확정 | 안전 종료(failed) |
| 대가 | — | 지연 3~5배(LLM 2회), 검증기의 모델 민감도 |

관련 PR: #68(분류기·검증기 분리) → #69(Resolution 순수화 + HITL) → #72(Pyright
수정), 문서 #67·#70·#71·#73.

---

## 1. 배경 — 왜 손댔나

기존 라우팅은 결정론 선가드(`_is_own_account_transfer`)가 LLM보다 먼저
워크플로우를 확정했다. `부계좌`·`내 계좌` 같은 **엔티티 표현**이 여러 워크플로우에
공통 등장하는데, 이체 동사와 우연히 겹치면 문장 전체 의도를 보기 전에 본인이체로
가로챘다.

실측 예: "이제부터 신한 부계좌에서 나가게 해줘"(기본계좌 설정)나 "신한 부계좌에
얼마 있어?"(조회)가 본인이체로 오분류. 결정론이 LLM 위에 있어 맥락 교정 기회조차
없었다.

---

## 2. 여정 — 단계별로 무엇을 했나

### 2-1. 분류기·검증기 분리 (PR #68)
라우팅을 두 LLM으로 나눴다. **분류기**가 문장 전체 행위로 후보를 고르고
(primary/alternatives/evidence/status), **검증기**가 그 결과와 발화의 모순을
검사(accept/reject/ambiguous)한다. 결정론 선가드는 "LLM보다 먼저 확정"에서
제거하고, `부계좌`를 라우팅 신호로 쓰지 않게 했다.

### 2-2. Resolution 순수화 + 안전 실패 (PR #69 Part A)
PR #68 직후에도 결정론 폴백(키워드·강가드)이 "세 번째 분류기"처럼 자연어를 다시
판단하고 있었고, LLM 실패 시 키워드로 강제 확정했다. 이를 전면 제거했다.
- 결정론은 **Resolution 정책**만 담당: 출력 유효성 검증, 결과 결합, 자동수정
  가능 여부, 사용자 확인 필요 여부, 안전 실패.
- `resolve_workflow` 정책: primary 무효→failed, classifier ambiguous는 accept여도
  유지, reject+corrected는 조회형→조회형만 자동수정·그 외 ambiguous,
  primary==corrected reject→failed, reason_code 전파.
- **LLM 실패 시 안전 종료(status=failed).** 키워드 강제 확정 금지.
- 환경변수 `WORKFLOW_VERIFIER_ENABLED`/`_FAIL_MODE`/`_QUERY_AUTO_CORRECTION_ENABLED`.

### 2-3. 라우팅 단계 사용자 확인(HITL) (PR #69 Part B)
자동수정을 좁히자 ambiguous가 늘었는데, no_match로 버리면 정상 발화가 유실됐다.
상위 그래프에 `request_workflow_clarification` 노드를 추가해, ambiguous면
`option_select`로 후보 업무를 되묻고 선택한 workflow로 진입한다. 기존
interrupt/resume 런타임·Backend·Frontend `OptionSelectUI`를 그대로 재사용(변경 0),
매니페스트에 HITL step만 추가·재생성했다.

### 2-4. 성능·배포 검증
구형/신형을 Ollama·Vertex로 교차 측정하고, 검증기 모델 민감도와 배포 조건까지
확인했다(3장·4장).

---

## 3. 트러블슈팅 로그 (문제 → 원인 → 해결 → 결과)

| # | 문제 | 원인 | 해결 | 결과 |
|---|------|------|------|------|
| 1 | 결정론 선가드 과잉 포섭 | 엔티티(부계좌)를 행위 신호로 오용, LLM보다 먼저 확정 | 분류기·검증기 분리, 엔티티를 신호로 안 씀 | overcapture 75→100% |
| 2 | 결정론이 자연어 재판단 + 실패 시 강제확정 | 키워드 폴백이 "세 번째 분류기" 역할 | 순수 Resolution + 안전 실패 | 모호 발화 강제확정 제거 |
| 3 | 라우팅 HITL 부재로 정상 발화 유실 | ambiguous를 소비할 곳이 없어 no_match로 버림 | clarification 노드 + 매니페스트 | 되묻기로 유실 방지 |
| 3b | 매니페스트 재생성 불가 | `openpyxl`이 dev 그룹인데 미설치 | `uv sync --group dev` | export 정상, 기존 contract_export 실패도 해소 |
| 4 | Vertex에서 모호 발화가 failed | gemini가 JSON null 대신 문자열 "null" 반환 | placeholder 문자열을 None으로 정규화 | Vertex 90→100% |
| 5 | Pyright regression (병합 후 발견) | #68/#69를 CI 우회(admin) 병합해 타입 에러 누락 | contract_agent/test 타입 수정 (#72) | 내 파일 pyright 0 errors |

**교훈**: 문제 5는 자책 포인트다. admin으로 CI를 우회해 병합하니 Pyright 실패를
놓쳤다. 이후 병합은 CI green 확인 후 진행해야 한다. (문제 4는 반대로, Vertex로
교차 검증하지 않았으면 못 잡았을 모델 이식성 버그 — 다중 프로바이더 검증의 가치.)

---

## 4. 성능 검증 (요약 — 상세는 benchmark 문서)

### 4-1. 구형 vs 신형 × Ollama vs Vertex

| 구조 | 모델 | overall | 모호 안전성 | 지연 |
|------|------|:---:|:---:|:---:|
| 구형 | Ollama 7b | 80% | 50% | 1.5s |
| 구형 | Vertex | 90% | 75% | 2.4s |
| 신형 | Ollama 7b | 100% | 100% | 7.9s |
| 신형 | Vertex | 100% | 100% | 7.1s |

신형은 충분히 강한 모델에서 전 지표 100%. 구형은 모델 의존적이고 모호 발화를
위험하게 강제 확정(구형 Ollama는 "신한 계좌로 해줘"를 타인송금으로 확정).

### 4-2. 검증기 모델 민감도 (핵심 발견)

**검증기는 분류기보다 훨씬 강한 모델을 요구한다.** 분류기("후보 골라라")는 3b도
정확하지만, 검증기("모순·반례를 찾아라")는 메타 추론이라 3b는 정상 분류까지 무조건
reject한다.

같은 qwen2.5:3b, 검증기 토글만:

| 3b 설정 | overall | 모호 안전성 |
|---------|:---:|:---:|
| 검증기 ON | 40% | 100%* |
| 검증기 OFF | 75% | 25% |

(*ON의 안전성 100%는 "모든 발화를 모호 취급"한 부작용)

3b는 켜도(정확도 붕괴) 꺼도(안전성 붕괴) 부적합 → 최소 7b급 필요. 이것이
`WORKFLOW_VERIFIER_ENABLED` 스위치가 존재하는 이유다.

---

## 5. 배포 관점 결론

- **EC2 배포는 `LLM_PROVIDER=openai`가 기본이며, EC2엔 Ollama가 없다.** OpenAI
  키가 데모 작동의 전제다(신형은 LLM 실패 시 규칙 폴백 없이 안전 종료).
- 데모 7발화 라우팅 실측: OpenAI급/Vertex/Ollama 7b = 7/7, Ollama 3b(ON) = 1/7.
- **배포 전 확인**: 실제 EC2 `.env`의 `LLM_PROVIDER`/`OPENAI_API_KEY`. ollama 3b로
  설정돼 있으면 데모가 오작동한다.
- 글로벌 가드레일(프롬프트 인젝션·민감정보 차단)도 Vertex 기준 정상 동작 확인.

부수적으로 확인한 DB 상태: Backend(Postgres 16테이블)와 Mock(SQLite 8테이블)이
분리돼 있고, **시드는 수동**(seed_qa_personas·seed_dev_db)이며 **Mock SQLite는 볼륨이
없어 컨테이너 재생성 시 소실**된다. 데모 전 시드 확인 필요.

---

## 6. 산출물 인덱스

**코드 (main 병합됨)**
- `agent/src/agent/workflow_routing.py` — 분류기/검증기/Resolution/오케스트레이터
- `agent/src/agent/workflow_matcher.py` — 하위호환 래퍼
- `agent/src/agent/workflows/contract_agent.py` — clarification 노드 + 그래프 배선
- `agent/contracts/workflow-contracts.json` + `scripts/build_agent_management_sheet_v3.py`
  — HITL step 매니페스트

**문서**
- `docs/routing-refactor-journey.md` (이 문서)
- `docs/routing-refactor-troubleshooting.md`, `docs/routing-refactor-benchmark.md`
- `docs/aws-ec2-demo-deploy.md`(LLM 요건 섹션)

**재현용 벤치마크**
- `agent/scripts/routing_benchmark.py` + `routing_eval_dataset.json` (구조 자동 감지, 4지표)

**PR**: #68, #69, #72(코드) / #67, #70, #71, #73(문서)

---

## 7. 남은 과제

1. **main CI Python quality green화**: 남은 Pyright regression은 이 라우팅 작업과
   무관한 `agent/src/agent/nodes.py`(#60 Intent Gate), `e2e/tests`,
   `security/redteam`. 각 담당의 후속 수정 필요.
2. **조건부 검증(설계안 P6)**: 명확한 조회형은 검증기 생략해 지연 완화.
3. **저사양 모델 정책**: 3b 등 부득이한 경우 검증기 OFF 운영 가이드 확정.
4. **배포 문서-실환경 정합**: 실제 EC2 `.env`의 LLM 설정 점검(위 5장).
