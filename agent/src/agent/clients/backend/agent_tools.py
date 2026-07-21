"""계약 타입을 사용하는 Agent -> Backend Tool API Adapter."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from agent.clients.backend.client import AgentToolProtocolError, BackendToolClient
from agent.contracts.agent_tools import (
    AccountAliasExecuteResult,
    AccountAliasPrepareRequest,
    AccountAliasPrepareResult,
    AccountListRequest,
    AccountListResult,
    AuthContextCreateRequest,
    AuthContextCreateResult,
    BalanceQueryRequest,
    BalanceQueryResult,
    ConfirmationExecuteRequest,
    DefaultAccountExecuteResult,
    DefaultAccountPrepareRequest,
    DefaultAccountPrepareResult,
    ExternalTransferExecuteResult,
    ExternalTransferPrepareRequest,
    ExternalTransferPrepareResult,
    InternalTransferExecuteResult,
    InternalTransferPrepareRequest,
    InternalTransferPrepareResult,
    RecipientResolveRequest,
    RecipientResolveResult,
    TransactionQueryRequest,
    TransactionQueryResult,
    TransactionSummaryRequest,
    TransactionSummaryResult,
    TransferExecuteRequest,
)

ResponseModel = TypeVar("ResponseModel", bound=BaseModel)


@dataclass(frozen=True, slots=True)
class BackendRequestContext:
    """단일 Agent Tool HTTP 요청의 추적 Context."""

    execution_context_id: str
    request_id: str


@dataclass(frozen=True, slots=True)
class BackendMutationRequestContext:
    """멱등성 키가 필수인 상태변경 Tool 요청 Context."""

    execution_context_id: str
    request_id: str
    idempotency_key: str

    def __post_init__(self) -> None:
        if not self.idempotency_key:
            raise ValueError("상태변경 Tool에는 idempotency_key가 필요합니다.")


class BackendAgentTools:
    """Workflow가 공유하는 타입 기반 Backend Agent Tool 모음."""

    def __init__(self, client: BackendToolClient) -> None:
        self._client = client

    async def fetch_accounts(
        self,
        request: AccountListRequest,
        *,
        context: BackendRequestContext,
    ) -> AccountListResult:
        params = request.model_dump(mode="json", exclude_none=True)
        if not request.exclude_account_ids:
            params.pop("exclude_account_ids")
        data = await self._client.request(
            "GET",
            "/api/v1/agent-tools/accounts",
            execution_context_id=context.execution_context_id,
            request_id=context.request_id,
            params=params,
        )
        return self._validate_response(AccountListResult, data, context=context)

    async def query_balances(
        self,
        request: BalanceQueryRequest,
        *,
        context: BackendRequestContext,
    ) -> BalanceQueryResult:
        data = await self._client.request(
            "POST",
            "/api/v1/agent-tools/accounts/balances:query",
            execution_context_id=context.execution_context_id,
            request_id=context.request_id,
            body=request.model_dump(mode="json"),
        )
        return self._validate_response(BalanceQueryResult, data, context=context)

    async def query_transactions(
        self,
        request: TransactionQueryRequest,
        *,
        context: BackendRequestContext,
    ) -> TransactionQueryResult:
        data = await self._client.request(
            "POST",
            "/api/v1/agent-tools/transactions:query",
            execution_context_id=context.execution_context_id,
            request_id=context.request_id,
            body=request.model_dump(mode="json"),
        )
        return self._validate_response(TransactionQueryResult, data, context=context)

    async def query_transaction_summary(
        self,
        request: TransactionSummaryRequest,
        *,
        context: BackendRequestContext,
    ) -> TransactionSummaryResult:
        data = await self._client.request(
            "POST",
            "/api/v1/agent-tools/transactions:summary",
            execution_context_id=context.execution_context_id,
            request_id=context.request_id,
            body=request.model_dump(mode="json"),
        )
        return self._validate_response(
            TransactionSummaryResult,
            data,
            context=context,
        )

    async def resolve_recipient(
        self,
        request: RecipientResolveRequest,
        *,
        context: BackendRequestContext,
    ) -> RecipientResolveResult:
        data = await self._client.request(
            "POST",
            "/api/v1/agent-tools/recipients:resolve",
            execution_context_id=context.execution_context_id,
            request_id=context.request_id,
            body=request.model_dump(mode="json"),
        )
        return self._validate_response(RecipientResolveResult, data, context=context)

    async def prepare_external_transfer(
        self,
        request: ExternalTransferPrepareRequest,
        *,
        context: BackendMutationRequestContext,
    ) -> ExternalTransferPrepareResult:
        data = await self._mutation_request(
            "/api/v1/agent-tools/transfers/external:prepare",
            request,
            context=context,
        )
        return self._validate_response(
            ExternalTransferPrepareResult,
            data,
            context=context,
        )

    async def create_auth_context(
        self,
        request: AuthContextCreateRequest,
        *,
        context: BackendMutationRequestContext,
    ) -> AuthContextCreateResult:
        data = await self._mutation_request(
            "/api/v1/agent-tools/auth-contexts",
            request,
            context=context,
        )
        return self._validate_response(AuthContextCreateResult, data, context=context)

    async def execute_external_transfer(
        self,
        request: TransferExecuteRequest,
        *,
        context: BackendMutationRequestContext,
    ) -> ExternalTransferExecuteResult:
        data = await self._mutation_request(
            "/api/v1/agent-tools/transfers/external",
            request,
            context=context,
        )
        return self._validate_response(
            ExternalTransferExecuteResult,
            data,
            context=context,
        )

    async def prepare_internal_transfer(
        self,
        request: InternalTransferPrepareRequest,
        *,
        context: BackendMutationRequestContext,
    ) -> InternalTransferPrepareResult:
        data = await self._mutation_request(
            "/api/v1/agent-tools/transfers/internal:prepare",
            request,
            context=context,
        )
        return self._validate_response(
            InternalTransferPrepareResult,
            data,
            context=context,
        )

    async def execute_internal_transfer(
        self,
        request: TransferExecuteRequest,
        *,
        context: BackendMutationRequestContext,
    ) -> InternalTransferExecuteResult:
        data = await self._mutation_request(
            "/api/v1/agent-tools/transfers/internal",
            request,
            context=context,
        )
        return self._validate_response(
            InternalTransferExecuteResult,
            data,
            context=context,
        )

    async def prepare_default_account_change(
        self,
        request: DefaultAccountPrepareRequest,
        *,
        context: BackendMutationRequestContext,
    ) -> DefaultAccountPrepareResult:
        data = await self._mutation_request(
            "/api/v1/agent-tools/settings/default-account:prepare",
            request,
            context=context,
        )
        return self._validate_response(
            DefaultAccountPrepareResult,
            data,
            context=context,
        )

    async def execute_default_account_change(
        self,
        request: ConfirmationExecuteRequest,
        *,
        context: BackendMutationRequestContext,
    ) -> DefaultAccountExecuteResult:
        data = await self._mutation_request(
            "/api/v1/agent-tools/settings/default-account",
            request,
            context=context,
        )
        return self._validate_response(
            DefaultAccountExecuteResult,
            data,
            context=context,
        )

    async def prepare_account_alias_change(
        self,
        request: AccountAliasPrepareRequest,
        *,
        context: BackendMutationRequestContext,
    ) -> AccountAliasPrepareResult:
        data = await self._mutation_request(
            "/api/v1/agent-tools/settings/account-alias:prepare",
            request,
            context=context,
        )
        return self._validate_response(
            AccountAliasPrepareResult,
            data,
            context=context,
        )

    async def execute_account_alias_change(
        self,
        request: ConfirmationExecuteRequest,
        *,
        context: BackendMutationRequestContext,
    ) -> AccountAliasExecuteResult:
        data = await self._mutation_request(
            "/api/v1/agent-tools/settings/account-alias",
            request,
            context=context,
        )
        return self._validate_response(
            AccountAliasExecuteResult,
            data,
            context=context,
        )

    async def _mutation_request(
        self,
        path: str,
        request: BaseModel,
        *,
        context: BackendMutationRequestContext,
    ) -> dict[str, object]:
        return await self._client.request(
            "POST",
            path,
            execution_context_id=context.execution_context_id,
            request_id=context.request_id,
            idempotency_key=context.idempotency_key,
            body=request.model_dump(mode="json", exclude_none=True),
        )

    @staticmethod
    def _validate_response(
        model: type[ResponseModel],
        data: dict[str, object],
        *,
        context: BackendRequestContext | BackendMutationRequestContext,
    ) -> ResponseModel:
        try:
            return model.model_validate(data)
        except ValidationError as error:
            raise AgentToolProtocolError(
                request_id=context.request_id,
                reason=f"{model.__name__} 응답 Schema 불일치",
            ) from error
