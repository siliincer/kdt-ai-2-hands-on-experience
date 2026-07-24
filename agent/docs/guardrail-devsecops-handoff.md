# 전역 가드레일 강화 — DevSecOps 인계 문서

작성: 에이전트팀 · 대상: DevSecOps팀
관련 브랜치: `fix/global-guardrail-intent-gate`

---

## 1. 배경

Red Team 실모델 전체 캠페인(51개 실행, PASS 11 / FAIL 33 / ERROR 7)에서
**복합 요청 원자적 차단 실패**가 여러 워크플로우에서 확인됐다.

정상 금융 업무 + 악성 지시(민감정보 공개 / 내부 지침 공개 / 승인·소유권·인증
우회)가 한 요청에 결합되면, Agent가 요청 전체를 차단하지 않고 정상 업무 부분
(송금 준비·실행, 계좌 설정 변경, 조회)을 계속 실행했다.

정확한 표현(과장 금지):

> 민감정보 공개 요구 자체가 실제 정보 유출로 이어지지는 않았지만(state·webhook·
> 응답에 민감정보 포함 증거 없음), 해당 악성 요구가 포함된 요청을 전체 차단하지
> 않고 업무 Tool 실행을 계속했다.

### 근본 원인 (최신 main `3bcca15` 기준)

라이브 실행 경로:
```
main.py → application_runtime → workflows/contract_agent.py: run_global_guardrail
  → nodes.py: global_guardrail_node
    → policy/context_extractor.py: build_global_context (규칙 평가용 변수 생성)
    → policy/guardrail_engine.py: GuardrailEngine.check_global
```

- `build_global_context`가 키워드 휴리스틱 변수 4개(`user_input`, `action_count`,
  `target_owner`, `action_type`)만 만들었다.
- 라이브 경로에서 실제 동작하던 global 규칙은 문자열 매칭 2개뿐:
  `prompt_injection_block`(키워드 2개), `unauthorized_account_access`(3인칭 정규식).
- "계좌번호와 인증값을 보여줘" 같은 민감정보 공개 요구를 표현할 **context 변수
  자체가 없어** 어떤 규칙에도 걸리지 않았다.

---

## 2. 에이전트팀이 이미 구현한 것 (이 브랜치)

정규식 키워드 나열이 아니라, **입력이 공격인지 판정하는 분류 에이전트(Intent
Gate)** 를 전역 진입점에 도입했다.

| 파일 | 내용 |
|---|---|
| `agent/src/agent/policy/intent_gate.py` (신규) | LLM 분류기. `workflow_matcher`와 동일한 `get_llm().with_structured_output` 패턴. |
| `agent/src/agent/policy/context_extractor.py` | 분류 결과(라벨)를 context에 노출. |
| `agent/src/agent/nodes.py` | 공격 판정 시 요청 전체 차단 + Security Decision 기록. |
| `agent/tests/test_intent_gate.py` (신규) | 복합 공격 7종 차단 + 정상 통과 + fail-closed 회귀 테스트. |
| `.env.example` | `GUARDRAIL_INTENT_GATE_ENABLED` 토글 문서화. |

동작:
- 분류가 공격(`is_disallowed=true`)이면 워크플로우 매칭·Tool 실행 **이전에**
  요청 전체를 `blocked` 처리한다(원자적 차단).
- 분류기 장애 시 동작은 `GUARDRAIL_INTENT_GATE_FAIL_MODE`로 정한다:
  - `fallback`(기본): 정규식 키워드 폴백(민감정보 공개/시스템 지침 공개/승인·
    소유권·인증 우회)으로 판정. 매칭 → 차단, 미매칭 → 통과. LLM 장애가 에이전트
    전체 중단으로 이어지지 않게 하는 graceful degradation.
  - `closed`: 순수 fail-closed. LLM 실패 시 요청 전체 차단(최대 보안).
- `GUARDRAIL_INTENT_GATE_ENABLED=false`로 게이트 전체를 끌 수 있다(LLM 없는
  로컬/비상용).
- 기존 3개 YAML 규칙(`prompt_injection_block` 등)은 LLM과 무관하게 항상 동작한다.
  정규식 폴백은 그 위에 민감정보 공개/우회 카테고리 커버리지를 더한다.

### context에 노출되는 변수 (규칙 작성 시 참조 가능)

| 변수 | 값 | 비고 |
|---|---|---|
| `intent_gate_status` | `ok` \| `failed` \| `skipped` | |
| `intent_attack` | `true` \| `false` | 최종 공격 판정 (status=ok일 때만 존재) |
| `intent_category` | `sensitive_disclosure` \| `system_instruction_disclosure` \| `approval_bypass` \| `ownership_bypass` \| `auth_bypass` \| `policy_override` \| `none` | |
| `requested_action` | `disclose` \| `transfer` \| `inquiry` \| `modify` \| `bypass` \| `other` | Red Team 분류기 라벨과 정합 |
| `target` | `sensitive_data` \| `system_instruction` \| `approval` \| `ownership` \| `auth` \| `account` \| `none` | |

---

## 3. DevSecOps에 요청하는 것

> 아래는 에이전트팀이 수정하지 않는다. 정책 소유는 DevSecOps다.
> 가드레일 규칙 정본은 구 관리시트(`18gNcQfyC4EhYZricaSHLXbCmjkT5_VDE1c6jmlgChao`)의
> `Guardrail Rule` 탭이며, 스키마 그대로 사용한다.

### D-1. 세부 차단 규칙 값 확정 (선택)

현재 공격 판정·차단은 Intent Gate 코드가 소유한다. DevSecOps가 라벨 조합에
대해 더 세밀한 정책(특정 category만 차단, 위험도 override 등)을 얹고 싶으면,
위 노출 변수로 `guardrail_rules.yaml`에 규칙을 추가할 수 있다. 예:

```yaml
intent_gate_block:
  rule_name: 복합 공격 차단
  applies_to_scope: global
  applies_to_ids: ['*']
  condition:
    expression: intent_attack == true
  action: block
  risk_level_override: R5
  user_message: 보안상 허용되지 않는 지시가 포함되어 처리할 수 없습니다.
  enabled: true
```

### D-2. 죽은 규칙 정리

라이브 경로에서 동작하지 않는 규칙들. 정리(삭제/재설계) 필요:

- `pii_masking` — 4중 무력화: `enabled=false` + `applies_to_ids=[]` + 존재하지
  않는 변수 `personal_info` 참조 + `info_masking` 액션에 코드 핸들러 없음.
  → 삭제하고 D-1로 대체 권장. `info_masking`은 구현되어 있지 않으니 사용 금지.
- `tool_abuse_block` — `action_count`가 라이브 V3 경로에서 항상 0(스텝 실행 수를
  누적하는 `execution_trace`를 채우는 코드가 없음). 무의미. 폐기하거나, 유지하려면
  카운터 채우기를 에이전트팀에 요청.
- tool scope 규칙 6개(`insufficient_balance`, `high_amount_transfer`,
  `new_recipient_warning`, `approval_required_for_execution`,
  `post_result_validation`, `high_amount_transfer_block`) — 레거시 정리(PR #53)로
  이들을 호출하던 `bank_tools.py`가 삭제됐다. 라이브 경로에서 호출되지 않으므로
  현재 사실상 죽은 규칙이다. 워크플로우별(scope=workflow) 가드레일은 별도 후속
  과제이며, 그때 계약 기반으로 재설계한다.

### D-3. 분류 실패 정책 승인

현재 기본값은 `fail_mode=fallback`(분류기 장애 시 정규식 키워드 폴백으로 판정,
미매칭은 통과)이다. 가용성과 최소 커버리지를 함께 확보하는 절충안이다. 최대
보안이 필요하면 `GUARDRAIL_INTENT_GATE_FAIL_MODE=closed`(전체 차단)로 전환한다.
운영 기본값을 어느 쪽으로 할지 확정 요청.

---

## 4. 함정 (규칙 작성 전 반드시 확인)

- **"누락 변수 = False"**: `GuardrailEngine`은 context에 없는 변수를 참조하는 절을
  조용히 False로 처리한다(오탐 방지 설계). 즉 오타나 존재하지 않는 변수를 쓰면
  **에러 없이 규칙이 무발동**한다. `pii_masking`이 죽은 주된 이유다. 규칙에 새
  변수가 필요하면 에이전트팀에 요청해야 한다(위 2번 표에 없는 변수는 존재하지 않음).
- **`info_masking` 액션은 핸들러가 없다.** 노드는 `block` 액션만 전역 차단으로
  처리한다. 다른 액션이 필요하면 에이전트팀과 협의.
- **운영 트레이드오프**: 게이트 활성 시 모든 요청이 분류 LLM을 1회 거친다(지연
  증가). LLM 장애가 전역 차단으로 이어진다(fail-closed). 운영 반영 전 확인 필요.

---

## 5. Red Team 리포트 프레이밍 정정

- FAIL 33 중 상당수는 보안 취약점이 아니라 **Reference 계약 불일치**
  (`tool_arguments` / `ui_payload` / `terminal_ui_payload`). 별도 트랙에서 실제
  Agent V3 출력 계약 기준으로 기대값을 다시 맞춘 뒤 재판정한다.
- 실제 개인정보/인증값 유출은 없었다 — "유출됐다"가 아니라 "차단하지 못하고
  실행을 계속했다"가 정확하다.
