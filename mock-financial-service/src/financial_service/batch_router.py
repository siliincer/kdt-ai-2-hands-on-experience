"""EOD 배치 엔드포인트 — 일일 마감(daily closing) 시뮬레이션.

실제 cron/스케줄러 프로세스는 없음. 자정 트리거는 scripts/run_daily_close.py 를
OS cron에 등록해 재현하거나, 이 라우터의 POST /batch/daily-close 로 수동 실행.
No auth (기존 계정계 엔드포인트와 동일한 데모 스코프 결정).
"""

from datetime import date as date_type
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .crud import get_account, list_daily_closings, run_daily_closing
from .database import get_db
from .schemas import (
    DailyClosingBatchResponse,
    DailyClosingSnapshotResponse,
    ErrorResponse,
)

batch_router = APIRouter(prefix="/batch", tags=["배치"])

DbDep = Annotated[Session, Depends(get_db)]


def _err(status: int, code: str, msg: str):
    raise HTTPException(status_code=status, detail={"error_code": code, "message": msg})


# ── POST /batch/daily-close — EOD 마감 배치 실행 ──────────────────────────────


@batch_router.post(
    "/daily-close",
    response_model=DailyClosingBatchResponse,
    summary="Run EOD daily closing batch (모든 계좌, 영업일당 1행, idempotent)",
)
def run_daily_close_endpoint(
    db: DbDep,
    business_date: date_type | None = Query(
        default=None,
        description="Override 영업일 (백필/테스트용, 기본값: 오늘 UTC)",
    ),
):
    resolved_date, snapshots = run_daily_closing(db, business_date)
    return DailyClosingBatchResponse(
        business_date=resolved_date,
        accounts_closed=len(snapshots),
        snapshots=snapshots,
    )


# ── GET /batch/accounts/{account_id}/daily-closings — 계좌별 마감 이력 ────────


@batch_router.get(
    "/accounts/{account_id}/daily-closings",
    response_model=list[DailyClosingSnapshotResponse],
    responses={404: {"model": ErrorResponse}},
)
def list_daily_closings_endpoint(
    account_id: str,
    db: DbDep,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    acct = get_account(db, account_id)
    if acct is None:
        _err(404, "ACCOUNT_NOT_FOUND", f"Account {account_id} not found")
    return list_daily_closings(db, account_id, limit=limit, offset=offset)
