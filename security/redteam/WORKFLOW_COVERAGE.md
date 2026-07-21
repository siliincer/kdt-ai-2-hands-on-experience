# Workflow Coverage

## 기준

이 문서는 팀 Agent의 업무 기능과 로컬 QA 검사 방식의 조합을 관리합니다. 기능 수와
YAML 파일 수를 같은 의미로 세지 않습니다.

- 행: 팀 Agent의 업무 Workflow 8개
- 열: 로컬 QA 검사 방식 8개
- 셀: 특정 업무 기능을 특정 방식으로 실행한 검증 케이스
- 반복: 각 셀 안에서 생성 모델이 만드는 여러 입력과 seed 실행

기능 정본은 2026-07-21의 `origin/main` commit `e867ccb`와
`agent/src/agent/config/workflows.yaml`입니다. PR #35, #36, #37의 업무 Graph와 PR #39의
글로벌 통합이 main에 반영된 상태를 기준으로 합니다.

## 업무 기능

| Workflow | 기능 | 현재 소스 상태 |
| --- | --- | --- |
| `wf_external_transfer` | 타인 송금 | main 글로벌 Graph 등록 |
| `wf_balance_inquiry` | 잔액 조회 | main 글로벌 Graph 등록 |
| `wf_account_list` | 계좌 목록 | main 글로벌 Graph 등록 |
| `wf_transaction_history` | 거래내역 조회 | main 글로벌 Graph 등록 |
| `wf_period_amount_summary` | 기간 거래 합계 | main 글로벌 Graph 등록 |
| `wf_set_default_account` | 기본 출금 계좌 변경 | main 글로벌 Graph 등록 |
| `wf_set_account_alias` | 계좌 별칭 변경 | main 글로벌 Graph 등록 |
| `wf_internal_transfer` | 본인 계좌 간 이체 | main 글로벌 Graph 등록 |

글로벌 진입 Workflow는 공통 경계이므로 업무 기능 8개에 포함하지 않습니다. 글로벌
진입 검사가 통과해도 각 업무 Workflow가 검증됐다고 계산하지 않습니다.

## 검사 방식

| 방식 | 기능별 확인 대상 |
| --- | --- |
| `prompt_injection` | 기능 수행 중 상위 지시나 내부 규칙이 바뀌지 않는가 |
| `approval_bypass` | 조회 권한 또는 변경 작업의 확인·인증 순서가 유지되는가 |
| `tool_governance` | 해당 기능에 허용된 Tool과 인자만 사용하는가 |
| `data_confidentiality` | 응답·UI·상태에 보호 대상 값이 노출되지 않는가 |
| `risk_manipulation` | 사용자의 주장으로 업무 검증 결과가 변경되지 않는가 |
| `audit_log_tampering` | 기록 생성·내용·순서를 사용자 입력으로 바꿀 수 없는가 |
| `multi_step_attack` | 중간 입력 수정 후 이전 승인이나 검증을 재사용하지 않는가 |
| `conversation_state` | 다른 대화나 Workflow 상태가 현재 기능에 섞이지 않는가 |

조회 기능에는 금융 승인 단계가 없으므로 `approval_bypass`는 승인 버튼을 억지로
추가하는 검사가 아닙니다. 다른 사용자나 검증되지 않은 Context로 조회를 진행할 수
있는지를 확인하는 권한 경계 검사로 적용합니다.

## 현재 커버리지

`workflow_coverage.yaml`이 8 x 8 셀의 정본입니다.

- `planned`: 기능별 입력과 기대 계약이 아직 없음
- `partial`: 현재 로컬 surrogate 또는 팀 Reference Workflow의 일부 경계를 확인했지만
  글로벌 진입부터 최종 증거까지 전체 경로를 검증하지 않음
- `implemented`: 팀 Reference Workflow와 공개 계약을 대상으로 실행하고 증거를 확인함
- `not_applicable`: 해당 Workflow에 검사할 단계나 상태가 없으며 이유가 기록됨

기존 시나리오 실행 증거는 `evidence`, 후속 Agent Testbed 계약 증거는
`reference_evidence`에 분리해 기록합니다. 조회 Workflow 19칸은 글로벌 진입과 업무별
Testbed를 함께 확인해 `implemented`입니다. 설정·이체 32칸은 업무별 Testbed 또는 기존
surrogate 증거가 있지만 최신 글로벌 통합 경로의 재개 문제가 남아 `partial`입니다.
의미 있는 51칸에 `planned` 상태는 없습니다.
전역 입력 검사와 일반 정보 보호 검사는 특정 업무 기능을 통과하지 않으므로 8 x 8
완료 수에 포함하지 않습니다. 따라서 현재 상태를 “8개 기능 검증 완료”라고 표현하지
않습니다.

저장소의 `test_agent_reference_integration.py`는 최신 Agent Testbed를 사용해 참조 파일
50개를 일괄 실행합니다. 읽기 26개와 설정·이체 24개가 모두 업무별 Testbed에서
통과합니다. 다만 설정·이체는 전역 Graph 재개와 원장·감사 변화량 증거가 남아 있으므로
커버리지 셀은 아래 설명대로 `partial`을 유지합니다. 참조 파일 개수는 하나의 파일이
여러 커버리지 셀의 증거가 될 수 있으므로 8 x 8 셀 개수와 같지 않습니다.
완료 상태는 `reference_evidence_manifest.yaml`의 Agent commit, 케이스 ID와 케이스 집합
해시가 통합 실행 결과와 모두 일치할 때만 유지됩니다. Testbed import 실패는 skip이 아닌
CI 실패로 처리합니다.

## 적용성 판단

| Workflow | 적용 방식 수 | 제외 방식과 이유 |
| --- | ---: | --- |
| 타인 송금 | 8 | 없음 |
| 본인 계좌 간 이체 | 8 | 없음 |
| 기본 출금 계좌 변경 | 8 | 없음; 비활성 계좌 정책 우회 여부 포함 |
| 계좌 별칭 변경 | 8 | 없음; 길이·금지어·중복 정책 우회 여부 포함 |
| 잔액 조회 | 5 | 승인, 위험 판단, 변경 감사 단계 없음 |
| 거래내역 조회 | 5 | 승인, 위험 판단, 변경 감사 단계 없음 |
| 기간 거래 합계 | 5 | 승인, 위험 판단, 변경 감사 단계 없음 |
| 계좌 목록 | 4 | 승인, 위험 판단, 변경 감사, 중단·재개 단계 없음 |

전체 64칸 중 실제 적용 대상은 51칸이고 `not_applicable`은 13칸입니다. 제외 항목은
실패나 미구현으로 계산하지 않으며, Agent 계약에 관련 단계가 추가되면 적용성을 다시
검토합니다. 반대로 단순히 입력 문장을 생성할 수 있다는 이유만으로 의미 없는 검사를
적용 대상으로 바꾸지 않습니다.

## 구현 순서

1. 최신 Agent Reference Workflow를 main 또는 합의된 통합 브랜치에서 확정합니다.
2. 로컬 runner가 기존 surrogate 대신 Reference Workflow의 시작·재개 계약을 호출하도록
   adapter를 교체합니다.
3. 조회 4종부터 각 방식의 입력, 응답, Tool 호출, 상태 증거를 연결합니다.
4. 설정 2종은 Prepare, 사용자 확인, Execute와 수정 후 재검증을 연결합니다.
5. 송금 2종은 승인, 추가 인증, 멱등성, 원장 변경, 감사 기록을 연결합니다.
6. 실행 보고서에 Workflow별 8개 셀의 PASS, FAIL, ERROR, 미구현 상태를 집계합니다.
7. 한 모델 조합으로 기능별 smoke를 통과한 뒤 seed·모델 비교를 수행합니다.

기능 구현이 없는 셀은 모델이 문장을 생성했다는 이유만으로 완료 처리하지 않습니다.
조회 기능 19셀의 구체적인 입력·증거 계약은 `READ_WORKFLOW_CASES.md`에 정의합니다.

최신 main 통합 검증에서는 설정 정상 입력 2종과 내부이체 정상 입력이 업무별 Testbed에서
통과했지만, 글로벌 Graph에서 승인 재개 직후 각 업무의 error Webhook으로 종료됐습니다.
중단 가능한 하위 Graph의 State가 글로벌 Graph 재개에서 이어지는지 Agent 담당 수정 후
같은 fixture로 재검증해야 합니다. 설정·이체의 원장·감사 변화량 증거도 연결 전이므로
해당 32칸은 `partial`을 유지합니다.
