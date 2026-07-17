"""본인 계좌 간 이체 검증 (#9·#10, 계약 17~18장).

repository·Confirmation·인증·계정계 클라이언트를 monkeypatch 해 DB·네트워크 없이
outcome 분기와 실행 경계를 검증한다. 업무 판정은 outcome, 기술 오류만 예외(D2').
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.agent_exceptions import AgentToolError
from backend.models.confirmation import ConfirmationOperation
from backend.schemas.agent_tools.transfer import (
    InternalTransferPrepareRequest,
    TransferExecuteRequest,
)
from backend.schemas.execution_context import ResolvedExecutionContext
from backend.services.agent_tools import transfer_service
from backend.services.financial import FinancialServiceError

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


def _acct(**overrides):
    base = dict(
        id=uuid4(),
        user_id=uuid4(),
        account_number="3333-12-1234567",
        bank_name="KDT은행",
        alias="생활비 통장",
        account_type="checking",
        currency="KRW",
        is_default=False,
        active=True,
        external_account_id="ext-1",
        balance=1_000_000,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _confirmation(fixed_data):
    return SimpleNamespace(
        id=uuid4(),
        operation=ConfirmationOperation.INTERNAL_TRANSFER,
        fixed_data=fixed_data,
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=300),
    )


def _auth(confirmation_id):
    return SimpleNamespace(id=uuid4(), confirmation_id=confirmation_id)


@pytest.fixture(autouse=True)
def _silence_audit(monkeypatch):
    async def _record(session, context, **kwargs):
        return None

    monkeypatch.setattr(transfer_service.financial_audit_service, "record", _record)


def _patch_owned(monkeypatch, accounts_by_id):
    async def _get(session, user_id, account_id):
        return accounts_by_id.get(account_id)

    monkeypatch.setattr(transfer_service, "get_owned_account", _get)


def _patch_balance(monkeypatch, amount):
    async def _read(account):
        return amount

    monkeypatch.setattr(transfer_service, "read_available_balance", _read)


def _patch_daily(monkeypatch, executed_confirmations):
    async def _get(session, user_id, since):
        return executed_confirmations

    monkeypatch.setattr(transfer_service, "get_executed_transfers_since", _get)


def _patch_confirmation_create(monkeypatch, confirmation):
    async def _create(session, context, operation, fixed_data, **kwargs):
        assert operation is ConfirmationOperation.INTERNAL_TRANSFER
        confirmation.fixed_data = fixed_data
        return confirmation

    monkeypatch.setattr(
        transfer_service.confirmation_service, "create_pending", _create
    )


def _prepare_req(from_account, to_account, amount=50_000):
    return InternalTransferPrepareRequest(
        from_account_id=str(from_account.id),
        to_account_id=str(to_account.id),
        amount=amount,
        currency="KRW",
    )


# ── #9 Prepare ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_prepare_ready_fixes_conditions(monkeypatch):
    ctx = _ctx()
    from_acct = _acct(alias="생활비")
    to_acct = _acct(alias="저축", account_number="3333-99-7654321")
    conf = _confirmation({})
    _patch_owned(monkeypatch, {from_acct.id: from_acct, to_acct.id: to_acct})
    _patch_balance(monkeypatch, 1_000_000)
    _patch_daily(monkeypatch, [])
    _patch_confirmation_create(monkeypatch, conf)

    data = await transfer_service.prepare_internal_transfer(
        _NO_SESSION, ctx, _prepare_req(from_acct, to_acct, amount=100_000)
    )

    assert data.outcome == "ready_for_confirmation"
    assert data.confirmation_id == str(conf.id)
    # Prepare 가 계좌·금액·수수료를 Confirmation 에 고정한다(계약 17.6).
    assert conf.fixed_data == {
        "from_account_id": str(from_acct.id),
        "to_account_id": str(to_acct.id),
        "amount": 100_000,
        "fee": 0,
        "currency": "KRW",
    }
    view = data.confirmation_view
    assert view is not None
    assert view.total_debit == 100_000  # fee=0
    assert view.from_account.masked_account_number == "3333-**-1234567"
    assert view.to_account.masked_account_number == "3333-**-7654321"


@pytest.mark.asyncio
async def test_prepare_same_account_is_correction(monkeypatch):
    ctx = _ctx()
    acct = _acct()
    _patch_owned(monkeypatch, {acct.id: acct})
    _patch_balance(monkeypatch, 1_000_000)
    _patch_daily(monkeypatch, [])

    data = await transfer_service.prepare_internal_transfer(
        _NO_SESSION, ctx, _prepare_req(acct, acct)
    )

    assert data.outcome == "correction_required"
    assert data.reason == "same_account"
    assert data.correction_view is not None
    assert data.correction_view.allowed_change_targets == ["to_account"]


@pytest.mark.asyncio
async def test_prepare_inactive_from_account(monkeypatch):
    ctx = _ctx()
    from_acct = _acct(active=False)
    to_acct = _acct()
    _patch_owned(monkeypatch, {from_acct.id: from_acct, to_acct.id: to_acct})
    _patch_balance(monkeypatch, 1_000_000)
    _patch_daily(monkeypatch, [])

    data = await transfer_service.prepare_internal_transfer(
        _NO_SESSION, ctx, _prepare_req(from_acct, to_acct)
    )

    assert data.outcome == "correction_required"
    assert data.reason == "account_inactive"
    assert data.correction_view is not None
    assert data.correction_view.allowed_change_targets == ["from_account"]


@pytest.mark.asyncio
async def test_prepare_single_limit_exceeded(monkeypatch):
    ctx = _ctx()
    from_acct = _acct()
    to_acct = _acct()
    _patch_owned(monkeypatch, {from_acct.id: from_acct, to_acct.id: to_acct})
    _patch_balance(monkeypatch, 100_000_000)
    _patch_daily(monkeypatch, [])

    data = await transfer_service.prepare_internal_transfer(
        _NO_SESSION, ctx, _prepare_req(from_acct, to_acct, amount=5_000_001)
    )

    assert data.outcome == "correction_required"
    assert data.reason == "limit_exceeded"
    assert data.correction_view is not None
    assert data.correction_view.allowed_change_targets == ["amount"]


@pytest.mark.asyncio
async def test_prepare_insufficient_balance(monkeypatch):
    ctx = _ctx()
    from_acct = _acct()
    to_acct = _acct()
    _patch_owned(monkeypatch, {from_acct.id: from_acct, to_acct.id: to_acct})
    _patch_balance(monkeypatch, 10_000)  # 요청 5만원보다 적음
    _patch_daily(monkeypatch, [])

    data = await transfer_service.prepare_internal_transfer(
        _NO_SESSION, ctx, _prepare_req(from_acct, to_acct, amount=50_000)
    )

    assert data.outcome == "correction_required"
    assert data.reason == "insufficient_balance"
    assert data.correction_view is not None
    assert data.correction_view.allowed_change_targets == ["from_account", "amount"]


@pytest.mark.asyncio
async def test_prepare_daily_limit_uses_executed_confirmations(monkeypatch):
    """일일 한도는 EXECUTED Confirmation 의 fixed_data.amount 합산으로 판정한다."""
    ctx = _ctx()
    from_acct = _acct()
    to_acct = _acct()
    _patch_owned(monkeypatch, {from_acct.id: from_acct, to_acct.id: to_acct})
    _patch_balance(monkeypatch, 100_000_000)
    # 오늘 이미 950만원 실행됨 → 100만원 추가 시 1000만원 한도 초과
    _patch_daily(
        monkeypatch,
        [SimpleNamespace(fixed_data={"amount": 9_500_000})],
    )

    data = await transfer_service.prepare_internal_transfer(
        _NO_SESSION, ctx, _prepare_req(from_acct, to_acct, amount=1_000_000)
    )

    assert data.outcome == "correction_required"
    assert data.reason == "limit_exceeded"


@pytest.mark.asyncio
async def test_prepare_unowned_account_denied(monkeypatch):
    ctx = _ctx()
    from_acct = _acct()
    _patch_owned(monkeypatch, {from_acct.id: from_acct})  # to 계좌는 소유 아님

    with pytest.raises(AgentToolError) as exc:
        await transfer_service.prepare_internal_transfer(
            _NO_SESSION, ctx, _prepare_req(from_acct, _acct())
        )
    assert exc.value.code == "ACCOUNT_ACCESS_DENIED"


# ── 요청 스키마 ──────────────────────────────────────────────────────────────


def test_prepare_request_rejects_zero_amount():
    with pytest.raises(ValidationError):
        InternalTransferPrepareRequest(
            from_account_id="a", to_account_id="b", amount=0, currency="KRW"
        )


def test_prepare_request_rejects_non_krw():
    with pytest.raises(ValidationError):
        InternalTransferPrepareRequest.model_validate(
            {
                "from_account_id": "a",
                "to_account_id": "b",
                "amount": 1000,
                "currency": "USD",
            }
        )


# ── #10 Execute ──────────────────────────────────────────────────────────────


def _fixed(from_acct, to_acct, amount=50_000):
    return {
        "from_account_id": str(from_acct.id),
        "to_account_id": str(to_acct.id),
        "amount": amount,
        "fee": 0,
        "currency": "KRW",
    }


def _patch_execute_stack(
    monkeypatch,
    conf,
    auth,
    accounts_by_id,
    balance=1_000_000,
    daily=None,
):
    """Execute 경로의 협력 객체를 일괄 대체한다."""
    marks = {"executed": False, "conf_invalidated": False, "auth_invalidated": False}

    async def _load_conf(session, context, cid, operation):
        assert operation is ConfirmationOperation.INTERNAL_TRANSFER
        return conf

    async def _load_auth(session, context, aid, confirmation):
        return auth

    async def _mark(session, confirmation):
        marks["executed"] = True
        return confirmation

    async def _invalidate_conf(session, confirmation):
        marks["conf_invalidated"] = True
        return confirmation

    async def _invalidate_auth(session, auth_context):
        marks["auth_invalidated"] = True
        return auth_context

    monkeypatch.setattr(
        transfer_service.confirmation_service, "load_for_execute", _load_conf
    )
    monkeypatch.setattr(
        transfer_service.auth_context_service, "load_verified", _load_auth
    )
    monkeypatch.setattr(transfer_service.confirmation_service, "mark_executed", _mark)
    monkeypatch.setattr(
        transfer_service.confirmation_service, "invalidate", _invalidate_conf
    )
    monkeypatch.setattr(
        transfer_service.auth_context_service, "invalidate", _invalidate_auth
    )
    _patch_owned(monkeypatch, accounts_by_id)
    _patch_balance(monkeypatch, balance)
    _patch_daily(monkeypatch, daily or [])
    return marks


class _FakeLedger:
    def __init__(self, error=False):
        self.error = error
        self.calls = []

    async def transfer(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise FinancialServiceError("down")
        return {"transfer_id": "txn_123", "status": "success"}


def _exec_req(conf, auth):
    return TransferExecuteRequest(
        confirmation_id=str(conf.id), auth_context_id=str(auth.id)
    )


@pytest.mark.asyncio
async def test_execute_completed_moves_ledger(monkeypatch):
    ctx = _ctx()
    from_acct = _acct()
    to_acct = _acct(account_number="3333-99-7654321")
    conf = _confirmation(_fixed(from_acct, to_acct))
    auth = _auth(conf.id)
    marks = _patch_execute_stack(
        monkeypatch, conf, auth, {from_acct.id: from_acct, to_acct.id: to_acct}
    )
    fake = _FakeLedger()
    monkeypatch.setattr(transfer_service, "is_financial_http_mode", lambda: True)
    monkeypatch.setattr(transfer_service, "get_financial_client", lambda: fake)

    data = await transfer_service.execute_internal_transfer(
        _NO_SESSION, ctx, _exec_req(conf, auth)
    )

    assert data.outcome == "completed"
    assert data.transaction_id == "txn_123"
    assert data.completed_at is not None
    assert marks["executed"] is True
    # 계정계에는 confirmation_id 기반 결정적 멱등성 키를 보낸다(계약 24.2).
    call = fake.calls[0]
    assert call["idempotency_key"] == f"internal_transfer_execute:{conf.id}"
    assert call["sender_account_number"] == from_acct.account_number
    assert call["receiver_account_number"] == to_acct.account_number
    assert call["receiver_bank_name"] == "KDT은행"
    assert call["amount"] == 50_000


@pytest.mark.asyncio
async def test_execute_expired_auth_requires_reauth(monkeypatch):
    """인증만 만료 → reauthentication_required. Confirmation 은 살려 둔다(계약 18.5)."""
    ctx = _ctx()
    from_acct = _acct()
    to_acct = _acct()
    conf = _confirmation(_fixed(from_acct, to_acct))
    marks = _patch_execute_stack(
        monkeypatch,
        conf,
        None,  # load_verified 가 None 반환 = 만료
        {from_acct.id: from_acct, to_acct.id: to_acct},
    )

    data = await transfer_service.execute_internal_transfer(
        _NO_SESSION, ctx, _exec_req(conf, _auth(conf.id))
    )

    assert data.outcome == "reauthentication_required"
    assert data.reason == "auth_context_expired"
    assert marks["conf_invalidated"] is False  # Confirmation 유지
    assert marks["executed"] is False


@pytest.mark.asyncio
async def test_execute_revalidation_failure_invalidates_both(monkeypatch):
    """실행 직전 잔액 부족 → correction + Confirmation·인증 재사용 불가(계약 18.4)."""
    ctx = _ctx()
    from_acct = _acct()
    to_acct = _acct()
    conf = _confirmation(_fixed(from_acct, to_acct))
    auth = _auth(conf.id)
    marks = _patch_execute_stack(
        monkeypatch,
        conf,
        auth,
        {from_acct.id: from_acct, to_acct.id: to_acct},
        balance=10,  # 승인 이후 잔액이 줄어든 상황
    )

    data = await transfer_service.execute_internal_transfer(
        _NO_SESSION, ctx, _exec_req(conf, auth)
    )

    assert data.outcome == "correction_required"
    assert data.reason == "insufficient_balance"
    assert marks["conf_invalidated"] is True
    assert marks["auth_invalidated"] is True
    assert marks["executed"] is False


@pytest.mark.asyncio
async def test_execute_missing_account_invalidates(monkeypatch):
    ctx = _ctx()
    from_acct = _acct()
    to_acct = _acct()
    conf = _confirmation(_fixed(from_acct, to_acct))
    auth = _auth(conf.id)
    marks = _patch_execute_stack(
        monkeypatch,
        conf,
        auth,
        {from_acct.id: from_acct},  # to 계좌 소실
    )

    data = await transfer_service.execute_internal_transfer(
        _NO_SESSION, ctx, _exec_req(conf, auth)
    )

    assert data.outcome == "correction_required"
    assert data.reason == "account_inactive"
    assert marks["conf_invalidated"] is True
    assert marks["auth_invalidated"] is True


@pytest.mark.asyncio
async def test_execute_ledger_outage_is_technical_error(monkeypatch):
    """계정계 장애는 업무 outcome 이 아니라 기술 오류(재시도 가능)다(계약 17.6)."""
    ctx = _ctx()
    from_acct = _acct()
    to_acct = _acct()
    conf = _confirmation(_fixed(from_acct, to_acct))
    auth = _auth(conf.id)
    marks = _patch_execute_stack(
        monkeypatch, conf, auth, {from_acct.id: from_acct, to_acct.id: to_acct}
    )
    monkeypatch.setattr(transfer_service, "is_financial_http_mode", lambda: True)
    monkeypatch.setattr(
        transfer_service, "get_financial_client", lambda: _FakeLedger(error=True)
    )

    with pytest.raises(AgentToolError) as exc:
        await transfer_service.execute_internal_transfer(
            _NO_SESSION, ctx, _exec_req(conf, auth)
        )
    assert exc.value.code == "BACKEND_TEMPORARY_ERROR"
    assert exc.value.retryable is True
    # 실행 확정 전 실패 — Confirmation 은 EXECUTED 로 전이되지 않는다.
    assert marks["executed"] is False


@pytest.mark.asyncio
async def test_execute_mock_mode_is_technical_error(monkeypatch):
    """mock 모드는 원장이 없어 이체를 시뮬레이션하지 않는다(거짓 completed 방지)."""
    ctx = _ctx()
    from_acct = _acct()
    to_acct = _acct()
    conf = _confirmation(_fixed(from_acct, to_acct))
    auth = _auth(conf.id)
    _patch_execute_stack(
        monkeypatch, conf, auth, {from_acct.id: from_acct, to_acct.id: to_acct}
    )
    monkeypatch.setattr(transfer_service, "is_financial_http_mode", lambda: False)

    with pytest.raises(AgentToolError) as exc:
        await transfer_service.execute_internal_transfer(
            _NO_SESSION, ctx, _exec_req(conf, auth)
        )
    assert exc.value.code == "BACKEND_TEMPORARY_ERROR"


# ── 라우터 게이트 ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "path,body",
    [
        (
            "/api/v1/agent-tools/transfers/internal:prepare",
            {
                "from_account_id": "a",
                "to_account_id": "b",
                "amount": 1000,
                "currency": "KRW",
            },
        ),
        (
            "/api/v1/agent-tools/transfers/internal",
            {"confirmation_id": "c", "auth_context_id": "d"},
        ),
    ],
)
def test_transfer_endpoints_require_service_token(client, path, body):
    response = client.post(path, json=body)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_SERVICE_TOKEN"
