# Agent Workflow Testbed

Frontend와 Backend가 완성되기 전에 Workflow를 검증하고, 같은 Scenario를 실제 연동까지 확장하기 위한 Notebook 모음이다.

| 단계 | 검증 대상 | 외부 시스템 |
| --- | --- | --- |
| Level 0 | 생성된 Workflow, API와 UI 계약 | 없음 |
| Level 1 | Agent 내부 Slot 추출과 Route 입력 | 없음 |
| Level 2 | Tool API, Webhook, Interrupt와 Resume | Mock Backend |
| Level 3 | Agent Tool API와 Webhook | 실제 Backend |
| Level 4 | 사용자 입력부터 화면 표시까지 | Frontend와 Backend |

Notebook은 사용자 발화, Step별 State, Tool API 요청·응답, Webhook과 Resume 값을 순서대로 확인한다. 실제 실행 코드는 `agent.testing.WorkflowTestbed`에 있고 pytest도 같은 Harness를 사용한다.

## 처음 실행

레포 루트는 `.venv`와 `pyproject.toml`이 있는 `kdt-ai-2-hands-on-experience` 폴더다.

```bash
uv sync
```

VS Code 또는 Cursor에서는 Notebook 우측 상단의 Kernel에서 레포 루트의 `.venv/bin/python`을 선택한다. 목록에 없으면 `Python: Select Interpreter`의 `Enter interpreter path...`에서 해당 파일을 직접 선택한다.

브라우저에서 실행하려면 다음 명령을 사용한다.

```bash
uv run --with jupyter jupyter lab
```

Notebook Kernel 이름은 공용 `python3`로 저장한다. 각 개발자는 자신의 `.venv`를 선택하며 개인 PC의 Kernel 이름이나 절대경로를 Notebook에 저장하지 않는다.

## Workflow Notebook

| Notebook | Workflow | 기본 검증 Scenario |
| --- | --- | --- |
| `01_balance_inquiry_testbed.ipynb` | `wf_balance_inquiry` | 계좌 선택 후 잔액 조회 |
| `04_account_list_testbed.ipynb` | `wf_account_list` | 별칭 힌트로 계좌 목록 조회 |
| `05_transaction_history_testbed.ipynb` | `wf_transaction_history` | 계좌 선택 Resume 후 첫 페이지 조회 |
| `06_period_amount_summary_testbed.ipynb` | `wf_period_amount_summary` | 이번 달 배민 지출 합계 조회 |

각 Notebook을 위에서부터 실행한다.

- 기본 실행은 외부 통신이 없는 Mock Backend Mode다.
- Slot 추출은 설정된 LLM을 우선 사용하며, LLM을 사용할 수 없으면 같은 Cell에서 결정적 규칙 폴백 결과를 확인할 수 있다.
- 실제 Backend를 호출할 때만 마지막 Cell의 `RUN_REAL_BACKEND`를 `True`로 변경한다.
- 실제 Token, Secret과 전체 금융 Payload는 Notebook 출력이나 Git에 저장하지 않는다.
- Notebook 출력은 커밋하지 않는다. 재현 여부는 pytest로 보장한다.

## Workflow별 확장 규칙

공통 Harness와 Workflow별 조립 코드를 분리한다.

```text
src/agent/testing/
├── workflow_testbed.py       # 공통, 통합 담당자 소유
├── mock_backend.py           # 공통, 통합 담당자 소유
├── balance_inquiry.py        # 잔액조회 담당자 소유
└── <workflow_name>.py        # 각 Workflow 담당자가 추가
```

새 Workflow 담당자는 공통 Harness에 Factory를 추가하지 않는다. 자기 파일에서 `create_workflow_testbed()`에 Workflow Graph Factory를 주입한다. 상세 절차는 `docs/agent-workflow-development-guide.md`를 따른다.

Level 3는 Agent와 Backend 사이의 Tool API와 Webhook 계약을 검증한다. Frontend 입력과 Backend 검증을 포함한 Level 4는 Backend 실행 시작·Resume Endpoint와 브라우저 E2E에서 별도로 검증한다.
