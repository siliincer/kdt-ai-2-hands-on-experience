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
from ...models.account import Account
from ...models.confirmation import Confirmation, ConfirmationOperation
from ...models.financial_audit_log import (
    EVENT_CONFIRMATION_CREATED,
    EVENT_FINANCIAL_EXECUTION_COMPLETED,
)
from ...models.recipient_candidate import CANDIDATE_STATUS_VERIFIED
from ...repository.account_repository import get_account_by_id, get_owned_account
from ...repository.confirmation_repository import (
    get_executed_external_transfers,
    get_executed_transfers_since,
)
from ...repository.recipient_candidate_repository import (
    get_recipient_candidate_by_id,
    mark_candidate_consumed,
)
from ...schemas.agent_tools.common import AccountDisplayRef, CorrectionView
from ...schemas.agent_tools.transfer import (
    WARNING_NEW_RECIPIENT,
    ExternalTransferConfirmationView,
    ExternalTransferPrepareData,
    ExternalTransferPrepareRequest,
    InternalTransferConfirmationView,
    InternalTransferPrepareData,
    InternalTransferPrepareRequest,
    RecipientRef,
    TransferExecuteData,
    TransferExecuteRequest,
    TransferOutcome,
    TransferReason,
)
from ...schemas.execution_context import ResolvedExecutionContext
from ...utils.masking import mask_account_number, mask_person_name
from ...utils.parsing import parse_uuid
from ...utils.timezone import resolve_tz
from .. import auth_context_service, confirmation_service, financial_audit_service
from ..financial import (
    FinancialServiceError,
    get_financial_client,
    is_financial_http_mode,
)
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


def _correction(
    reason: str, targets: list[str], title: str
) -> tuple[str, CorrectionView]:
    return reason, CorrectionView(title=title, allowed_change_targets=targets)


def _account_ref(account: Account) -> AccountDisplayRef:
    return AccountDisplayRef(
        account_id=str(account.id),
        account_alias=account.alias,
        bank_name=account.bank_name,
        masked_account_number=mask_account_number(account.account_number),
    )


def _invalid_account_id() -> AgentToolError:
    return AgentToolError.invalid_request("account_id 형식이 올바르지 않습니다.")


async def _load_owned(
    session: AsyncSession, context: ResolvedExecutionContext, account_id: str
) -> Account:
    account = await get_owned_account(
        session, context.user_id, parse_uuid(account_id, _invalid_account_id)
    )
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
    if not is_financial_http_mode():
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


# ── #6 타인송금 Prepare ──────────────────────────────────────────────────────

_CONTRACT_EXTERNAL_PREPARE = "API-EXTERNAL-TRANSFER-PREPARE"
_OP_EXTERNAL_PREPARE = "external_transfer_prepare"


async def _evaluate_withdrawal(
    session: AsyncSession,
    context: ResolvedExecutionContext,
    from_account: Account,
    amount: int,
) -> tuple[str, CorrectionView] | None:
    """출금 측 공통 판정(활성·1회 한도·잔액·일일 한도). 문제 없으면 None."""
    if not from_account.active:
        return _correction(
            TransferReason.ACCOUNT_INACTIVE,
            ["from_account"],
            "다른 출금 계좌를 선택해 주세요.",
        )
    if amount > MAX_SINGLE_TRANSFER_KRW:
        return _correction(
            TransferReason.LIMIT_EXCEEDED, ["amount"], "1회 이체 한도를 초과했습니다."
        )
    available = await read_available_balance(from_account)
    if available < amount + TRANSFER_FEE_KRW:
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


def _recipient_correction() -> tuple[str, CorrectionView]:
    return _correction(
        TransferReason.RECIPIENT_NOT_VERIFIED,
        ["recipient"],
        "받는 분 계좌를 다시 확인해 주세요.",
    )


async def _resolve_existing_recipient(
    session: AsyncSession,
    context: ResolvedExecutionContext,
    to_recipient_id: str,
) -> tuple[Account, str]:
    """기존 수취인 참조를 검증한다(계약 14.2).

    `to_recipient_id` 는 본인의 실행 완료된 타인송금 이력에 등장한 계좌만 허용한다
    (임의 계좌 열거 차단). 이력에 없으면 `RECIPIENT_NOT_FOUND`(404).
    """
    recipient_account_id = parse_uuid(
        to_recipient_id, AgentToolError.recipient_not_found
    )
    executed = await get_executed_external_transfers(session, context.user_id)
    name: str | None = None
    for confirmation in executed:
        fixed = confirmation.fixed_data
        if str(fixed.get("recipient_account_id")) == str(recipient_account_id):
            name = str(fixed.get("recipient_name") or "") or name
    if name is None:
        raise AgentToolError.recipient_not_found()

    account = await get_account_by_id(session, recipient_account_id)
    if account is None:
        raise AgentToolError.recipient_not_found()
    return account, name


async def _resolve_candidate_recipient(
    session: AsyncSession,
    context: ResolvedExecutionContext,
    to_recipient_candidate_id: str,
) -> tuple[Account, str, object]:
    """신규 검증 수취인 후보를 검증한다(계약 14.3). 반환: (계좌, 이름, 후보행)."""
    candidate_id = parse_uuid(
        to_recipient_candidate_id, AgentToolError.recipient_not_found
    )

    candidate = await get_recipient_candidate_by_id(session, candidate_id)
    if candidate is None or candidate.user_id != context.user_id:
        # 다른 사용자의 후보는 존재 여부를 노출하지 않는다.
        raise AgentToolError.recipient_not_found()
    if candidate.status != CANDIDATE_STATUS_VERIFIED:
        raise AgentToolError.recipient_candidate_expired()
    if candidate.expires_at <= datetime.now(timezone.utc):
        raise AgentToolError.recipient_candidate_expired()

    account = await get_account_by_id(session, candidate.recipient_account_id)
    if account is None:
        raise AgentToolError.recipient_not_found()
    return account, candidate.resolved_name, candidate


async def prepare_external_transfer(
    session: AsyncSession,
    context: ResolvedExecutionContext,
    req: ExternalTransferPrepareRequest,
) -> ExternalTransferPrepareData:
    """타인송금 조건을 평가하고 Confirmation 에 고정한다(계약 14장).

    `fixed_data` 의 recipient_account_id·recipient_name 은 #5(recipients:resolve)의
    이력 원천이 된다 — 이 계약을 바꾸면 recipient_service 도 함께 바꿔야 한다.
    """
    from_account = await _load_owned(session, context, req.from_account_id)

    candidate = None
    if req.to_recipient_id is not None:
        recipient_account, recipient_name = await _resolve_existing_recipient(
            session, context, req.to_recipient_id
        )
    else:
        (
            recipient_account,
            recipient_name,
            candidate,
        ) = await _resolve_candidate_recipient(
            session, context, str(req.to_recipient_candidate_id)
        )

    # 수취 계좌가 비활성이거나 본인 소유면 수취인 재선택으로 유도한다.
    if not recipient_account.active or recipient_account.user_id == context.user_id:
        reason, correction_view = _recipient_correction()
        return ExternalTransferPrepareData(
            outcome=TransferOutcome.CORRECTION_REQUIRED,
            reason=reason,
            correction_view=correction_view,
        )

    violation = await _evaluate_withdrawal(session, context, from_account, req.amount)
    if violation is not None:
        reason, correction_view = violation
        return ExternalTransferPrepareData(
            outcome=TransferOutcome.CORRECTION_REQUIRED,
            reason=reason,
            correction_view=correction_view,
        )

    is_new_recipient = candidate is not None
    confirmation = await confirmation_service.create_pending(
        session,
        context,
        ConfirmationOperation.EXTERNAL_TRANSFER,
        fixed_data={
            "from_account_id": str(from_account.id),
            "recipient_account_id": str(recipient_account.id),
            "recipient_name": recipient_name,
            "amount": req.amount,
            "fee": TRANSFER_FEE_KRW,
            "currency": req.currency,
        },
    )
    if candidate is not None:
        # 후보는 1회용 참조 — Confirmation 에 고정됐으므로 소비 처리한다.
        await mark_candidate_consumed(session, candidate)  # type: ignore[arg-type]

    warning_codes = [WARNING_NEW_RECIPIENT] if is_new_recipient else []
    await financial_audit_service.record(
        session,
        context,
        event_type=EVENT_CONFIRMATION_CREATED,
        operation=_OP_EXTERNAL_PREPARE,
        outcome=TransferOutcome.READY_FOR_CONFIRMATION,
        contract_id=_CONTRACT_EXTERNAL_PREPARE,
        confirmation_id=confirmation.id,
        policy_codes=warning_codes,
    )
    return ExternalTransferPrepareData(
        outcome=TransferOutcome.READY_FOR_CONFIRMATION,
        confirmation_id=str(confirmation.id),
        confirmation_view=ExternalTransferConfirmationView(
            from_account=_account_ref(from_account),
            recipient=RecipientRef(
                name=mask_person_name(recipient_name),
                bank_name=resolve_owned_account_bank(recipient_account),
                masked_account_number=mask_account_number(
                    recipient_account.account_number
                ),
            ),
            amount=req.amount,
            fee=TRANSFER_FEE_KRW,
            total_debit=req.amount + TRANSFER_FEE_KRW,
            currency=req.currency,
            variant="warning" if warning_codes else "default",
            warning_codes=warning_codes,
            expires_at=confirmation.expires_at,
        ),
    )


# ── #8 타인송금 Execute ──────────────────────────────────────────────────────

_CONTRACT_EXTERNAL_EXECUTE = "API-EXTERNAL-TRANSFER-EXECUTE"
_OP_EXTERNAL_EXECUTE = "external_transfer_execute"


async def execute_external_transfer(
    session: AsyncSession,
    context: ResolvedExecutionContext,
    req: TransferExecuteRequest,
) -> TransferExecuteData:
    """승인 + 인증된 타인송금을 실행한다(실행 직전 재검증 포함, 계약 16.7).

    모든 타인송금은 추가 인증이 필수라 confirmation_id 와 auth_context_id 를 받는다.
    송금 조건(출금 계좌·수취인·금액)은 Confirmation `fixed_data` 를 신뢰한다.
    """
    confirmation = await confirmation_service.load_for_execute(
        session, context, req.confirmation_id, ConfirmationOperation.EXTERNAL_TRANSFER
    )
    auth_context = await auth_context_service.load_verified(
        session, context, req.auth_context_id, confirmation
    )
    # Confirmation 은 유효하고 인증만 만료됨 → 재인증(계약 16.5).
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
    recipient_account = await get_account_by_id(
        session, UUID(str(fixed["recipient_account_id"]))
    )

    async def _invalidate_pair() -> None:
        await confirmation_service.invalidate(session, confirmation)
        await auth_context_service.invalidate(session, auth_context)

    if from_account is None or not from_account.active:
        await _invalidate_pair()
        return TransferExecuteData(
            outcome=TransferOutcome.CORRECTION_REQUIRED,
            reason=TransferReason.ACCOUNT_INACTIVE,
            correction_view=CorrectionView(
                title="다른 출금 계좌를 선택해 주세요.",
                allowed_change_targets=["from_account"],
            ),
        )
    # 승인 이후 수취인 상태가 바뀌었을 수 있다(계약 16.7 "수취인 현재 상태").
    if (
        recipient_account is None
        or not recipient_account.active
        or recipient_account.user_id == context.user_id
    ):
        await _invalidate_pair()
        reason, correction_view = _recipient_correction()
        return TransferExecuteData(
            outcome=TransferOutcome.CORRECTION_REQUIRED,
            reason=reason,
            correction_view=correction_view,
        )

    violation = await _evaluate_withdrawal(session, context, from_account, amount)
    if violation is not None:
        reason, correction_view = violation
        await _invalidate_pair()
        return TransferExecuteData(
            outcome=TransferOutcome.CORRECTION_REQUIRED,
            reason=reason,
            correction_view=correction_view,
        )

    ledger_key = f"{_OP_EXTERNAL_EXECUTE}:{confirmation.id}"
    transaction_id = await _move_ledger(
        from_account, recipient_account, amount, ledger_key
    )
    await confirmation_service.mark_executed(session, confirmation)
    completed_at = datetime.now(timezone.utc)
    await financial_audit_service.record(
        session,
        context,
        event_type=EVENT_FINANCIAL_EXECUTION_COMPLETED,
        operation=_OP_EXTERNAL_EXECUTE,
        outcome=TransferOutcome.COMPLETED,
        contract_id=_CONTRACT_EXTERNAL_EXECUTE,
        confirmation_id=confirmation.id,
        auth_context_id=auth_context.id,
        transaction_id=transaction_id,
        idempotency_key=ledger_key,
    )
    return TransferExecuteData(
        outcome=TransferOutcome.COMPLETED,
        transaction_id=transaction_id,
        completed_at=completed_at,
    )


__all__ = [
    "prepare_internal_transfer",
    "execute_internal_transfer",
    "prepare_external_transfer",
    "execute_external_transfer",
]
