# 워크플로우 라우팅 리팩터링 — 트러블슈팅 기록

작성일: 2026-07-25 / 대상: Agent 담당자
관련 PR: #68(분류기·검증기 분리), #69(Resolution 순수화 + 라우팅 HITL)

## 배경

워크플로우 라우팅(사용자 발화 → 실행할 업무 워크플로우 결정)은 Agent의 첫 관문이다. 기존 구조는 **결정론 선가드 → 단일 LLM 분류 → 키워드 폴백**이었는데, 실사용에서 오분류가 반복돼 구조를 **분류기 → 검증기 → 순수 Resolution → (모호 시) 사용자 확인**으로 전환했다. 이 문서는 그 과정에서 발견한 문제 4건과 해결, 그리고 테스트/실측 결과의 변화를 기록한다.

---

## 문제 1 — 결정론 선가드의 과잉 포섭

### 증상
"이제부터 신한 부계좌에서 나가게 해줘"(기본계좌 설정)나 "신한 부계좌에 얼마 있어?"(조회) 같은 발화가 **본인이체(`wf_internal_transfer`)로 오분류**됐다.

### 원인
`_is_own_account_transfer` 결정론 선가드가 LLM보다 **먼저** 워크플로우를 확정했다. `부계좌`·`내 계좌`처럼 여러 워크플로우에 공통으로 등장하는 **엔티티 표현**이 있고 이체 동사가 우연히 겹치면, 문장 전체 의도를 보기 전에 본인이체로 가로챘다. 결정론이 LLM보다 위에 있어 맥락 교정 기회 자체가 없었다.

### 해결 (PR #68 → #69)
- 라우팅을 **분류기(WorkflowClassification) + 검증기(WorkflowVerification)** 2단계로 분리. 분류기가 문장 전체 행위로 후보를 고르고, 검증기가 그 결과와 발화의 모순을 검사한다.
- 결정론 선가드를 "LLM보다 먼저 확정"에서 제거하고, `부계좌`를 라우팅 신호로 쓰지 않도록 했다(엔티티일 뿐 행위 신호가 아님).
- 검증기가 오분류를 잡으면 조회·설정형은 자동 수정, 실행형 충돌은 사용자 확인으로 보류.

### 결과
로컬 Ollama·Vertex 실측에서 과잉 포섭 3케이스(부계좌 설정/별칭/조회)가 모두 정확한 워크플로우로 분류됐다. 벤치마크의 `overcapture_acc`가 구형 75%(Ollama)에서 신형 100%로 개선(문서 `routing-refactor-benchmark.md`).

---

## 문제 2 — 결정론이 여전히 자연어를 재판단 + LLM 실패 시 강제 확정

### 증상
PR #68 직후에도 (a) 키워드 폴백/강가드가 분류기·검증기의 정상 결론을 뒤집을 수 있었고, (b) LLM 호출이 실패하면 키워드로 워크플로우를 **강제 확정**했다. 금융 Agent에서 "정확히 알 수 없는데 일단 실행"은 위험하다.

### 원인
결정론 폴백이 "세 번째 분류기"처럼 자연어 의미를 다시 판단하고 있었다. 예: `"부계좌"`가 있으면 키워드 규칙이 본인이체로, `"민수한테 쏴줘"`처럼 등록되지 않은 동사는 폴백이 놓쳐 오분류.

### 해결 (PR #69 Part A)
- **결정론 재판단 전면 제거**: `extract_routing_signals`, `_KEYWORD_RULES`, 강가드, `deterministic_fallback` 삭제. 검증기 프롬프트에서 결정론 신호 블록 제거.
- 결정론은 **Resolution 정책**만 담당: 출력 유효성 검증, 두 결과 결합, 자동수정 가능 여부, 사용자 확인 필요 여부, 안전 실패.
- `resolve_workflow` 재작성: primary 무효→`failed`, classifier ambiguous는 검증기 accept여도 유지, reject+corrected는 **조회형→조회형만 자동수정**·그 외 ambiguous, `primary==corrected`인 reject는 논리 오류로 `failed`.
- **LLM 실패 시 키워드 강제 확정 금지 → `status=failed`로 안전 종료.** 환경변수 `WORKFLOW_VERIFIER_ENABLED`/`_FAIL_MODE`/`_QUERY_AUTO_CORRECTION_ENABLED`로 동작 제어.

### 결과
`agent/tests` resolve 정책 순수함수 테스트 재작성(20+ 케이스). 전체 스위트 통과. 모호 발화가 강제 확정되지 않고 ambiguous로 처리됨(문제 4에서 모델별 이슈 추가 발견·수정).

---

## 문제 3 — 라우팅 단계에 사용자 확인(HITL)이 없어 정상 발화가 유실

### 증상
자동수정을 좁히자(조회형만 자동) 실행형 충돌·모호 발화가 늘었는데, 이를 `no_match`로 버리면 "이제부터 부계좌에서 나가게 해줘" 같은 발화가 처리되지 못하고 데모가 후퇴했다.

### 원인
워크플로우 "내부" HITL(계좌 선택 등)은 있었지만, 라우팅 "단계"에서 사용자에게 되묻는 흐름이 없었다. Resolution이 ambiguous를 내도 소비할 곳이 없어 버려졌다.

### 해결 (PR #69 Part B)
- `contract_agent` 상위 그래프에 `request_workflow_clarification` 노드 추가. ambiguous면 `need_input(option_select)`로 후보 업무를 되묻고, 선택한 workflow_id로 해당 워크플로우에 진입. 취소·후보부족은 안전 종료.
- 매니페스트(`wf_global_agent_entry`)에 clarification step + `UI-WORKFLOW-CLARIFICATION` 계약 + `resume.value` 매핑 + state_key를 추가하고 엑셀·JSON을 재생성.
- **기존 interrupt/resume 런타임·Backend·Frontend `OptionSelectUI`를 그대로 재사용(변경 0).** 후보를 option payload로 전달하는 것만으로 동작.

### 부수 문제 — 매니페스트 재생성 도구 누락
매니페스트는 엑셀(`agent-management-sheet-v3.xlsx`)에서 생성되는데, 그 도구 `openpyxl`이 워크트리 `.venv`에 설치돼 있지 않아 `export --check`가 실패하고 있었다(기존 `test_workflow_contract_export` 2건 실패의 진짜 원인). `openpyxl`은 `[dependency-groups] dev`에 선언돼 있어 `uv sync --group dev`로 설치하면 해소된다. 설치 후 엑셀↔JSON 일치를 확인하고 clarification step을 반영했다.

### 결과
clarification 흐름 통합 테스트 2건(취소 안전종료 / 선택 후 워크플로우 진입) 추가·통과. `export --check` 통과, 기존 contract_export 실패도 함께 해소. 전체 298 passed.

---

## 문제 4 — Vertex(gemini)가 문자열 "null"을 반환해 모호 발화가 failed로 오처리

### 증상
Ollama에서는 정상이던 모호 발화("신한 계좌로 해줘", "계좌 관련해서 뭘 할 수 있어?")가 **Vertex(gemini-2.5-flash)에서는 ambiguous가 아니라 `failed:invalid_classifier_output`**로 빠졌다. 정상(명확) 발화는 문제없었다.

### 원인
Gemini가 structured output에서 JSON `null` 대신 **문자열 `'null'`**을 `primary_workflow_id`에 채웠다(Ollama는 진짜 `None`을 반환해 드러나지 않았음). `resolve_workflow`가 `"null"`을 카탈로그에 없는 **무효 ID**로 오인해 안전 실패 처리했다. 모델별 structured output 구현 차이로 인한 이식성 버그.

### 해결 (커밋 6d03061)
`classify_workflow`/`verify_workflow`에서 placeholder 문자열(`null`/`none`/`n/a`/빈 문자열 등)을 실제 `None`으로 정규화하는 `_normalize_workflow_id`를 추가했다. 회귀 테스트 추가.

### 결과
Vertex 재실측에서 모호 발화가 정상적으로 ambiguous로 처리됨. Vertex·Ollama 양쪽 벤치마크 모두 전 지표 100%. **이 버그는 Vertex로 교차 검증하지 않았으면 발견하지 못했을 모델 이식성 결함이라, 다중 프로바이더 실측의 가치를 보여준다.**

---

## 요약: 문제 → 해결 → 지표 변화

| 문제 | 해결 | 지표 변화(구형→신형, 벤치마크 참조) |
|------|------|------------------------------------|
| 결정론 선가드 과잉 포섭 | 분류기·검증기 분리, 엔티티를 신호로 안 씀 | overcapture 75%→100% (Ollama) |
| 결정론 재판단 + 실패 시 강제확정 | 순수 Resolution + 안전 실패 | ambiguity_safety 50/75%→100% |
| 라우팅 HITL 부재 | clarification 노드 + 매니페스트 | ambiguous 발화를 되묻어 유실 방지 |
| Vertex "null" 문자열 | placeholder 정규화 | Vertex overall 90%(수정 전 모호 failed)→100% |

전체 정확도(overall)는 구형 80%(Ollama)/90%(Vertex)에서 신형 100%/100%로 개선됐다. 자세한 수치·재현 방법은 `routing-refactor-benchmark.md` 참조.
