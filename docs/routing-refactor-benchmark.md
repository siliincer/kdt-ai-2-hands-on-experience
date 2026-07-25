# 워크플로우 라우팅 성능 벤치마크 — 구형 vs 신형 × Ollama vs Vertex

작성일: 2026-07-25 / 대상: Agent 담당자
관련 PR: #68, #69 / 트러블슈팅: `routing-refactor-troubleshooting.md`

## 목적

라우팅 구조 전환(구형: 결정론 선가드 + 단일 LLM + 키워드 폴백 → 신형: 분류기 + 검증기 + 순수 Resolution)의 효과를 정량 측정한다. 로컬 LLM(Ollama)과 클라우드 LLM(Vertex) 양쪽에서 재현해 **모델 의존성**까지 확인한다.

## 평가 방법

- 데이터셋: 20개 발화, 4개 카테고리 (`agent/scripts/routing_eval_dataset.json`).
  - `clear`/`colloquial`(12): 명확·구어체 발화 → 정답 워크플로우와 일치해야 함.
  - `overcapture`(4): 부계좌 등 엔티티 + 설정/조회 발화(구형이 본인이체로 오분류하기 쉬운 케이스).
  - `ambiguous`(4): 의도가 모호한 발화 → 잘못 확정하지 않아야 안전(신형=ambiguous/no_match, 구형=None).
- 지표:
  - **clear_acc**: 명확·구어체 정확도.
  - **overcapture_acc**: 과잉 포섭 케이스 정확도.
  - **ambiguity_safety**: 모호 발화를 잘못 확정하지 않은 비율(금융 안전성 핵심).
  - **overall_acc**: 전체 정답률.
  - **avg_latency_ms**: 발화당 평균 지연.
- 구조 자동 감지: `route_workflow` 존재 시 신형(resolution), 없으면 구형 `match_workflow`.
- 모델: Ollama `qwen2.5:7b`, Vertex `gemini-2.5-flash`(기본).

## 결과 (구조 × 모델)

| 구조 | 모델 | 검증기 | clear | overcapture | ambiguity_safety | **overall** | latency |
|------|------|:---:|:-----:|:-----------:|:----------------:|:-----------:|:-------:|
| 구형 | Ollama qwen2.5:7b | — | 91.7% | 75.0% | 50.0% | **80.0%** | 1.5s |
| 구형 | Vertex gemini-2.5-flash | — | 91.7% | 100.0% | 75.0% | **90.0%** | 2.4s |
| 신형 | Ollama qwen2.5:7b | ON | 100.0% | 100.0% | 100.0% | **100.0%** | 7.9s |
| 신형 | Vertex gemini-2.5-flash | ON | 100.0% | 100.0% | 100.0% | **100.0%** | 7.1s |
| 신형 | Ollama qwen2.5:**3b** | ON | 33.3% | 0.0% | 100.0% | **40.0%** | 3.3s |
| 신형 | Ollama qwen2.5:**3b** | OFF | 83.3% | 100.0% | 25.0% | **75.0%** | 1.8s |

## 해석

### 1. 신형이 충분히 강한 모델에서 전 지표 100%
Ollama 7b·Vertex에서 분류기 + 검증기 + 순수 Resolution이 과잉 포섭과 모호 발화 오처리를 모두 제거했다. 특히 **ambiguity_safety가 구형 50~75%에서 신형 100%**로 오른 것이 핵심 — 구형은 모호 발화를 위험하게 강제 확정했다.

### 2. 신형은 "충분한 모델"에서만 모델 무관 — 검증기가 모델 민감도의 병목
구형 overall은 Ollama 80% ↔ Vertex 90%로 모델에 의존한다. 신형은 7b·Vertex에서 모두 100%로 편차를 흡수하지만, **더 작은 3b에서는 무너진다(아래 별도 섹션).** 즉 신형의 안정성은 "검증기가 제 역할을 할 만큼 모델이 강할 때"만 성립한다.

### 3. 구형의 위험 오답 (금융 안전성)
구형 Ollama에서 **"신한 계좌로 해줘" → 타인송금(`wf_external_transfer`)으로 강제 확정**됐다. 의도가 불명확한데 실행형 워크플로우로 진입시키는 것은 금융 Agent에서 심각한 문제다. 신형은 같은 발화를 ambiguous로 처리해 사용자에게 되묻는다.

### 4. 대가는 지연
신형은 발화당 요청이 분류기+검증기 **2회 LLM 호출**이라 지연이 구형(1회) 대비 **3~5배**(구형 1.5~2.4s → 신형 7~8s). 정확도·안전성과 지연의 트레이드오프다. 완화책:
- `WORKFLOW_VERIFIER_ENABLED=false`로 검증기를 끄면 분류기 1회로 축소(정확도 일부 포기).
- 명확한 조회형은 조건부로 검증 생략(후속 최적화, 설계안 P6).

## 검증기 모델 민감도 (핵심)

**검증기는 분류기보다 훨씬 강한 모델을 요구한다.** 두 LLM의 태스크 난이도가 다르기 때문이다.

- **분류기**("발화에 맞는 워크플로우를 골라라")는 상대적으로 쉬운 태스크로, **3b도 정확히 수행**한다.
- **검증기**("분류 결과와 발화 사이의 모순·반례를 찾아라")는 자기 판단을 다시 의심하는 메타 추론이라 더 어렵다. **3b는 이 역할을 제대로 못 하고, 정상 분류까지 무조건 reject(ACTION_MISMATCH)** 한다(수정안 corrected도 못 냄 → 전부 ambiguous).

같은 3b 모델에서 검증기 ON/OFF만 바꾼 결과가 이를 정량적으로 보여준다.

| 3b 설정 | clear | overcapture | ambiguity_safety | overall | latency |
|---------|:-----:|:-----------:|:----------------:|:-------:|:-------:|
| 검증기 ON | 33.3% | 0.0% | 100.0% | **40.0%** | 3.3s |
| 검증기 OFF | 83.3% | 100.0% | 25.0% | **75.0%** | 1.8s |

- **검증기 ON**: 검증기가 정상 분류를 전부 reject해 명확 발화까지 ambiguous로 빠진다. ambiguity_safety만 100%인 것은 "모든 발화를 모호 취급"한 부작용이라 의미가 없다. overall 40%로 사실상 사용 불가.
- **검증기 OFF**: 분류기만 신뢰하면 명확·과잉포섭은 잘 처리하지만(83%/100%), 모호 발화를 강제 확정해 **ambiguity_safety가 25%로 붕괴**(금융 안전성 상실).

즉 **3b는 검증기를 켜도(정확도 붕괴) 꺼도(안전성 붕괴) 만족스럽지 않다** — 신형 라우팅에 근본적으로 부적합하며, 최소 7b급 이상이 필요하다.

### 운영 권고 (모델 급별)

| 배포 모델 | 검증기 | 근거 |
|-----------|:---:|------|
| OpenAI / Vertex / Ollama 7b+ | **ON** | 검증기가 오분류 교정 + 모호 발화 안전 처리. 전 지표 100% |
| Ollama 3b 등 소형 | (권장 안 함) | ON=정확도 붕괴, OFF=안전성 붕괴. 부득이하면 OFF로 분류기만 사용하되 모호 발화 강제 확정 위험 감수 |

`WORKFLOW_VERIFIER_ENABLED`는 이 모델 민감도 때문에 존재하는 스위치다. "항상 켜는 것"이 정답이 아니라, **배포 모델 급에 맞춰 판단**해야 한다. 배포 기본(OpenAI)에서는 켜 두는 것이 옳다.

## 재현 방법

```bash
# 신형 (feat/workflow-resolution-hardening 워크트리)
cd agent
LLM_PROVIDER=ollama OLLAMA_MODEL=qwen2.5:7b \
  uv run python scripts/routing_benchmark.py new-ollama out_new_ollama.json
LLM_PROVIDER=vertex GOOGLE_CLOUD_PROJECT=<proj> VERTEX_LOCATION=us-central1 \
  uv run python scripts/routing_benchmark.py new-vertex out_new_vertex.json

# 검증기 모델 민감도 (같은 3b, 토글만 변경)
LLM_PROVIDER=ollama OLLAMA_MODEL=qwen2.5:3b \
  uv run python scripts/routing_benchmark.py new-3b-on out_3b_on.json
LLM_PROVIDER=ollama OLLAMA_MODEL=qwen2.5:3b WORKFLOW_VERIFIER_ENABLED=false \
  uv run python scripts/routing_benchmark.py new-3b-off out_3b_off.json

# 구형 (main 스냅샷 등 route_workflow 없는 체크아웃)
# 동일 스크립트가 match_workflow로 자동 폴백해 구형을 측정
LLM_PROVIDER=ollama OLLAMA_MODEL=qwen2.5:7b \
  uv run python scripts/routing_benchmark.py legacy-ollama out_legacy_ollama.json
```

- Vertex는 ADC 인증(`gcloud auth application-default login`)과 프로젝트 설정 필요.
- Ollama는 로컬 데몬(`ollama serve`)과 `qwen2.5:7b` 모델 필요.
- 스크립트·데이터셋: `agent/scripts/routing_benchmark.py`, `agent/scripts/routing_eval_dataset.json`.

## 한계

- 표본 20개로 규모가 작다. 카테고리별 대표 케이스 위주라 추세는 뚜렷하지만, 절대 수치는 표본 확대 시 변동 가능.
- 지연은 로컬 하드웨어·네트워크·모델 로딩 상태에 좌우된다(구형/신형 배수 비교가 유효, 절대값은 참고).
- 정답 라벨은 데모 시나리오 기준으로 저자가 부여했다. 일부 발화("하나계좌"의 소유 모호성 등)는 문맥에 따라 정답이 갈릴 수 있다.
