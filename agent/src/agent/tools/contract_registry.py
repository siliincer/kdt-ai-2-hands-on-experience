"""계약 ID와 Tool ID의 중복 구현을 차단하는 공통 Registry."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any

from agent.workflow_contracts import WorkflowContractStore


@dataclass(frozen=True, slots=True)
class ContractToolCall:
    """Workflow Runtime이 Tool에 전달하는 업무 인자와 요청 Context."""

    execution_context_id: str
    request_id: str
    arguments: Mapping[str, Any]
    idempotency_key: str | None = None


class ContractToolInputError(ValueError):
    """Workflow State가 Agent Tool 요청 계약과 일치하지 않는 경우."""

    def __init__(self, *, contract_id: str, reason: str):
        super().__init__(f"{contract_id} 요청 계약 오류: {reason}")
        self.contract_id = contract_id
        self.reason = reason


ToolHandler = Callable[[ContractToolCall], Awaitable[Mapping[str, Any]]]


@dataclass(frozen=True, slots=True)
class ContractToolBinding:
    contract_id: str
    tool_id: str
    handler: ToolHandler


class ContractToolRegistry:
    """하나의 API 계약과 Tool 이름에 하나의 구현만 연결한다."""

    def __init__(self, contract_store: WorkflowContractStore) -> None:
        self._contract_store = contract_store
        self._by_contract: dict[str, ContractToolBinding] = {}
        self._by_tool: dict[str, ContractToolBinding] = {}

    def register(
        self,
        *,
        contract_id: str,
        tool_id: str,
        handler: ToolHandler,
    ) -> ContractToolBinding:
        contract = self._contract_store.get_contract(contract_id)
        if contract["contract_type"] != "agent_tool_api":
            raise ValueError(f"Agent Tool API 계약이 아닙니다: {contract_id}")
        if contract_id in self._by_contract:
            raise ValueError(f"contract_id 구현이 중복입니다: {contract_id}")
        if tool_id in self._by_tool:
            raise ValueError(f"tool_id 구현이 중복입니다: {tool_id}")

        binding = ContractToolBinding(
            contract_id=contract_id,
            tool_id=tool_id,
            handler=handler,
        )
        self._by_contract[contract_id] = binding
        self._by_tool[tool_id] = binding
        return binding

    def get_by_contract(self, contract_id: str) -> ContractToolBinding:
        try:
            return self._by_contract[contract_id]
        except KeyError as error:
            raise KeyError(f"등록되지 않은 Tool 계약입니다: {contract_id}") from error

    def get_by_tool(self, tool_id: str) -> ContractToolBinding:
        try:
            return self._by_tool[tool_id]
        except KeyError as error:
            raise KeyError(f"등록되지 않은 Tool입니다: {tool_id}") from error

    async def invoke_by_tool(
        self,
        tool_id: str,
        call: ContractToolCall,
    ) -> Mapping[str, Any]:
        """등록된 Tool을 공통 호출 Context로 실행한다."""

        return await self.get_by_tool(tool_id).handler(call)

    def missing_contracts_for_workflow(self, workflow_id: str) -> set[str]:
        required = self._contract_store.required_contract_ids(
            workflow_id,
            contract_type="agent_tool_api",
        )
        return required - self._by_contract.keys()
