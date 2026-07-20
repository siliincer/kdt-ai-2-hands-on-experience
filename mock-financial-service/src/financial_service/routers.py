"""FastAPI routers — 7 endpoints."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.orm import Session

from .crud import (
    ConflictError,
    NotFoundError,
    ValidationError,
    create_account,
    get_account,
    get_account_by_number,
    get_balance,
    get_ledger_entries,
    ledger_entry_counterparty_fields,
    transfer,
    update_account_alias,
)
from .database import get_db
from .models import BANK_NAME
from .schemas import (
    AccountAliasUpdate,
    AccountCreate,
    AccountResponse,
    BalanceResponse,
    ErrorResponse,
    LedgerEntryResponse,
    TransferRequest,
    TransferResponse,
)
from .utils import throw_err

router = APIRouter()

DbDep = Annotated[Session, Depends(get_db)]

# ── 1. POST /accounts — create account ───────────────────────────────────────


@router.post(
    "/accounts",
    response_model=AccountResponse,
    status_code=201,
    responses={422: {"model": ErrorResponse}},
)
def create_account_endpoint(payload: AccountCreate, db: DbDep):
    acct, balance = create_account(db, payload)
    return AccountResponse(
        account_id=acct.account_id,
        owner=acct.owner,
        bank_name=acct.bank_name,
        account_number=acct.account_number,
        alias=acct.alias,
        balance=balance,
        currency=acct.currency,
        created_at=acct.created_at,
    )


# ── 2. GET /accounts/{account_id} — get account ──────────────────────────────


@router.get(
    "/accounts/{account_id}",
    response_model=AccountResponse,
    responses={404: {"model": ErrorResponse}},
)
def get_account_endpoint(account_id: str, db: DbDep):
    acct = get_account(db, account_id)
    if acct is None:
        throw_err(404, "ACCOUNT_NOT_FOUND", f"Account {account_id} not found")
    balance = get_balance(db, account_id)
    return AccountResponse(
        account_id=acct.account_id,
        owner=acct.owner,
        bank_name=acct.bank_name,
        account_number=acct.account_number,
        alias=acct.alias,
        balance=balance,
        currency=acct.currency,
        created_at=acct.created_at,
    )


# ── 3. GET /accounts/by-number/{account_number} — lookup(예금주 조회) ────────
# TODO(계정계) 해소: 계좌번호 기반 조회 — 신규 수취 계좌 검증(D5)이 여기로 위임 가능.


@router.get(
    "/accounts/by-number/{account_number}",
    response_model=AccountResponse,
    responses={404: {"model": ErrorResponse}},
)
def get_account_by_number_endpoint(account_number: str, db: DbDep):
    acct = get_account_by_number(db, account_number)
    if acct is None:
        throw_err(
            404, "ACCOUNT_NOT_FOUND", f"Account with number {account_number} not found"
        )
    balance = get_balance(db, acct.account_id)
    return AccountResponse(
        account_id=acct.account_id,
        owner=acct.owner,
        bank_name=acct.bank_name,
        account_number=acct.account_number,
        alias=acct.alias,
        balance=balance,
        currency=acct.currency,
        created_at=acct.created_at,
    )


# ── 4. PATCH /accounts/{account_id}/alias — alias 변경 ───────────────────────
# TODO(계정계) 해소: 별칭 write endpoint.


@router.patch(
    "/accounts/{account_id}/alias",
    response_model=AccountResponse,
    responses={404: {"model": ErrorResponse}},
)
def update_account_alias_endpoint(
    account_id: str, payload: AccountAliasUpdate, db: DbDep
):
    acct = update_account_alias(db, account_id, payload.alias)
    if acct is None:
        throw_err(404, "ACCOUNT_NOT_FOUND", f"Account {account_id} not found")
    balance = get_balance(db, account_id)
    return AccountResponse(
        account_id=acct.account_id,
        owner=acct.owner,
        bank_name=acct.bank_name,
        account_number=acct.account_number,
        alias=acct.alias,
        balance=balance,
        currency=acct.currency,
        created_at=acct.created_at,
    )


# ── 5. GET /accounts/{account_id}/balance — balance ──────────────────────────


@router.get(
    "/accounts/{account_id}/balance",
    response_model=BalanceResponse,
    responses={404: {"model": ErrorResponse}},
)
def get_balance_endpoint(account_id: str, db: DbDep):
    acct = get_account(db, account_id)
    if acct is None:
        throw_err(404, "ACCOUNT_NOT_FOUND", f"Account {account_id} not found")
    balance = get_balance(db, account_id)
    return BalanceResponse(
        account_id=account_id, balance=balance, currency=acct.currency
    )


# ── 6. GET /accounts/{account_id}/transactions — ledger history ───────────────


@router.get(
    "/accounts/{account_id}/transactions",
    response_model=list[LedgerEntryResponse],
    responses={404: {"model": ErrorResponse}},
)
def get_transactions_endpoint(
    account_id: str,
    db: DbDep,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
):
    acct = get_account(db, account_id)
    if acct is None:
        throw_err(404, "ACCOUNT_NOT_FOUND", f"Account {account_id} not found")
    entries = get_ledger_entries(
        db,
        account_id,
        limit=limit,
        offset=offset,
        start_date=start_date,
        end_date=end_date,
    )
    return [
        LedgerEntryResponse(
            entry_id=e.entry_id,
            transaction_id=e.transaction_id,
            entry_type=e.entry_type,
            amount=e.amount,
            running_balance=e.running_balance,
            created_at=e.created_at,
            **ledger_entry_counterparty_fields(e),
        )
        for e in entries
    ]


# ── 7. POST /transfers — transfer ────────────────────────────────────────────


@router.post(
    "/transfers",
    response_model=TransferResponse,
    status_code=200,
    responses={
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
def transfer_endpoint(
    payload: TransferRequest,
    db: DbDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
):
    if not idempotency_key:
        throw_err(422, "MISSING_IDEMPOTENCY_KEY", "Idempotency-Key header is required")

    try:
        txn = transfer(db, payload, idempotency_key)
    except ValidationError as e:
        throw_err(422, e.error_code, e.message)
    except NotFoundError as e:
        throw_err(404, e.error_code, e.message)
    except ConflictError as e:
        throw_err(409, e.error_code, e.message)

    return TransferResponse(
        transfer_id=txn.transaction_id,
        from_account=txn.sender_account_id,
        to_account=txn.receiver_account_id,
        sender_bank_name=BANK_NAME,
        sender_account_number=payload.sender_account_number,
        receiver_bank_name=payload.receiver_bank_name,
        receiver_account_number=payload.receiver_account_number,
        amount=txn.amount,
        status=txn.status,
        created_at=txn.created_at,
    )
