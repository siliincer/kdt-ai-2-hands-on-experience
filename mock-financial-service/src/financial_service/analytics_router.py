"""정보계 (downstream analytics) read endpoints.

All routes under /analytics/ require X-Analytics-Key header.
Existing 계정계 endpoints remain unauthenticated (out-of-scope for auth retrofit).
"""

import os
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session

from .crud import (
    get_account,
    get_audit_logs,
    get_balance,
    get_card,
    get_card_ledger_entries,
    get_ledger_entries,
    get_snapshot,
    reconcile_snapshot,
)
from .database import get_db
from .schemas import (
    AuditLogResponse,
    BalanceResponse,
    CardLedgerEntryResponse,
    CardResponse,
    ErrorResponse,
    LedgerEntryResponse,
    ReconciliationResponse,
    SnapshotResponse,
)
from .utils import throw_err

# 정보계 read access API key. Default keeps local/demo runs working with no
# setup; override via env var for any shared or non-local environment.
ANALYTICS_API_KEY = os.environ.get("ANALYTICS_API_KEY", "analytics-demo-key")

analytics_router = APIRouter(prefix="/analytics", tags=["정보계"])

DbDep = Annotated[Session, Depends(get_db)]


def _require_analytics_key(
    x_analytics_key: Annotated[str | None, Header(alias="X-Analytics-Key")] = None,
) -> None:
    """FastAPI dependency — rejects requests without valid analytics API key."""
    if x_analytics_key != ANALYTICS_API_KEY:
        raise HTTPException(
            status_code=401,
            detail={
                "error_code": "UNAUTHORIZED",
                "message": "Valid X-Analytics-Key required",
            },
        )


AnalyticsAuth = Annotated[None, Depends(_require_analytics_key)]


# ── GET /analytics/accounts/{account_id}/snapshot ────────────────────────────


@analytics_router.get(
    "/accounts/{account_id}/snapshot",
    response_model=SnapshotResponse,
    responses={404: {"model": ErrorResponse}, 401: {"model": ErrorResponse}},
    summary="Read cached balance snapshot (정보계)",
)
def get_snapshot_endpoint(account_id: str, db: DbDep, _auth: AnalyticsAuth):
    """Return the latest balance snapshot for an account.

    Returns 404 if no snapshot has been generated yet
    (call POST /accounts/{id}/snapshot first).
    """
    acct = get_account(db, account_id)
    if acct is None:
        throw_err(404, "ACCOUNT_NOT_FOUND", f"Account {account_id} not found")
    snap = get_snapshot(db, account_id)
    if snap is None:
        throw_err(
            404,
            "SNAPSHOT_NOT_FOUND",
            f"No snapshot for {account_id}. "
            f"Call POST /accounts/{account_id}/snapshot first.",
        )
    return snap


# ── GET /analytics/accounts/{account_id}/reconcile ───────────────────────────


@analytics_router.get(
    "/accounts/{account_id}/reconcile",
    response_model=ReconciliationResponse,
    responses={404: {"model": ErrorResponse}, 401: {"model": ErrorResponse}},
    summary="Reconcile cached snapshot vs live ledger (정보계)",
)
def reconcile_endpoint(account_id: str, db: DbDep, _auth: AnalyticsAuth):
    """Compare watermark-scoped stored sums vs live recompute.

    drift_detected=true means cached_balance diverges from recomputed
    sum at watermark. Pure read — does not acquire locks or block ledger writes.
    """
    acct = get_account(db, account_id)
    if acct is None:
        throw_err(404, "ACCOUNT_NOT_FOUND", f"Account {account_id} not found")
    result = reconcile_snapshot(db, account_id)
    return result


# ── GET /analytics/accounts/{account_id}/balance ─────────────────────────────


@analytics_router.get(
    "/accounts/{account_id}/balance",
    response_model=BalanceResponse,
    responses={404: {"model": ErrorResponse}, 401: {"model": ErrorResponse}},
    summary="Read canonical account balance (정보계)",
)
def get_analytics_balance(account_id: str, db: DbDep, _auth: AnalyticsAuth):
    """Return canonical balance (SUM CREDIT - SUM DEBIT) for the account.

    Identical to /api/v1/accounts/{id}/balance but protected by X-Analytics-Key.
    """
    acct = get_account(db, account_id)
    if acct is None:
        throw_err(404, "ACCOUNT_NOT_FOUND", f"Account {account_id} not found")
    balance = get_balance(db, account_id)
    return BalanceResponse(
        account_id=account_id, balance=balance, currency=acct.currency
    )


# ── GET /analytics/accounts/{account_id}/ledger ──────────────────────────────


@analytics_router.get(
    "/accounts/{account_id}/ledger",
    response_model=list[LedgerEntryResponse],
    responses={404: {"model": ErrorResponse}, 401: {"model": ErrorResponse}},
    summary="Read ledger entries (정보계)",
)
def get_analytics_ledger(
    account_id: str,
    db: DbDep,
    _auth: AnalyticsAuth,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """Return ledger entries for an account in descending creation order.

    Identical data to /api/v1/accounts/{id}/transactions but protected
    by X-Analytics-Key.
    """
    acct = get_account(db, account_id)
    if acct is None:
        throw_err(404, "ACCOUNT_NOT_FOUND", f"Account {account_id} not found")
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


# ── GET /analytics/accounts/{account_id}/audit-logs ──────────────────────────


@analytics_router.get(
    "/accounts/{account_id}/audit-logs",
    response_model=list[AuditLogResponse],
    responses={404: {"model": ErrorResponse}, 401: {"model": ErrorResponse}},
    summary="Read audit logs linked to an account (정보계)",
)
def get_analytics_audit_logs(
    account_id: str,
    db: DbDep,
    _auth: AnalyticsAuth,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """Return audit log entries linked to this account via its transactions.

    Covers ACCOUNT_CREATE and TRANSFER/TRANSFER_FAILED entries where the
    account was sender or receiver. Read-only — audit_logs stays DB-trigger
    immutable regardless of this read path.
    """
    acct = get_account(db, account_id)
    if acct is None:
        throw_err(404, "ACCOUNT_NOT_FOUND", f"Account {account_id} not found")
    logs = get_audit_logs(db, account_id, limit=limit, offset=offset)
    return [
        AuditLogResponse(
            audit_log_id=log.audit_log_id,
            transaction_id=log.transaction_id,
            actor=log.actor,
            action=log.action,
            reason=log.reason,
            status=log.status,
            timestamp=log.timestamp,
        )
        for log in logs
    ]


# ── GET /analytics/cards/{card_id} ───────────────────────────────────────────


@analytics_router.get(
    "/cards/{card_id}",
    response_model=CardResponse,
    responses={404: {"model": ErrorResponse}, 401: {"model": ErrorResponse}},
    summary="Read card details (정보계)",
)
def get_analytics_card(card_id: str, db: DbDep, _auth: AnalyticsAuth):
    card = get_card(db, card_id)
    if card is None:
        throw_err(404, "CARD_NOT_FOUND", f"Card {card_id} not found")
    return CardResponse(
        card_id=card.card_id,
        account_id=card.account_id,
        limit=card.limit,
        currency=card.currency,
        created_at=card.created_at,
    )


# ── GET /analytics/cards/{card_id}/ledger ────────────────────────────────────


@analytics_router.get(
    "/cards/{card_id}/ledger",
    response_model=list[CardLedgerEntryResponse],
    responses={404: {"model": ErrorResponse}, 401: {"model": ErrorResponse}},
    summary="Read card ledger entries (정보계)",
)
def get_analytics_card_ledger(
    card_id: str,
    db: DbDep,
    _auth: AnalyticsAuth,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """Return card-ledger entries (purchases) for a card in descending order.

    Covers all entries: settled and unsettled. Settlement boundary is determined
    by settlement_watermark_rowid on the latest CARD_SETTLEMENT Transaction.
    Protected by X-Analytics-Key (정보계 read pattern).
    """
    card = get_card(db, card_id)
    if card is None:
        throw_err(404, "CARD_NOT_FOUND", f"Card {card_id} not found")
    entries = get_card_ledger_entries(db, card_id, limit=limit, offset=offset)
    return [
        CardLedgerEntryResponse(
            card_ledger_entry_id=e.card_ledger_entry_id,
            card_id=e.card_id,
            amount=e.amount,
            created_at=e.created_at,
        )
        for e in entries
    ]
