"""수취인 자동 확정 검증 (#5, 계약 13장 / D5).

이력 원천 = 실행 완료된 타인송금 Confirmation 의 fixed_data. repository 를
monkeypatch 해 DB 없이 자동 확정 규칙(정확 일치·중복 제거·비활성 제외)을 검증한다.
"""

from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.schemas.agent_tools.recipient import RecipientResolveRequest
from backend.schemas.execution_context import ResolvedExecutionContext
from backend.services.agent_tools import recipient_service

_NO_SESSION = cast(AsyncSession, None)


def _ctx() -> ResolvedExecutionContext:
    return ResolvedExecutionContext(
        execution_context_id=uuid4(),
        user_id=uuid4(),
        chat_session_id=uuid4(),
        agent_thread_id="thread_1",
        scopes=["transfer:request"],
        timezone="Asia/Seoul",
    )


def _executed(recipient_account_id, recipient_name):
    """실행 완료된 타인송금 Confirmation 의 최소 형태."""
    return SimpleNamespace(
        fixed_data={
            "recipient_account_id": str(recipient_account_id),
            "recipient_name": recipient_name,
            "amount": 50_000,
        }
    )


def _patch_history(monkeypatch, confirmations):
    async def _get(session, user_id):
        return confirmations

    monkeypatch.setattr(recipient_service, "get_executed_external_transfers", _get)


def _patch_accounts(monkeypatch, accounts_by_id):
    async def _get(session, account_id):
        return accounts_by_id.get(str(account_id))

    monkeypatch.setattr(recipient_service, "get_account_by_id", _get)


def _active_account(account_id, active=True):
    return SimpleNamespace(id=account_id, active=active)


def _req(hint="홍길동"):
    return RecipientResolveRequest(recipient_name_hint=hint)


@pytest.mark.asyncio
async def test_single_match_resolves(monkeypatch):
    rcp = uuid4()
    _patch_history(monkeypatch, [_executed(rcp, "홍길동")])
    _patch_accounts(monkeypatch, {str(rcp): _active_account(rcp)})

    data = await recipient_service.resolve_recipient(_NO_SESSION, _ctx(), _req())

    assert data.outcome == "resolved"
    assert data.to_recipient_id == str(rcp)
    assert data.selection_reason is None


@pytest.mark.asyncio
async def test_name_is_normalized_before_match(monkeypatch):
    """공백·대소문자 차이는 정확 일치로 취급한다(정규화 후 비교)."""
    rcp = uuid4()
    _patch_history(monkeypatch, [_executed(rcp, "홍 길동")])
    _patch_accounts(monkeypatch, {str(rcp): _active_account(rcp)})

    data = await recipient_service.resolve_recipient(
        _NO_SESSION, _ctx(), _req("홍길동 ")
    )

    assert data.outcome == "resolved"


@pytest.mark.asyncio
async def test_repeat_transfers_to_same_recipient_dedup(monkeypatch):
    """동일 수취 계좌 반복 거래는 하나로 중복 제거 → resolved(계약 13.5)."""
    rcp = uuid4()
    _patch_history(
        monkeypatch,
        [_executed(rcp, "홍길동"), _executed(rcp, "홍길동"), _executed(rcp, "홍길동")],
    )
    _patch_accounts(monkeypatch, {str(rcp): _active_account(rcp)})

    data = await recipient_service.resolve_recipient(_NO_SESSION, _ctx(), _req())

    assert data.outcome == "resolved"
    assert data.to_recipient_id == str(rcp)


@pytest.mark.asyncio
async def test_multiple_distinct_recipients_require_selection(monkeypatch):
    """동명이인(다른 계좌) 2명 → selection_required / multiple_matches."""
    rcp1, rcp2 = uuid4(), uuid4()
    _patch_history(monkeypatch, [_executed(rcp1, "홍길동"), _executed(rcp2, "홍길동")])
    _patch_accounts(
        monkeypatch,
        {str(rcp1): _active_account(rcp1), str(rcp2): _active_account(rcp2)},
    )

    data = await recipient_service.resolve_recipient(_NO_SESSION, _ctx(), _req())

    assert data.outcome == "selection_required"
    assert data.selection_reason == "multiple_matches"
    assert data.to_recipient_id is None


@pytest.mark.asyncio
async def test_no_history_match_requires_selection(monkeypatch):
    _patch_history(monkeypatch, [_executed(uuid4(), "김철수")])
    _patch_accounts(monkeypatch, {})

    data = await recipient_service.resolve_recipient(_NO_SESSION, _ctx(), _req())

    assert data.outcome == "selection_required"
    assert data.selection_reason == "no_match"


@pytest.mark.asyncio
async def test_partial_match_is_not_resolved(monkeypatch):
    """부분 일치는 자동 확정하지 않는다(계약 13.5)."""
    rcp = uuid4()
    _patch_history(monkeypatch, [_executed(rcp, "홍길동수")])
    _patch_accounts(monkeypatch, {str(rcp): _active_account(rcp)})

    data = await recipient_service.resolve_recipient(_NO_SESSION, _ctx(), _req())

    assert data.outcome == "selection_required"
    assert data.selection_reason == "no_match"


@pytest.mark.asyncio
async def test_inactive_recipient_excluded(monkeypatch):
    """사용할 수 없는 수취인(비활성·소실)은 제외 → no_match."""
    rcp_inactive, rcp_missing = uuid4(), uuid4()
    _patch_history(
        monkeypatch,
        [_executed(rcp_inactive, "홍길동"), _executed(rcp_missing, "홍길동")],
    )
    _patch_accounts(
        monkeypatch, {str(rcp_inactive): _active_account(rcp_inactive, active=False)}
    )

    data = await recipient_service.resolve_recipient(_NO_SESSION, _ctx(), _req())

    assert data.outcome == "selection_required"
    assert data.selection_reason == "no_match"


@pytest.mark.asyncio
async def test_exclusion_leaves_exactly_one_resolves(monkeypatch):
    """2건 일치 중 1건이 비활성으로 제외되어 1건 남으면 resolved."""
    rcp_ok, rcp_bad = uuid4(), uuid4()
    _patch_history(
        monkeypatch, [_executed(rcp_ok, "홍길동"), _executed(rcp_bad, "홍길동")]
    )
    _patch_accounts(
        monkeypatch,
        {
            str(rcp_ok): _active_account(rcp_ok),
            str(rcp_bad): _active_account(rcp_bad, active=False),
        },
    )

    data = await recipient_service.resolve_recipient(_NO_SESSION, _ctx(), _req())

    assert data.outcome == "resolved"
    assert data.to_recipient_id == str(rcp_ok)


# ── 요청 스키마 ──────────────────────────────────────────────────────────────


def test_request_rejects_blank_hint():
    with pytest.raises(ValidationError):
        RecipientResolveRequest(recipient_name_hint="   ")


def test_request_rejects_over_100_chars():
    with pytest.raises(ValidationError):
        RecipientResolveRequest(recipient_name_hint="가" * 101)


# ── 라우터 게이트 ────────────────────────────────────────────────────────────


def test_resolve_endpoint_requires_service_token(client):
    response = client.post(
        "/api/v1/agent-tools/recipients:resolve",
        json={"recipient_name_hint": "홍길동"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_SERVICE_TOKEN"
