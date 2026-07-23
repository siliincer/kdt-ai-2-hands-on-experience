# Agent Integration Contract

## Ownership

The Agent team owns `agent/src/agent/main.py`, `service.py`, and `schemas.py`.
The local QA runner consumes that public contract without modifying Agent source.

## Runtime Generations

The checked-out surrogate currently uses synchronous `POST /chat`. The reference
workflows merged through PR #39 additionally expose contract-based execution through
`POST /internal/v1/executions` and `POST /internal/v1/executions/{agent_thread_id}/resume`.
Those endpoints acknowledge work with HTTP 202 and publish actual progress through
Backend Tool and Webhook clients, so an accepted response is not execution evidence.

The workflow-aware runner must therefore use an injected local testbed adapter for the
reference runtime. It must capture the selected `workflow_id`, invoked contract IDs,
webhook events, pending interaction identifiers, terminal state, and local ledger or
audit deltas. It must not infer workflow execution from message keywords or HTTP 202.
The legacy `/chat` adapter remains a surrogate for the older local scenario runner.
When it cannot expose execution evidence, its response-contract result is not counted
as reference workflow coverage. Only the injected Testbed path can claim that coverage.

`runner/reference_runtime.py` implements bounded evidence conversion for start, input
resume, and runtime-validated approval/authentication resume requests. It records the
observed workflow, runtime/checkpoint status, repeated Tool order, Tool paths, Webhook
steps, pending identifiers, request/context IDs, and trace. All 51 applicable coverage
cells have fixture evidence; 19 read cells also pass the global entry.

## Agent source baseline

레드팀 Reference Campaign은 문서에 특정 Agent commit을 수동으로 고정해
최신 상태라고 간주하지 않는다.

실행 시 다음 경로를 마지막으로 변경한 Git revision을 계산한다.

- `agent/src`
- `agent/pyproject.toml`
- `pyproject.toml`
- `uv.lock`

````bash
git log -1 --format=%H -- \
  agent/src \
  agent/pyproject.toml \
  pyproject.toml \
  uv.lock

`runner/agent_reference.py` and `test_agent_reference_integration.py` replace the
temporary preview script with a repository-owned regression path. The latest Agent
Testbeds execute all 51 reference files: 27 read files and 24 setting or transfer
files. This dedicated-Testbed success does not close the global-graph and ledger or
audit dependencies above. The `runner/reference_cli.py` command uses separate local
generation and judgment models and writes one redacted JSON and Markdown campaign
report.

`reference_evidence_manifest.yaml` pins this completed evidence to Agent commit
`6b247dc7f1d4455308dac5153adc531b68d7391e` and the exact case-set hash. A checkout
without those Agent Testbeds explicitly skips that integration module; verification with
the pinned Agent source fails when execution no longer matches the manifest.
Request and execution-context identifiers are required for a passing case. Checkpoint
trace remains optional because the current Testbed snapshot does not expose populated
trace entries; it must be promoted to required evidence when the Agent runtime does.

## Public Endpoints

### `GET /health`

The response must be a JSON object containing `{"status": "ok"}`.

### `POST /chat`

Request fields:

- `message`: non-empty text, at most 2,000 characters
- `user_id`: local fixture user id
- `thread_id`: omitted for a new turn; returned unchanged when resuming a pending turn

Response fields:

- `reply`: display text
- `status`: `completed`, `waiting_input`, `blocked`, `no_match`, or `failed`
- `thread_id`: non-empty conversation id
- `prompt_for`: opaque pending-state key or `null`
- `ui`: structured UI payload or `null`

Supported UI types are `account_card_list`, `search_select`, `number_input`,
`confirm_modal`, and `auth_request`. Unknown status, malformed state, oversized data,
or an unexpected UI type is rejected or evaluated as a failed contract.

## Conversation State

The runner sends no `thread_id` for a new case. When a response is waiting for input,
the next turn sends the exact returned `thread_id`. A changed id during a resumed flow
is a contract failure. Agent state is in-memory and is reset with the managed process.

## Local-Only Evidence

The managed wrapper adds endpoints that are not part of the deployed Agent API:

- `GET /__local_test__/ledger`: balance, state digest, and audit evidence
- `GET /__local_test__/llm-telemetry`: Target model call and policy marker counts

These endpoints bind to the managed loopback process only. They must not be added to
the deployed Agent service.

For the contract runtime, equivalent evidence belongs in the injected QA adapter rather
than new production endpoints. A case is valid only when the observed workflow ID equals
its declared `target_workflow_id`. A routing mismatch is an invalid execution (`ERROR`),
not a workflow security failure (`FAIL`).

## Change Procedure

Before renaming an endpoint, field, status, or UI type, update the Agent contract owner
and this consumer in the same integration window. Run:

```bash
uv run pytest security/redteam/tests/test_agent_integration.py -q
uv run pytest security/redteam/tests -q
````

The current supported contract is config version `1`, scenario version `1`, and
scenario type `adaptive_attack`.
