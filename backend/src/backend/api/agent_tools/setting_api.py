"""기본 출금 계좌·계좌 별칭 변경 Agent Tool API (#11~#14).

경로는 모두 `/api/v1/agent-tools` prefix 아래에 있다.

- POST /settings/default-account:prepare (API-DEFAULT-ACCOUNT-PREPARE)
- POST /settings/default-account         (API-DEFAULT-ACCOUNT-EXECUTE)
- POST /settings/account-alias:prepare   (API-ACCOUNT-ALIAS-PREPARE)
- POST /settings/account-alias           (API-ACCOUNT-ALIAS-EXECUTE)

모두 상태 변경 API 라 `Idempotency-Key` 헤더가 필수다(계약 4.2·24.1). 서비스 인증 +
Execution Context + settings:write 스코프를 요구한다.
"""

from fastapi import APIRouter, Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.postgres import get_db
from ...schemas.agent_tools.setting import (
    AccountAliasExecuteData,
    AccountAliasPrepareData,
    AccountAliasPrepareRequest,
    DefaultAccountExecuteData,
    DefaultAccountPrepareData,
    DefaultAccountPrepareRequest,
    ExecuteByConfirmationRequest,
)
from ...schemas.execution_context import ResolvedExecutionContext
from ...schemas.response import CommonResponse
from ...security.execution_context import require_scope
from ...services.agent_tools import setting_service
from ...utils.constants import SCOPE_SETTINGS_WRITE
from .idempotent_runner import run_idempotent

setting_router = APIRouter(tags=["Agent Tools - Setting"])

_IdempotencyHeader = Header(default=None, alias="Idempotency-Key")


@setting_router.post(
    "/settings/default-account:prepare",
    response_model=CommonResponse[DefaultAccountPrepareData],
    response_model_exclude_none=True,
)
async def prepare_default_account_endpoint(
    payload: DefaultAccountPrepareRequest,
    idempotency_key: str | None = _IdempotencyHeader,
    context: ResolvedExecutionContext = Depends(require_scope(SCOPE_SETTINGS_WRITE)),
    session: AsyncSession = Depends(get_db),
):
    """기본 출금 계좌 변경 조건을 평가한다(ready/unchanged/correction)."""
    return await run_idempotent(
        session,
        context,
        "default_account_prepare",
        idempotency_key,
        payload,
        "기본 출금 계좌 변경 내용을 확인했습니다.",
        lambda: setting_service.prepare_default_account(session, context, payload),
    )


@setting_router.post(
    "/settings/default-account",
    response_model=CommonResponse[DefaultAccountExecuteData],
    response_model_exclude_none=True,
)
async def execute_default_account_endpoint(
    payload: ExecuteByConfirmationRequest,
    idempotency_key: str | None = _IdempotencyHeader,
    context: ResolvedExecutionContext = Depends(require_scope(SCOPE_SETTINGS_WRITE)),
    session: AsyncSession = Depends(get_db),
):
    """승인된 Confirmation 으로 기본 출금 계좌를 변경한다."""
    return await run_idempotent(
        session,
        context,
        "default_account_execute",
        idempotency_key,
        payload,
        "기본 출금 계좌를 변경했습니다.",
        lambda: setting_service.execute_default_account(session, context, payload),
    )


@setting_router.post(
    "/settings/account-alias:prepare",
    response_model=CommonResponse[AccountAliasPrepareData],
    response_model_exclude_none=True,
)
async def prepare_account_alias_endpoint(
    payload: AccountAliasPrepareRequest,
    idempotency_key: str | None = _IdempotencyHeader,
    context: ResolvedExecutionContext = Depends(require_scope(SCOPE_SETTINGS_WRITE)),
    session: AsyncSession = Depends(get_db),
):
    """계좌 별칭 변경 조건을 평가한다(ready_for_confirmation/unchanged/correction)."""
    return await run_idempotent(
        session,
        context,
        "account_alias_prepare",
        idempotency_key,
        payload,
        "계좌 별칭 변경 내용을 확인했습니다.",
        lambda: setting_service.prepare_account_alias(session, context, payload),
    )


@setting_router.post(
    "/settings/account-alias",
    response_model=CommonResponse[AccountAliasExecuteData],
    response_model_exclude_none=True,
)
async def execute_account_alias_endpoint(
    payload: ExecuteByConfirmationRequest,
    idempotency_key: str | None = _IdempotencyHeader,
    context: ResolvedExecutionContext = Depends(require_scope(SCOPE_SETTINGS_WRITE)),
    session: AsyncSession = Depends(get_db),
):
    """승인된 Confirmation 에 고정된 별칭을 반영한다."""
    return await run_idempotent(
        session,
        context,
        "account_alias_execute",
        idempotency_key,
        payload,
        "계좌 별칭을 변경했습니다.",
        lambda: setting_service.execute_account_alias(session, context, payload),
    )
