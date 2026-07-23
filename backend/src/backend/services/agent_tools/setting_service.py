"""기본 출금 계좌·계좌 별칭 변경 로직 (#11~#14, 계약 19~22장).

흐름: Prepare(조건 평가 + Confirmation 고정) → 사용자 승인 → Execute(재검증 + 반영).
설정 변경은 추가 인증을 요구하지 않는다(계약 19.3).

업무 판정은 예외가 아니라 `outcome` 으로 반환한다(D2'). 소유권·서비스 인증 실패 같은
요청 오류만 AgentToolError 로 던진다.

별칭 정본: 계정계(mock-financial-service)에도 accounts.alias 컬럼이 있으나 이를 변경할
write endpoint 가 없어 로컬 `accounts.alias` 를 정본으로 사용한다(D4).
TODO(계정계): 별칭을 계정계에서도 관리해야 하면 alias 수정 endpoint 를 제공해 달라.
그전까지 계정계의 alias 값은 Backend 가 사용하지 않는다.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ...core.agent_exceptions import AgentToolError
from ...models.account import Account
from ...models.confirmation import ConfirmationOperation
from ...models.financial_audit_log import (
    EVENT_CONFIRMATION_CREATED,
    EVENT_SETTING_CHANGE_COMPLETED,
)
from ...repository.account_repository import (
    alias_exists_for_user,
    get_default_account,
    get_owned_account,
    set_account_alias,
    set_default_account,
)
from ...schemas.agent_tools.common import AccountDisplayRef, CorrectionView
from ...schemas.agent_tools.setting import (
    AccountAliasConfirmationView,
    AccountAliasExecuteData,
    AccountAliasPrepareData,
    AccountAliasPrepareRequest,
    AliasAccountRef,
    DefaultAccountConfirmationView,
    DefaultAccountExecuteData,
    DefaultAccountPrepareData,
    DefaultAccountPrepareRequest,
    ExecuteByConfirmationRequest,
    SettingOutcome,
    SettingReason,
)
from ...schemas.execution_context import ResolvedExecutionContext
from ...utils.masking import mask_account_number
from ...utils.parsing import parse_uuid
from .. import confirmation_service, financial_audit_service
from .policy_constants import (
    ALIAS_MAX_LENGTH,
    ALIAS_MIN_LENGTH,
    is_alias_forbidden,
    normalize_alias,
)

_CONTRACT_DEFAULT_PREPARE = "API-DEFAULT-ACCOUNT-PREPARE"
_CONTRACT_DEFAULT_EXECUTE = "API-DEFAULT-ACCOUNT-EXECUTE"
_CONTRACT_ALIAS_PREPARE = "API-ACCOUNT-ALIAS-PREPARE"
_CONTRACT_ALIAS_EXECUTE = "API-ACCOUNT-ALIAS-EXECUTE"

_OP_DEFAULT_PREPARE = "default_account_prepare"
_OP_DEFAULT_EXECUTE = "default_account_execute"
_OP_ALIAS_PREPARE = "account_alias_prepare"
_OP_ALIAS_EXECUTE = "account_alias_execute"


def _invalid_account_id() -> AgentToolError:
    return AgentToolError.invalid_request("account_id 형식이 올바르지 않습니다.")


async def _load_owned_account(session: AsyncSession, context: ResolvedExecutionContext, account_id: str) -> Account:
    """대상 계좌 소유권 검증. 소유가 아니면 존재 여부를 노출하지 않고 거부한다."""
    account = await get_owned_account(session, context.user_id, parse_uuid(account_id, _invalid_account_id))
    if account is None:
        raise AgentToolError.account_access_denied()
    return account


def _account_ref(account: Account) -> AccountDisplayRef:
    return AccountDisplayRef(
        account_id=str(account.id),
        bank_name=account.bank_name,
        account_alias=account.alias,
        masked_account_number=mask_account_number(account.account_number),
    )


def _alias_account_ref(account: Account) -> AliasAccountRef:
    return AliasAccountRef(
        account_id=str(account.id),
        bank_name=account.bank_name,
        masked_account_number=mask_account_number(account.account_number),
    )


def _account_correction(title: str) -> CorrectionView:
    return CorrectionView(title=title, allowed_change_targets=["account"])


def _alias_correction(title: str) -> CorrectionView:
    return CorrectionView(title=title, allowed_change_targets=["alias"])


# ── #11 기본 출금 계좌 변경 Prepare ──────────────────────────────────────────


async def prepare_default_account(
    session: AsyncSession,
    context: ResolvedExecutionContext,
    req: DefaultAccountPrepareRequest,
) -> DefaultAccountPrepareData:
    """기본 출금 계좌 변경 조건을 평가하고 Confirmation 을 고정한다."""
    account = await _load_owned_account(session, context, req.account_id)

    # 활성·출금 가능해야 기본 출금 계좌가 될 수 있다(계약 19.6).
    if not account.active:
        return DefaultAccountPrepareData(
            outcome=SettingOutcome.CORRECTION_REQUIRED,
            reason=SettingReason.ACCOUNT_NOT_ELIGIBLE,
            correction_view=_account_correction("다른 계좌를 선택해 주세요."),
        )

    # 이미 기본계좌면 오류가 아니라 unchanged (Confirmation 미생성, 계약 19.4).
    if account.is_default:
        return DefaultAccountPrepareData(outcome=SettingOutcome.UNCHANGED, account_id=str(account.id))

    current_default = await get_default_account(session, context.user_id)
    confirmation = await confirmation_service.create_pending(
        session,
        context,
        ConfirmationOperation.DEFAULT_ACCOUNT_CHANGE,
        fixed_data={"account_id": str(account.id)},
    )
    await financial_audit_service.record(
        session,
        context,
        event_type=EVENT_CONFIRMATION_CREATED,
        operation=_OP_DEFAULT_PREPARE,
        outcome=SettingOutcome.READY_FOR_CONFIRMATION,
        contract_id=_CONTRACT_DEFAULT_PREPARE,
        confirmation_id=confirmation.id,
    )
    return DefaultAccountPrepareData(
        outcome=SettingOutcome.READY_FOR_CONFIRMATION,
        confirmation_id=str(confirmation.id),
        confirmation_view=DefaultAccountConfirmationView(
            current_default_account=(_account_ref(current_default) if current_default else None),
            new_default_account=_account_ref(account),
            expires_at=confirmation.expires_at,
        ),
    )


# ── #12 기본 출금 계좌 변경 Execute ──────────────────────────────────────────


async def execute_default_account(
    session: AsyncSession,
    context: ResolvedExecutionContext,
    req: ExecuteByConfirmationRequest,
) -> DefaultAccountExecuteData:
    """승인된 Confirmation 으로 기본 출금 계좌를 반영한다(직전 재검증 포함)."""
    confirmation = await confirmation_service.load_for_execute(
        session,
        context,
        req.confirmation_id,
        ConfirmationOperation.DEFAULT_ACCOUNT_CHANGE,
    )
    account_id = str(confirmation.fixed_data["account_id"])
    account = await get_owned_account(session, context.user_id, UUID(account_id))

    # 승인 이후 계좌가 사라졌거나 비활성화된 경우 기존 Confirmation 을 무효화한다.
    if account is None or not account.active:
        await confirmation_service.invalidate(session, confirmation)
        return DefaultAccountExecuteData(
            outcome=SettingOutcome.CORRECTION_REQUIRED,
            reason=SettingReason.ACCOUNT_NOT_ELIGIBLE,
            correction_view=_account_correction("다른 계좌를 선택해 주세요."),
        )

    await set_default_account(session, context.user_id, account)
    won = await confirmation_service.mark_executed(session, confirmation)
    completed_at = datetime.now(timezone.utc)
    if won:  # C2: 동시 실행에서 진 요청은 중복 Audit 을 남기지 않는다.
        await financial_audit_service.record(
            session,
            context,
            event_type=EVENT_SETTING_CHANGE_COMPLETED,
            operation=_OP_DEFAULT_EXECUTE,
            outcome=SettingOutcome.COMPLETED,
            contract_id=_CONTRACT_DEFAULT_EXECUTE,
            confirmation_id=confirmation.id,
        )
    return DefaultAccountExecuteData(
        outcome=SettingOutcome.COMPLETED,
        account_id=str(account.id),
        completed_at=completed_at,
    )


# ── #13 계좌 별칭 변경 Prepare ───────────────────────────────────────────────


async def _alias_policy_violation(
    session: AsyncSession,
    context: ResolvedExecutionContext,
    account: Account,
    alias: str,
) -> str | None:
    """별칭 정책 위반 사유를 반환한다(문제 없으면 None)."""
    if not (ALIAS_MIN_LENGTH <= len(alias) <= ALIAS_MAX_LENGTH):
        return "length"
    if is_alias_forbidden(alias):
        return "forbidden"
    if await alias_exists_for_user(session, context.user_id, alias, account.id):
        return "duplicated"
    return None


async def prepare_account_alias(
    session: AsyncSession,
    context: ResolvedExecutionContext,
    req: AccountAliasPrepareRequest,
) -> AccountAliasPrepareData:
    """계좌 별칭 변경 조건을 평가하고 Confirmation 을 고정한다."""
    account = await _load_owned_account(session, context, req.account_id)
    alias = normalize_alias(req.alias)

    violation = await _alias_policy_violation(session, context, account, alias)
    if violation is not None:
        return AccountAliasPrepareData(
            outcome=SettingOutcome.CORRECTION_REQUIRED,
            reason=SettingReason.ALIAS_NOT_ALLOWED,
            correction_view=_alias_correction("다른 별칭을 입력해 주세요."),
        )

    # 현재 별칭과 정규화 결과가 같으면 unchanged (Confirmation 미생성, 계약 21.5).
    if account.alias is not None and normalize_alias(account.alias) == alias:
        return AccountAliasPrepareData(
            outcome=SettingOutcome.UNCHANGED,
            account_id=str(account.id),
            alias=alias,
        )

    confirmation = await confirmation_service.create_pending(
        session,
        context,
        ConfirmationOperation.ACCOUNT_ALIAS_CHANGE,
        fixed_data={"account_id": str(account.id), "alias": alias},
    )
    await financial_audit_service.record(
        session,
        context,
        event_type=EVENT_CONFIRMATION_CREATED,
        operation=_OP_ALIAS_PREPARE,
        outcome=SettingOutcome.READY_FOR_CONFIRMATION,
        contract_id=_CONTRACT_ALIAS_PREPARE,
        confirmation_id=confirmation.id,
    )
    return AccountAliasPrepareData(
        outcome=SettingOutcome.READY_FOR_CONFIRMATION,
        confirmation_id=str(confirmation.id),
        confirmation_view=AccountAliasConfirmationView(
            account=_alias_account_ref(account),
            alias=alias,
            expires_at=confirmation.expires_at,
        ),
    )


# ── #14 계좌 별칭 변경 Execute ───────────────────────────────────────────────


async def execute_account_alias(
    session: AsyncSession,
    context: ResolvedExecutionContext,
    req: ExecuteByConfirmationRequest,
) -> AccountAliasExecuteData:
    """승인된 Confirmation 에 고정된 별칭을 반영한다(직전 재검증 포함)."""
    confirmation = await confirmation_service.load_for_execute(
        session,
        context,
        req.confirmation_id,
        ConfirmationOperation.ACCOUNT_ALIAS_CHANGE,
    )
    account_id = str(confirmation.fixed_data["account_id"])
    alias = str(confirmation.fixed_data["alias"])
    account = await get_owned_account(session, context.user_id, UUID(account_id))

    if account is None or not account.active:
        await confirmation_service.invalidate(session, confirmation)
        return AccountAliasExecuteData(
            outcome=SettingOutcome.CORRECTION_REQUIRED,
            reason=SettingReason.ACCOUNT_NOT_ELIGIBLE,
            correction_view=_account_correction("다른 계좌를 선택해 주세요."),
        )

    # 승인 이후 별칭 정책이 바뀌었거나 다른 계좌가 같은 별칭을 선점했을 수 있다.
    violation = await _alias_policy_violation(session, context, account, alias)
    if violation is not None:
        await confirmation_service.invalidate(session, confirmation)
        return AccountAliasExecuteData(
            outcome=SettingOutcome.CORRECTION_REQUIRED,
            reason=SettingReason.ALIAS_NOT_ALLOWED,
            correction_view=_alias_correction("다른 별칭을 입력해 주세요."),
        )

    await set_account_alias(session, account, alias)
    won = await confirmation_service.mark_executed(session, confirmation)
    completed_at = datetime.now(timezone.utc)
    if won:  # C2: 동시 실행에서 진 요청은 중복 Audit 을 남기지 않는다.
        await financial_audit_service.record(
            session,
            context,
            event_type=EVENT_SETTING_CHANGE_COMPLETED,
            operation=_OP_ALIAS_EXECUTE,
            outcome=SettingOutcome.COMPLETED,
            contract_id=_CONTRACT_ALIAS_EXECUTE,
            confirmation_id=confirmation.id,
        )
    return AccountAliasExecuteData(
        outcome=SettingOutcome.COMPLETED,
        account_id=str(account.id),
        alias=alias,
        completed_at=completed_at,
    )
