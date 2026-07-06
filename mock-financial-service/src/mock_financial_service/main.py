"""Mock Financial Service — Fake Money 원장 API.

시트 API Spec 탭의 계약을 구현한다. agent의 HttpBankClient(BANK_CLIENT=http)가
이 서비스를 호출한다. 진입점: mock_financial_service.main:app (포트 8002).

에러 의미론:
  - GET /api/accounts/{user_id}: 사용자/계좌 없음 -> 404
  - GET /api/recipients: 검색형 엔드포인트 -> 무매칭도 200 + 빈 목록
  - POST transfer-external: 계좌/수취인 없음 404, 잔액 부족 409, 금액 오류 422
"""

from __future__ import annotations

import uuid

from fastapi import FastAPI, HTTPException, status

from mock_financial_service import ledger
from mock_financial_service.schemas import (
    AuditLogRequest,
    AuditLogResponse,
    TransferRequest,
    TransferResponse,
)

app = FastAPI(title="Mock Financial Service", version="0.1.0")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/accounts/{user_id}")
def get_accounts(user_id: str, account_id: str | None = None) -> dict:
    accounts = ledger.ACCOUNTS.get(user_id)
    if not accounts:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="사용자를 찾을 수 없습니다.",
        )
    if account_id:
        accounts = [a for a in accounts if a["account_id"] == account_id]
        if not accounts:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="계좌를 찾을 수 없습니다.",
            )
    return {"user_id": user_id, "accounts": accounts}


@app.get("/api/recipients")
def get_recipients(user_id: str, recipient_name: str | None = None) -> dict:
    recipients = ledger.RECIPIENTS.get(user_id, [])
    if recipient_name:
        recipients = [r for r in recipients if recipient_name in r["name"]]
    # 검색형 엔드포인트 — 무매칭도 200 + 빈 목록
    return {"recipient_candidates": recipients}


@app.post("/api/transactions/transfer-external", response_model=TransferResponse)
def transfer_external(request: TransferRequest) -> TransferResponse:
    accounts = ledger.ACCOUNTS.get(request.user_id, [])
    account = next(
        (a for a in accounts if a["account_id"] == request.from_account_id), None
    )
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="출금 계좌를 찾을 수 없습니다.",
        )
    recipients = ledger.RECIPIENTS.get(request.user_id, [])
    if not any(r["recipient_id"] == request.to_recipient_id for r in recipients):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="수취인을 찾을 수 없습니다.",
        )
    if account["balance"] < request.amount:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="잔액이 부족합니다.",
        )

    account["balance"] -= request.amount  # Fake Money 원장 차감

    return TransferResponse(
        transaction_id=f"txn_{uuid.uuid4().hex[:8]}", status="completed"
    )


@app.post("/api/audit-logs", response_model=AuditLogResponse)
def post_audit_log(request: AuditLogRequest) -> AuditLogResponse:
    ledger.AUDIT_LOGS.append(request.model_dump())
    return AuditLogResponse(log_id=f"srv_log_{len(ledger.AUDIT_LOGS):04d}")
