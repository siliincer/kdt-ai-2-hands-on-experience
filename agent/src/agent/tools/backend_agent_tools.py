"""타입 기반 Backend Agent Tool을 계약 Registry에 연결한다."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from agent.clients.backend import (
    BackendAgentTools,
    BackendMutationRequestContext,
    BackendRequestContext,
)
from agent.contracts.agent_tools import (
    AccountAliasPrepareRequest,
    AccountListRequest,
    AuthContextCreateRequest,
    BalanceQueryRequest,
    ConfirmationExecuteRequest,
    DefaultAccountPrepareRequest,
    ExternalTransferPrepareRequest,
    InternalTransferPrepareRequest,
    RecipientResolveRequest,
    TransactionQueryRequest,
    TransactionSummaryRequest,
    TransferExecuteRequest,
)
from agent.tools.contract_registry import (
    ContractToolCall,
    ContractToolInputError,
    ContractToolRegistry,
)

RequestModel = TypeVar("RequestModel", bound=BaseModel)


def _request_context(call: ContractToolCall) -> BackendRequestContext:
    return BackendRequestContext(
        execution_context_id=call.execution_context_id,
        request_id=call.request_id,
    )


def _mutation_context(
    call: ContractToolCall,
    *,
    contract_id: str,
) -> BackendMutationRequestContext:
    if not call.idempotency_key:
        raise ContractToolInputError(
            contract_id=contract_id,
            reason="상태변경 요청에는 Idempotency-Key가 필요합니다.",
        )
    return BackendMutationRequestContext(
        execution_context_id=call.execution_context_id,
        request_id=call.request_id,
        idempotency_key=call.idempotency_key,
    )


def _validate_arguments(
    model: type[RequestModel],
    call: ContractToolCall,
    *,
    contract_id: str,
) -> RequestModel:
    try:
        return model.model_validate(call.arguments)
    except ValidationError as error:
        raise ContractToolInputError(
            contract_id=contract_id,
            reason="Workflow State와 요청 Schema 불일치",
        ) from error


def register_backend_agent_tools(
    registry: ContractToolRegistry,
    tools: BackendAgentTools,
) -> None:
    """현재 명세의 Agent Tool API 14개를 하나의 Registry에 등록한다."""

    register_read_backend_agent_tools(registry, tools)
    register_transfer_backend_agent_tools(registry, tools)
    register_setting_backend_agent_tools(registry, tools)


def register_read_backend_agent_tools(
    registry: ContractToolRegistry,
    tools: BackendAgentTools,
) -> None:
    """조회 계열 5개 API 계약을 공통 구현에 한 번만 등록한다."""

    async def fetch_accounts(call: ContractToolCall) -> Mapping[str, Any]:
        contract_id = "API-ACCOUNT-LIST"
        request = _validate_arguments(
            AccountListRequest,
            call,
            contract_id=contract_id,
        )
        result = await tools.fetch_accounts(request, context=_request_context(call))
        return result.model_dump(mode="json")

    async def query_balances(call: ContractToolCall) -> Mapping[str, Any]:
        contract_id = "API-BALANCE-QUERY"
        request = _validate_arguments(
            BalanceQueryRequest,
            call,
            contract_id=contract_id,
        )
        result = await tools.query_balances(request, context=_request_context(call))
        return result.model_dump(mode="json")

    async def query_transactions(call: ContractToolCall) -> Mapping[str, Any]:
        contract_id = "API-TRANSACTION-QUERY"
        request = _validate_arguments(
            TransactionQueryRequest,
            call,
            contract_id=contract_id,
        )
        result = await tools.query_transactions(request, context=_request_context(call))
        return result.model_dump(mode="json")

    async def query_transaction_summary(
        call: ContractToolCall,
    ) -> Mapping[str, Any]:
        contract_id = "API-TRANSACTION-SUMMARY"
        request = _validate_arguments(
            TransactionSummaryRequest,
            call,
            contract_id=contract_id,
        )
        result = await tools.query_transaction_summary(
            request,
            context=_request_context(call),
        )
        return result.model_dump(mode="json")

    async def resolve_recipient_hint(
        call: ContractToolCall,
    ) -> Mapping[str, Any]:
        contract_id = "API-RECIPIENT-RESOLVE"
        request = _validate_arguments(
            RecipientResolveRequest,
            call,
            contract_id=contract_id,
        )
        result = await tools.resolve_recipient(
            request,
            context=_request_context(call),
        )
        return result.model_dump(mode="json")

    registry.register(
        contract_id="API-ACCOUNT-LIST",
        tool_id="fetch_accounts",
        handler=fetch_accounts,
    )
    registry.register(
        contract_id="API-BALANCE-QUERY",
        tool_id="query_balances",
        handler=query_balances,
    )
    registry.register(
        contract_id="API-TRANSACTION-QUERY",
        tool_id="query_transactions",
        handler=query_transactions,
    )
    registry.register(
        contract_id="API-TRANSACTION-SUMMARY",
        tool_id="query_transaction_summary",
        handler=query_transaction_summary,
    )
    registry.register(
        contract_id="API-RECIPIENT-RESOLVE",
        tool_id="resolve_recipient_hint",
        handler=resolve_recipient_hint,
    )


def register_transfer_backend_agent_tools(
    registry: ContractToolRegistry,
    tools: BackendAgentTools,
) -> None:
    """송금·인증 5개 상태변경 API를 공통 구현에 등록한다."""

    async def prepare_external_transfer(
        call: ContractToolCall,
    ) -> Mapping[str, Any]:
        contract_id = "API-EXTERNAL-TRANSFER-PREPARE"
        request = _validate_arguments(
            ExternalTransferPrepareRequest,
            call,
            contract_id=contract_id,
        )
        result = await tools.prepare_external_transfer(
            request,
            context=_mutation_context(call, contract_id=contract_id),
        )
        return result.model_dump(mode="json")

    async def create_auth_context(call: ContractToolCall) -> Mapping[str, Any]:
        contract_id = "API-AUTH-CONTEXT-CREATE"
        request = _validate_arguments(
            AuthContextCreateRequest,
            call,
            contract_id=contract_id,
        )
        result = await tools.create_auth_context(
            request,
            context=_mutation_context(call, contract_id=contract_id),
        )
        return result.model_dump(mode="json")

    async def execute_external_transfer(
        call: ContractToolCall,
    ) -> Mapping[str, Any]:
        contract_id = "API-EXTERNAL-TRANSFER-EXECUTE"
        request = _validate_arguments(
            TransferExecuteRequest,
            call,
            contract_id=contract_id,
        )
        result = await tools.execute_external_transfer(
            request,
            context=_mutation_context(call, contract_id=contract_id),
        )
        return result.model_dump(mode="json")

    async def prepare_internal_transfer(
        call: ContractToolCall,
    ) -> Mapping[str, Any]:
        contract_id = "API-INTERNAL-TRANSFER-PREPARE"
        request = _validate_arguments(
            InternalTransferPrepareRequest,
            call,
            contract_id=contract_id,
        )
        result = await tools.prepare_internal_transfer(
            request,
            context=_mutation_context(call, contract_id=contract_id),
        )
        return result.model_dump(mode="json")

    async def execute_internal_transfer(
        call: ContractToolCall,
    ) -> Mapping[str, Any]:
        contract_id = "API-INTERNAL-TRANSFER-EXECUTE"
        request = _validate_arguments(
            TransferExecuteRequest,
            call,
            contract_id=contract_id,
        )
        result = await tools.execute_internal_transfer(
            request,
            context=_mutation_context(call, contract_id=contract_id),
        )
        return result.model_dump(mode="json")

    registry.register(
        contract_id="API-EXTERNAL-TRANSFER-PREPARE",
        tool_id="prepare_external_transfer",
        handler=prepare_external_transfer,
    )
    registry.register(
        contract_id="API-AUTH-CONTEXT-CREATE",
        tool_id="create_auth_context",
        handler=create_auth_context,
    )
    registry.register(
        contract_id="API-EXTERNAL-TRANSFER-EXECUTE",
        tool_id="execute_external_transfer",
        handler=execute_external_transfer,
    )
    registry.register(
        contract_id="API-INTERNAL-TRANSFER-PREPARE",
        tool_id="prepare_internal_transfer",
        handler=prepare_internal_transfer,
    )
    registry.register(
        contract_id="API-INTERNAL-TRANSFER-EXECUTE",
        tool_id="execute_internal_transfer",
        handler=execute_internal_transfer,
    )


def register_setting_backend_agent_tools(
    registry: ContractToolRegistry,
    tools: BackendAgentTools,
) -> None:
    """설정 변경 4개 상태변경 API를 공통 구현에 등록한다."""

    async def prepare_default_account_change(
        call: ContractToolCall,
    ) -> Mapping[str, Any]:
        contract_id = "API-DEFAULT-ACCOUNT-PREPARE"
        request = _validate_arguments(
            DefaultAccountPrepareRequest,
            call,
            contract_id=contract_id,
        )
        result = await tools.prepare_default_account_change(
            request,
            context=_mutation_context(call, contract_id=contract_id),
        )
        return result.model_dump(mode="json")

    async def execute_default_account_change(
        call: ContractToolCall,
    ) -> Mapping[str, Any]:
        contract_id = "API-DEFAULT-ACCOUNT-EXECUTE"
        request = _validate_arguments(
            ConfirmationExecuteRequest,
            call,
            contract_id=contract_id,
        )
        result = await tools.execute_default_account_change(
            request,
            context=_mutation_context(call, contract_id=contract_id),
        )
        return result.model_dump(mode="json")

    async def prepare_account_alias_change(
        call: ContractToolCall,
    ) -> Mapping[str, Any]:
        contract_id = "API-ACCOUNT-ALIAS-PREPARE"
        request = _validate_arguments(
            AccountAliasPrepareRequest,
            call,
            contract_id=contract_id,
        )
        result = await tools.prepare_account_alias_change(
            request,
            context=_mutation_context(call, contract_id=contract_id),
        )
        return result.model_dump(mode="json")

    async def execute_account_alias_change(
        call: ContractToolCall,
    ) -> Mapping[str, Any]:
        contract_id = "API-ACCOUNT-ALIAS-EXECUTE"
        request = _validate_arguments(
            ConfirmationExecuteRequest,
            call,
            contract_id=contract_id,
        )
        result = await tools.execute_account_alias_change(
            request,
            context=_mutation_context(call, contract_id=contract_id),
        )
        return result.model_dump(mode="json")

    registry.register(
        contract_id="API-DEFAULT-ACCOUNT-PREPARE",
        tool_id="prepare_default_account_change",
        handler=prepare_default_account_change,
    )
    registry.register(
        contract_id="API-DEFAULT-ACCOUNT-EXECUTE",
        tool_id="execute_default_account_change",
        handler=execute_default_account_change,
    )
    registry.register(
        contract_id="API-ACCOUNT-ALIAS-PREPARE",
        tool_id="prepare_account_alias_change",
        handler=prepare_account_alias_change,
    )
    registry.register(
        contract_id="API-ACCOUNT-ALIAS-EXECUTE",
        tool_id="execute_account_alias_change",
        handler=execute_account_alias_change,
    )
