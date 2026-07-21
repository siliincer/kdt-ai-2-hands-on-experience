"""관리시트 Step Data Mapping 기반 Resume-to-State 변환 테스트."""

from __future__ import annotations

from typing import Any, Literal

import pytest
from pydantic import ValidationError

from agent.runtime.hitl import ExecutionResumeRequest, PendingInteraction
from agent.runtime.resume_state_mapper import (
    ResumeStateMapper,
    ResumeStateMappingError,
)
from agent.runtime.resume_validation import ValidatedResume
from agent.workflow_contracts import WorkflowContractStore


def _validated(
    *,
    interaction_type: Literal["input", "approval", "authentication"],
    workflow_id: str,
    step_id: str,
    ui_contract_id: str,
    resume: dict[str, Any],
) -> ValidatedResume:
    identifier_fields: dict[str, str | None] = {
        "input_request_id": None,
        "confirmation_id": None,
        "auth_context_id": None,
    }
    if interaction_type == "input":
        identifier_fields["input_request_id"] = str(resume["input_request_id"])
    elif interaction_type == "approval":
        identifier_fields["confirmation_id"] = str(resume["confirmation_id"])
    else:
        identifier_fields["auth_context_id"] = str(resume["auth_context_id"])

    return ValidatedResume.model_validate(
        {
            "request_id": "req_resume_123",
            "agent_thread_id": "thread_123",
            "pending_interaction": PendingInteraction(
                type=interaction_type,
                workflow_id=workflow_id,
                step_id=step_id,
                ui_contract_id=ui_contract_id,
                **identifier_fields,
            ),
            "resume": resume,
        }
    )


def _mapper() -> ResumeStateMapper:
    return ResumeStateMapper(WorkflowContractStore())


def test_input_resume_maps_only_declared_amount_fields() -> None:
    validated = _validated(
        interaction_type="input",
        workflow_id="wf_external_transfer",
        step_id="request_external_transfer_amount",
        ui_contract_id="UI-TRANSFER-AMOUNT-INPUT",
        resume={
            "type": "input",
            "input_request_id": "input_amount_123",
            "value": {
                "amount_input_outcome": "submitted",
                "amount": 50000,
                "unmapped_field": "must_not_enter_state",
            },
        },
    )

    update = _mapper().map(validated)

    assert update.values == {
        "amount_input_outcome": "submitted",
        "amount": 50000,
    }


def test_single_account_mapping_extracts_first_array_item() -> None:
    validated = _validated(
        interaction_type="input",
        workflow_id="wf_set_default_account",
        step_id="request_default_account_selection",
        ui_contract_id="UI-DEFAULT-ACCOUNT-SELECTION",
        resume={
            "type": "input",
            "input_request_id": "input_account_123",
            "value": {
                "account_selection_outcome": "selected",
                "account_ids": ["acc_002"],
            },
        },
    )

    update = _mapper().map(validated)

    assert update.values == {
        "account_selection_outcome": "selected",
        "account_id": "acc_002",
    }


def test_cancelled_empty_account_array_clears_single_account() -> None:
    validated = _validated(
        interaction_type="input",
        workflow_id="wf_set_default_account",
        step_id="request_default_account_selection",
        ui_contract_id="UI-DEFAULT-ACCOUNT-SELECTION",
        resume={
            "type": "input",
            "input_request_id": "input_account_123",
            "value": {
                "account_selection_outcome": "cancelled",
                "account_ids": [],
            },
        },
    )

    assert _mapper().map(validated).values["account_id"] is None


def test_approval_resume_uses_backend_approval_outcome() -> None:
    validated = _validated(
        interaction_type="approval",
        workflow_id="wf_set_account_alias",
        step_id="request_account_alias_approval",
        ui_contract_id="UI-ACCOUNT-ALIAS-CONFIRMATION",
        resume={
            "type": "approval",
            "confirmation_id": "confirm_alias_123",
            "approval_outcome": "change_requested",
            "change_target": "alias",
        },
    )

    assert _mapper().map(validated).values == {
        "approval_outcome": "change_requested",
        "change_target": "alias",
    }


def test_authentication_resume_maps_auth_status() -> None:
    validated = _validated(
        interaction_type="authentication",
        workflow_id="wf_external_transfer",
        step_id="request_external_authentication",
        ui_contract_id="UI-EXTERNAL-TRANSFER-AUTH",
        resume={
            "type": "authentication",
            "auth_context_id": "auth_123",
            "auth_status": "verified",
        },
    )

    assert _mapper().map(validated).values == {"auth_status": "verified"}


def test_mapper_rejects_missing_required_resume_value() -> None:
    validated = _validated(
        interaction_type="input",
        workflow_id="wf_external_transfer",
        step_id="request_external_transfer_amount",
        ui_contract_id="UI-TRANSFER-AMOUNT-INPUT",
        resume={
            "type": "input",
            "input_request_id": "input_amount_123",
            "value": {"amount": 50000},
        },
    )

    with pytest.raises(ResumeStateMappingError) as raised:
        _mapper().map(validated)

    assert raised.value.code == "REQUIRED_RESUME_VALUE_MISSING"


def test_outdated_frontend_decision_cannot_enter_agent_resume_contract() -> None:
    with pytest.raises(ValidationError):
        ExecutionResumeRequest.model_validate(
            {
                "request_id": "req_resume_123",
                "chat_session_id": "chat_123",
                "execution_context_id": "exec_123",
                "resume": {
                    "type": "approval",
                    "confirmation_id": "confirm_123",
                    "decision": "approve",
                },
            }
        )


def test_all_manifest_resume_paths_use_supported_mapping_grammar() -> None:
    store = WorkflowContractStore()
    for workflow_id in store.workflow_ids():
        workflow = store.get_workflow(workflow_id)
        for mapping in workflow["step_data_mappings"]:
            path = str(mapping.get("contract_field_path") or "")
            if mapping["direction"] != "output" or not path.startswith("resume.value."):
                continue
            field = path.removeprefix("resume.value.").split("[", maxsplit=1)[0]
            value: Any = ["value"] if "[" in path else "value"
            assert (
                ResumeStateMapper._extract_value(
                    {field: value},
                    path=path,
                    required=False,
                )
                is not None
            )
