"""FastAPI routers — 5 endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session

from .crud import (
    ConflictError,
    NotFoundError,
    ValidationError,
    create_account,
    get_account,
    get_balance,
    get_ledger_entries,
    transfer,
)
from .database import get_db
from .schemas import (
    AccountCreate,
    AccountResponse,
    BalanceResponse,
    ErrorResponse,
    LedgerEntryResponse,
    TransferRequest,
    TransferResponse,
)

router = APIRouter()

DbDep = Annotated[Session, Depends(get_db)]


def _err(status: int, code: str, msg: str):
    raise HTTPException(status_code=status, detail={"error_code": code, "message": msg})


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
        _err(404, "ACCOUNT_NOT_FOUND", f"Account {account_id} not found")
    balance = get_balance(db, account_id)
    return AccountResponse(
        account_id=acct.account_id,
        owner=acct.owner,
        balance=balance,
        currency=acct.currency,
        created_at=acct.created_at,
    )


# ── 3. GET /accounts/{account_id}/balance — balance ──────────────────────────


@router.get(
    "/accounts/{account_id}/balance",
    response_model=BalanceResponse,
    responses={404: {"model": ErrorResponse}},
)
def get_balance_endpoint(account_id: str, db: DbDep):
    acct = get_account(db, account_id)
    if acct is None:
        _err(404, "ACCOUNT_NOT_FOUND", f"Account {account_id} not found")
    balance = get_balance(db, account_id)
    return BalanceResponse(
        account_id=account_id, balance=balance, currency=acct.currency
    )


# ── 4. GET /accounts/{account_id}/transactions — ledger history ───────────────


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
):
    acct = get_account(db, account_id)
    if acct is None:
        _err(404, "ACCOUNT_NOT_FOUND", f"Account {account_id} not found")
    entries = get_ledger_entries(db, account_id, limit=limit, offset=offset)
    return [
        LedgerEntryResponse(
            entry_id=e.entry_id,
            transaction_id=e.transaction_id,
            entry_type=e.entry_type,
            amount=e.amount,
            running_balance=e.running_balance,
            created_at=e.created_at,
        )
        for e in entries
    ]


# ── 5. POST /transfers — transfer ────────────────────────────────────────────


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
        _err(422, "MISSING_IDEMPOTENCY_KEY", "Idempotency-Key header is required")

    try:
        txn = transfer(db, payload, idempotency_key)
    except ValidationError as e:
        _err(422, e.error_code, e.message)
    except NotFoundError as e:
        _err(404, e.error_code, e.message)
    except ConflictError as e:
        _err(409, e.error_code, e.message)

    return TransferResponse(
        transfer_id=txn.transaction_id,
        from_account=txn.sender_account_id,
        to_account=txn.receiver_account_id,
        amount=txn.amount,
        status=txn.status,
        created_at=txn.created_at,
    )
