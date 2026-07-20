"""생성된 Workflow 계약 Manifest를 조회하는 공통 Store."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULT_MANIFEST_PATH = (
    Path(__file__).resolve().parents[2] / "contracts" / "workflow-contracts.json"
)


class WorkflowContractNotFoundError(KeyError):
    """요청한 Workflow 또는 계약이 Manifest에 없는 경우."""


class WorkflowContractStore:
    """개발자가 XLSX를 직접 해석하지 않도록 정규화된 계약을 제공한다."""

    def __init__(self, manifest_path: Path = DEFAULT_MANIFEST_PATH) -> None:
        self._manifest_path = manifest_path
        self._manifest: dict[str, Any] = json.loads(
            manifest_path.read_text(encoding="utf-8")
        )

    @property
    def manifest_version(self) -> str:
        return str(self._manifest["manifest_version"])

    def workflow_ids(self) -> tuple[str, ...]:
        return tuple(str(workflow_id) for workflow_id in self._manifest["workflows"])

    def get_workflow(self, workflow_id: str) -> dict[str, Any]:
        workflow = self._manifest["workflows"].get(workflow_id)
        if workflow is None:
            raise WorkflowContractNotFoundError(
                f"등록되지 않은 workflow_id입니다: {workflow_id}"
            )
        return workflow

    def get_contract(self, contract_id: str) -> dict[str, Any]:
        contract = self._manifest["contracts"].get(contract_id)
        if contract is None:
            raise WorkflowContractNotFoundError(
                f"등록되지 않은 contract_id입니다: {contract_id}"
            )
        return contract

    def required_contract_ids(
        self,
        workflow_id: str,
        *,
        contract_type: str | None = None,
    ) -> set[str]:
        workflow = self.get_workflow(workflow_id)
        contract_ids = {
            str(step["contract_id"])
            for step in workflow["steps"]
            if step.get("contract_id")
        }
        if contract_type is None:
            return contract_ids
        return {
            contract_id
            for contract_id in contract_ids
            if self.get_contract(contract_id)["contract_type"] == contract_type
        }

    def step_data_mappings(
        self,
        workflow_id: str,
        step_id: str,
        *,
        direction: str | None = None,
    ) -> tuple[dict[str, Any], ...]:
        workflow = self.get_workflow(workflow_id)
        mappings = (
            mapping
            for mapping in workflow["step_data_mappings"]
            if mapping["step_id"] == step_id
        )
        if direction is not None:
            mappings = (
                mapping for mapping in mappings if mapping["direction"] == direction
            )
        return tuple(mappings)
