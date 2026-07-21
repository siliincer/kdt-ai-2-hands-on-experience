"""신규 수취 계좌 검증(FE 전용 API) 테스트 (D5).

repository·세션 검증을 monkeypatch 해 DB 없이 검증 분기와 마스킹을 확인한다.
"""

from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.schemas.recipient_candidate import RecipientCandidateVerifyRequest
from backend.services import recipient_candidate_service

_NO_SESSION = cast(AsyncSession, None)


def _account(user_id=None, active=True, name="홍길동"):
    return SimpleNamespace(
        id=uuid4(),
        user_id=user_id or uuid4(),
        account_number="110-222-123456",
        bank_name="KDT은행",
        active=active,
        user=SimpleNamespace(name=name),
    )


def _req(account_number="110-222-123456", bank_name=None):
    return RecipientCandidateVerifyRequest(
        chat_session_id=uuid4(),
        bank_name=bank_name,
        account_number=account_number,
    )


@pytest.fixture(autouse=True)
def _pass_session_ownership(monkeypatch):
    async def _verify(session, user_id, chat_session_id):
        return None

    monkeypatch.setattr(recipient_candidate_service, "verify_chat_session_owner", _verify)


def _patch_lookup(monkeypatch, account):
    async def _get(session, account_number):
        return account

    monkeypatch.setattr(recipient_candidate_service, "get_account_by_number", _get)


def _patch_create(monkeypatch, box):
    async def _create(session, **kwargs):
        box.update(kwargs)
        return SimpleNamespace(
            id=uuid4(),
            resolved_name=kwargs["resolved_name"],
            bank_name=kwargs["bank_name"],
            masked_account_number=kwargs["masked_account_number"],
            status="verified",
            expires_at=kwargs["expires_at"],
        )

    monkeypatch.setattr(recipient_candidate_service, "create_recipient_candidate", _create)


@pytest.mark.asyncio
async def test_verify_issues_candidate_with_masked_values(monkeypatch):
    account = _account(name="홍길동")
    saved: dict = {}
    _patch_lookup(monkeypatch, account)
    _patch_create(monkeypatch, saved)

    data = await recipient_candidate_service.verify_recipient_candidate(_NO_SESSION, uuid4(), _req())

    assert data.recipient_candidate_id
    assert data.name == "홍*동"  # 예금주명 마스킹
    assert data.masked_account_number == "110-***-123456"
    assert data.status == "verified"
    # 저장에도 원문 계좌번호가 아닌 마스킹본만 들어간다(D5).
    assert saved["masked_account_number"] == "110-***-123456"
    assert saved["recipient_account_id"] == account.id
    assert saved["resolved_name"] == "홍길동"  # 스냅샷은 실명(응답만 마스킹)


@pytest.mark.asyncio
async def test_verify_missing_account_404(monkeypatch):
    _patch_lookup(monkeypatch, None)

    with pytest.raises(HTTPException) as exc:
        await recipient_candidate_service.verify_recipient_candidate(_NO_SESSION, uuid4(), _req())
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_verify_inactive_account_404(monkeypatch):
    _patch_lookup(monkeypatch, _account(active=False))

    with pytest.raises(HTTPException) as exc:
        await recipient_candidate_service.verify_recipient_candidate(_NO_SESSION, uuid4(), _req())
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_verify_bank_mismatch_404(monkeypatch):
    """은행 불일치도 존재 여부를 구분하지 않고 같은 404 를 쓴다(탐색 방지)."""
    _patch_lookup(monkeypatch, _account())

    with pytest.raises(HTTPException) as exc:
        await recipient_candidate_service.verify_recipient_candidate(_NO_SESSION, uuid4(), _req(bank_name="다른은행"))
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_verify_own_account_rejected(monkeypatch):
    """본인 계좌는 타인송금 수취처가 될 수 없다(본인이체 대상)."""
    user_id = uuid4()
    _patch_lookup(monkeypatch, _account(user_id=user_id))

    with pytest.raises(HTTPException) as exc:
        await recipient_candidate_service.verify_recipient_candidate(_NO_SESSION, user_id, _req())
    assert exc.value.status_code == 400


def test_verify_endpoint_requires_user_auth(client):
    response = client.post(
        "/api/v1/recipient-candidates:verify",
        json={
            "chat_session_id": str(uuid4()),
            "account_number": "110-222-123456",
        },
    )
    # Frontend Bearer 인증(HTTPBearer) 미제공 → 403(FastAPI 기본)
    assert response.status_code in (401, 403)
