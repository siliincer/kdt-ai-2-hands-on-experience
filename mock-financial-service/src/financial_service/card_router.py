"""Card write endpoints — POST /api/v1/cards, charges, settlement.

No auth (consistent with existing demo-scope decision for account endpoints).
Charge endpoint requires Idempotency-Key header
(same pattern as POST /api/v1/transfers).
"""

from typing import Annotated, cast

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from .crud import (
    NotFoundError,
    ValidationError,
    charge_card,
    create_card,
    get_card,
    settle_card,
)
from .database import get_db
from .err import _err
from .schemas import (
    CardChargeRequest,
    CardChargeResponse,
    CardCreate,
    CardResponse,
    CardSettleResponse,
    ErrorResponse,
)

card_router = APIRouter(tags=["카드"])

DbDep = Annotated[Session, Depends(get_db)]


# ── POST /cards — create card ─────────────────────────────────────────────────


@card_router.post(
    "/cards",
    response_model=CardResponse,
    status_code=201,
    responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    summary="Create a card under an existing account",
)
def create_card_endpoint(payload: CardCreate, db: DbDep):
    try:
        card = create_card(db, payload)
    except NotFoundError as e:
        _err(404, e.error_code, e.message)

    return CardResponse(
        card_id=card.card_id,
        account_id=card.account_id,
        limit=card.limit,
        currency=card.currency,
        created_at=card.created_at,
    )


# ── GET /cards/{card_id} — get card ──────────────────────────────────────────


@card_router.get(
    "/cards/{card_id}",
    response_model=CardResponse,
    responses={404: {"model": ErrorResponse}},
    summary="Get card details",
)
def get_card_endpoint(card_id: str, db: DbDep):
    card = get_card(db, card_id)
    if card is None:
        _err(404, "CARD_NOT_FOUND", f"Card {card_id} not found")
    return CardResponse(
        card_id=card.card_id,
        account_id=card.account_id,
        limit=card.limit,
        currency=card.currency,
        created_at=card.created_at,
    )


# ── POST /cards/{card_id}/charges — charge card ───────────────────────────────


@card_router.post(
    "/cards/{card_id}/charges",
    response_model=CardChargeResponse,
    status_code=201,
    responses={
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
    summary="Record a card purchase (deferred — account untouched until settlement)",
)
def charge_card_endpoint(
    card_id: str,
    payload: CardChargeRequest,
    db: DbDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
):
    if not idempotency_key:
        _err(422, "MISSING_IDEMPOTENCY_KEY", "Idempotency-Key header is required")

    try:
        entry = charge_card(db, card_id, payload, idempotency_key)
    except ValidationError as e:
        _err(422, e.error_code, e.message)
    except NotFoundError as e:
        _err(404, e.error_code, e.message)

    return CardChargeResponse(
        card_ledger_entry_id=entry.card_ledger_entry_id,
        card_id=entry.card_id,
        amount=entry.amount,
        created_at=entry.created_at,
    )


# ── POST /cards/{card_id}/settle — settle card ────────────────────────────────


@card_router.post(
    "/cards/{card_id}/settle",
    response_model=CardSettleResponse,
    status_code=200,
    responses={
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
    summary="Settle all unsettled card charges (advances watermark, debits account)",
)
def settle_card_endpoint(card_id: str, db: DbDep):
    try:
        txn = settle_card(db, card_id)
    except ValidationError as e:
        _err(422, e.error_code, e.message)
    except NotFoundError as e:
        _err(404, e.error_code, e.message)

    settlement_watermark_rowid = cast(int, txn.settlement_watermark_rowid)
    settlement_card_id = cast(str, txn.settlement_card_id)

    return CardSettleResponse(
        transaction_id=txn.transaction_id,
        card_id=settlement_card_id,
        settled_amount=txn.amount,
        settlement_watermark_rowid=settlement_watermark_rowid,
        status=txn.status,
        created_at=txn.created_at,
    )
