"""본인 계좌 간 이체 로직 (#9·#10, 계약 17~18장).

흐름: Prepare(조건 평가 + Confirmation 고정) → 사용자 승인 → 추가 인증 → Execute.
본인 이체도 추가 인증이 **필수**다(계약 17.3).

업무 판정은 예외가 아니라 `outcome` 으로 반환한다(D2'). 계정계 장애처럼 판정 자체를
완료하지 못한 경우만 `success=false`(technical_error)로 반환한다(계약 17.6).

원장 변경은 계정계(`POST /transfers`)가 정본이라 Backend DB 와 하나의 물리 트랜잭션으로
묶을 수 없다. 대신 계정계에 **confirmation_id 기반 결정적 Idempotency-Key** 를 보내
재호출해도 이체가 중복되지 않게 한다(계약 18.7·24.5의 safe replay).
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ...core.agent_exceptions import AgentToolError
from ...core.load_environment_var import settings
from ...models.account import Account
from ...models.confirmation import Confirmation, ConfirmationOperation
from ...models.financial_audit_log import (
    EVENT_CONFIRMATION_CREATED,
    EVENT_FINANCIAL_EXECUTION_COMPLETED,
)
from ...repository.account_repository import get_owned_account
from ...repository.confirmation_repository import get_executed_transfers_since
from ...schemas.agent_tools.transfer import (
    CorrectionView,
    InternalTransferConfirmationView,
    InternalTransferPrepareData,
    InternalTransferPrepareRequest,
    TransferAccountRef,
    TransferExecuteData,
    TransferExecuteRequest,
    TransferOutcome,
    TransferReason,
)
from ...schemas.execution_context import ResolvedExecutionContext
from ...utils.masking import mask_account_number
from ...utils.timezone import resolve_tz
from .. import auth_context_service, confirmation_service, financial_audit_service
from ..financial import FinancialServiceError, get_financial_client
from .balance_reader import read_available_balance
from .bank_resolver import resolve_owned_account_bank
from .policy_constants import (
    MAX_DAILY_TRANSFER_KRW,
    MAX_SINGLE_TRANSFER_KRW,
    TRANSFER_FEE_KRW,
)

_CONTRACT_INTERNAL_PREPARE = "API-INTERNAL-TRANSFER-PREPARE"
_CONTRACT_INTERNAL_EXECUTE = "API-INTERNAL-TRANSFER-EXECUTE"
_OP_INTERNAL_PREPARE = "internal_transfer_prepare"
_OP_INTERNAL_EXECUTE = "internal_transfer_execute"


def _use_http() -> bool:
    return settings.FINANCIAL_CLIENT.strip().lower() == "http"


def _correction(
    reason: str, targets: list[str], title: str
) -> tuple[str, CorrectionView]:
    return reason, CorrectionView(title=title, allowed_change_targets=targets)


def _account_ref(account: Account) -> TransferAccountRef:
    return TransferAccountRef(
        account_id=str(account.id),
        account_alias=account.alias,
        bank_name=account.bank_name,
        masked_account_number=mask_account_number(account.account_number),
    )


def _parse_id(raw: str) -> UUID:
    try:
        return UUID(raw)
    except (ValueError, AttributeError) as exc:
        raise AgentToolError.invalid_request(
            "account_id 형식이 올바르지 않습니다."
        ) from exc


async def _load_owned(
    session: AsyncSession, context: ResolvedExecutionContext, account_id: str
) -> Account:
    account = await get_owned_account(session, context.user_id, _parse_id(account_id))
    if account is None:
        # 소유하지 않은 계좌는 존재 여부를 노출하지 않고 거부한다.
        raise AgentToolError.account_access_denied()
    return account


async def _daily_transferred_amount(
    session: AsyncSession, context: ResolvedExecutionContext
) -> int:
    """사용자 타임존 기준 오늘 실행된 이체 금액 합계(일일 한도 산정).

    금액 원천은 EXECUTED Confirmation 의 `fixed_data.amount` 다.
    TODO(계정계): 계정계가 사용자 기준 일일 이체 합계를 제공하면 그쪽으로 위임한다.
    """
    tz = resolve_tz(context.timezone)
    today_start_local = datetime.now(tz).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    since = today_start_local.astimezone(timezone.utc)
    executed = await get_executed_transfers_since(session, context.user_id, since)
    return sum(int(c.fixed_data.get("amount", 0)) for c in executed)


async def _evaluate_internal_transfer(
    session: AsyncSession,
    context: ResolvedExecutionContext,
    from_account: Account,
    to_account: Account,
    amount: int,
) -> tuple[str, CorrectionView] | None:
    """이체 조건을 평가한다. 문제가 없으면 None, 있으면 (reason, correction_view)."""
    if from_account.id == to_account.id:
        return _correction(
            TransferReason.SAME_ACCOUNT,
            ["to_account"],
            "출금 계좌와 입금 계좌가 같습니다.",
        )
    if not from_account.active:
        return _correction(
            TransferReason.ACCOUNT_INACTIVE,
            ["from_account"],
            "다른 출금 계좌를 선택해 주세요.",
        )
    if not to_account.active:
        return _correction(
            TransferReason.ACCOUNT_INACTIVE,
            ["to_account"],
            "다른 입금 계좌를 선택해 주세요.",
        )
    if amount > MAX_SINGLE_TRANSFER_KRW:
        return _correction(
            TransferReason.LIMIT_EXCEEDED, ["amount"], "1회 이체 한도를 초과했습니다."
        )

    total_debit = amount + TRANSFER_FEE_KRW
    available = await read_available_balance(from_account)
    if available < total_debit:
        return _correction(
            TransferReason.INSUFFICIENT_BALANCE,
            ["from_account", "amount"],
            "출금 계좌 또는 금액을 변경해 주세요.",
        )

    already = await _daily_transferred_amount(session, context)
    if already + amount > MAX_DAILY_TRANSFER_KRW:
        return _correction(
            TransferReason.LIMIT_EXCEEDED, ["amount"], "일일 이체 한도를 초과했습니다."
        )
    return None


# ── #9 본인 이체 Prepare ─────────────────────────────────────────────────────


async def prepare_internal_transfer(
    session: AsyncSession,
    context: ResolvedExecutionContext,
    req: InternalTransferPrepareRequest,
) -> InternalTransferPrepareData:
    """본인 계좌 간 이체 조건을 평가하고 Confirmation 에 고정한다."""
    from_account = await _load_owned(session, context, req.from_account_id)
    to_account = await _load_owned(session, context, req.to_account_id)

    violation = await _evaluate_internal_transfer(
        session, context, from_account, to_account, req.amount
    )
    if violation is not None:
        reason, correction_view = violation
        return InternalTransferPrepareData(
            outcome=TransferOutcome.CORRECTION_REQUIRED,
            reason=reason,
            correction_view=correction_view,
        )

    total_debit = req.amount + TRANSFER_FEE_KRW
    confirmation = await confirmation_service.create_pending(
        session,
        context,
        ConfirmationOperation.INTERNAL_TRANSFER,
        fixed_data={
            "from_account_id": str(from_account.id),
            "to_account_id": str(to_account.id),
            "amount": req.amount,
            "fee": TRANSFER_FEE_KRW,
            "currency": req.currency,
        },
    )
    await financial_audit_service.record(
        session,
        context,
        event_type=EVENT_CONFIRMATION_CREATED,
        operation=_OP_INTERNAL_PREPARE,
        outcome=TransferOutcome.READY_FOR_CONFIRMATION,
        contract_id=_CONTRACT_INTERNAL_PREPARE,
        confirmation_id=confirmation.id,
    )
    return InternalTransferPrepareData(
        outcome=TransferOutcome.READY_FOR_CONFIRMATION,
        confirmation_id=str(confirmation.id),
        confirmation_view=InternalTransferConfirmationView(
            from_account=_account_ref(from_account),
            to_account=_account_ref(to_account),
            amount=req.amount,
            fee=TRANSFER_FEE_KRW,
            total_debit=total_debit,
            currency=req.currency,
            expires_at=confirmation.expires_at,
        ),
    )


# ── #10 본인 이체 Execute ────────────────────────────────────────────────────


def _ledger_idempotency_key(confirmation: Confirmation) -> str:
    """계정계로 보낼 결정적 멱등성 키(계약 24.2).

    Agent 가 보낸 헤더 값을 그대로 쓰지 않고 confirmation_id 로 직접 만든다. 재시도·
    타임아웃에도 항상 같은 키가 되어 계정계가 최초 이체를 그대로 재현한다.
    """
    return f"internal_transfer_execute:{confirmation.id}"


async def _move_ledger(
    from_account: Account, to_account: Account, amount: int, idempotency_key: str
) -> str:
    """계정계 원장을 이동시키고 transaction_id 를 반환한다."""
    if not _use_http():
        # 실제 원장은 계정계에만 있다. mock 모드에서는 이체를 시뮬레이션하지 않는다
        # (잔액을 실제로 옮기지 않은 채 completed 로 보고하면 감사 기록이 거짓이 된다).
        raise AgentToolError.backend_temporary_error()
    try:
        result = await get_financial_client().transfer(
            sender_account_number=from_account.account_number,
            receiver_bank_name=resolve_owned_account_bank(to_account),
            receiver_account_number=to_account.account_number,
            amount=amount,
            idempotency_key=idempotency_key,
        )
    except FinancialServiceError as exc:
        # 계정계 장애·거절은 업무 outcome 이 아니라 기술 오류로 반환한다(계약 17.6).
        raise AgentToolError.backend_temporary_error() from exc
    return str(result["transfer_id"])


async def execute_internal_transfer(
    session: AsyncSession,
    context: ResolvedExecutionContext,
    req: TransferExecuteRequest,
) -> TransferExecuteData:
    """승인 + 인증된 이체를 실행한다(실행 직전 재검증 포함, 계약 18.7)."""
    confirmation = await confirmation_service.load_for_execute(
        session, context, req.confirmation_id, ConfirmationOperation.INTERNAL_TRANSFER
    )
    auth_context = await auth_context_service.load_verified(
        session, context, req.auth_context_id, confirmation
    )
    # Confirmation 은 유효하고 인증만 만료됨 → 재인증(계약 18.5).
    if auth_context is None:
        return TransferExecuteData(
            outcome=TransferOutcome.REAUTHENTICATION_REQUIRED,
            reason=TransferReason.AUTH_CONTEXT_EXPIRED,
        )

    fixed = confirmation.fixed_data
    amount = int(fixed["amount"])
    from_account = await get_owned_account(
        session, context.user_id, UUID(str(fixed["from_account_id"]))
    )
    to_account = await get_owned_account(
        session, context.user_id, UUID(str(fixed["to_account_id"]))
    )
    if from_account is None or to_account is None:
        await confirmation_service.invalidate(session, confirmation)
        await auth_context_service.invalidate(session, auth_context)
        return TransferExecuteData(
            outcome=TransferOutcome.CORRECTION_REQUIRED,
            reason=TransferReason.ACCOUNT_INACTIVE,
            correction_view=CorrectionView(
                title="다른 계좌를 선택해 주세요.",
                allowed_change_targets=["from_account", "to_account"],
            ),
        )

    # 승인 이후 잔액·한도·계좌 상태가 바뀌었을 수 있어 실행 직전에 다시 판정한다.
    violation = await _evaluate_internal_transfer(
        session, context, from_account, to_account, amount
    )
    if violation is not None:
        reason, correction_view = violation
        await confirmation_service.invalidate(session, confirmation)
        await auth_context_service.invalidate(session, auth_context)
        return TransferExecuteData(
            outcome=TransferOutcome.CORRECTION_REQUIRED,
            reason=reason,
            correction_view=correction_view,
        )

    transaction_id = await _move_ledger(
        from_account, to_account, amount, _ledger_idempotency_key(confirmation)
    )
    await confirmation_service.mark_executed(session, confirmation)
    completed_at = datetime.now(timezone.utc)
    await financial_audit_service.record(
        session,
        context,
        event_type=EVENT_FINANCIAL_EXECUTION_COMPLETED,
        operation=_OP_INTERNAL_EXECUTE,
        outcome=TransferOutcome.COMPLETED,
        contract_id=_CONTRACT_INTERNAL_EXECUTE,
        confirmation_id=confirmation.id,
        auth_context_id=auth_context.id,
        transaction_id=transaction_id,
        idempotency_key=_ledger_idempotency_key(confirmation),
    )
    return TransferExecuteData(
        outcome=TransferOutcome.COMPLETED,
        transaction_id=transaction_id,
        completed_at=completed_at,
    )


__all__ = ["prepare_internal_transfer", "execute_internal_transfer"]
