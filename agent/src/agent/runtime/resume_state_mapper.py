"""검증된 Resume 값을 관리시트 계약에 따라 Workflow State로 매핑한다."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from agent.runtime.hitl import ApprovalResume, AuthenticationResume, InputResume
from agent.runtime.resume_validation import ValidatedResume
from agent.workflow_contracts import WorkflowContractStore

ResumeMappingErrorCode = Literal[
    "RESUME_MAPPING_NOT_FOUND",
    "UNSUPPORTED_MAPPING_PATH",
    "REQUIRED_RESUME_VALUE_MISSING",
    "RESUME_VALUE_TYPE_MISMATCH",
]
_RESUME_PATH_PATTERN = re.compile(
    r"^resume\.value\.(?P<field>[a-z][a-z0-9_]*)(?:\[(?P<index>\d+)\])?$"
)
_MISSING = object()


class ResumeStateUpdate(BaseModel):
    """단일 HITL Step Resume로 생성한 Workflow State 변경분."""

    model_config = ConfigDict(extra="forbid")

    workflow_id: str
    step_id: str
    values: dict[str, Any]


class ResumeStateMappingError(ValueError):
    """Resume 값과 관리시트 Step Data Mapping을 적용할 수 없는 경우."""

    def __init__(
        self,
        *,
        code: ResumeMappingErrorCode,
        reason: str,
    ) -> None:
        super().__init__(reason)
        self.code = code
        self.reason = reason


class ResumeStateMapper:
    """`resume.value.*` 경로만 허용하여 State 오염을 차단한다."""

    def __init__(self, contract_store: WorkflowContractStore) -> None:
        self._contract_store = contract_store

    def map(self, validated: ValidatedResume) -> ResumeStateUpdate:
        pending = validated.pending_interaction
        mappings = tuple(
            mapping
            for mapping in self._contract_store.step_data_mappings(
                pending.workflow_id,
                pending.step_id,
                direction="output",
            )
            if str(mapping.get("contract_field_path") or "").startswith(
                "resume.value."
            )
        )
        if not mappings:
            raise ResumeStateMappingError(
                code="RESUME_MAPPING_NOT_FOUND",
                reason=(
                    f"[{pending.workflow_id}/{pending.step_id}] "
                    "Resume 출력 매핑이 없습니다."
                ),
            )

        resume_value = self._normalize_resume_value(validated)
        state_values: dict[str, Any] = {}
        for mapping in mappings:
            state_key = str(mapping["state_key"])
            path = str(mapping["contract_field_path"])
            required = bool(mapping["required_at_step"])
            value = self._extract_value(resume_value, path=path, required=required)
            if value is not _MISSING:
                state_values[state_key] = value

        return ResumeStateUpdate(
            workflow_id=pending.workflow_id,
            step_id=pending.step_id,
            values=state_values,
        )

    @staticmethod
    def _normalize_resume_value(validated: ValidatedResume) -> dict[str, Any]:
        resume = validated.resume
        if isinstance(resume, InputResume):
            return dict(resume.value)
        if isinstance(resume, ApprovalResume):
            return {
                "approval_outcome": resume.approval_outcome,
                "change_target": resume.change_target,
            }
        if isinstance(resume, AuthenticationResume):
            return {"auth_status": resume.auth_status}
        return {}

    @staticmethod
    def _extract_value(
        resume_value: dict[str, Any],
        *,
        path: str,
        required: bool,
    ) -> Any:
        match = _RESUME_PATH_PATTERN.fullmatch(path)
        if match is None:
            raise ResumeStateMappingError(
                code="UNSUPPORTED_MAPPING_PATH",
                reason=f"지원하지 않는 Resume 매핑 경로입니다: {path}",
            )

        field = match.group("field")
        if field not in resume_value:
            if required:
                raise ResumeStateMappingError(
                    code="REQUIRED_RESUME_VALUE_MISSING",
                    reason=f"필수 Resume 값이 없습니다: {path}",
                )
            return _MISSING

        value = resume_value[field]
        index_text = match.group("index")
        if index_text is not None:
            if not isinstance(value, list):
                raise ResumeStateMappingError(
                    code="RESUME_VALUE_TYPE_MISMATCH",
                    reason=f"Resume 값이 배열이 아닙니다: {path}",
                )
            index = int(index_text)
            if index >= len(value):
                if required:
                    raise ResumeStateMappingError(
                        code="REQUIRED_RESUME_VALUE_MISSING",
                        reason=f"필수 Resume 배열 값이 없습니다: {path}",
                    )
                return None
            value = value[index]

        if required and value is None:
            raise ResumeStateMappingError(
                code="REQUIRED_RESUME_VALUE_MISSING",
                reason=f"필수 Resume 값이 null입니다: {path}",
            )
        return value
