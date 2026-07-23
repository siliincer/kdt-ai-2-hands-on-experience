"""타인송금 Prepare(#6)·Execute(#8) 검증 (계약 14·16장).

수취인 참조 규칙이 핵심:
- to_recipient_id 는 본인의 실행 이력에 등장한 계좌만 허용(임의 계좌 열거 차단)
- to_recipient_candidate_id 는 검증된 미만료 후보만, 사용 후 소비 처리
Execute 는 confirmation_id + auth_context_id(추가 인증 필수)로 직전 재검증을 수행한다.
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
    ExternalTransferPrepareRequest,
    TransferExecuteRequest,
)
from backend.schemas.execution_context import ResolvedExecutionContext
from backend.services.agent_tools import transfer_service

_NO_SESSION = cast(AsyncSession, None)


def _ctx(user_id=None) -> ResolvedExecutionContext:
    return ResolvedExecutionContext(
        execution_context_id=uuid4(),
        user_id=user_id or uuid4(),
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
        currency="KRW",
        active=True,
        external_account_id="ext-1",
        balance=1_000_000,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _candidate(user_id, recipient_account_id, status="verified", expires_in=600):
    return SimpleNamespace(
        id=uuid4(),
        user_id=user_id,
        recipient_account_id=recipient_account_id,
        resolved_name="홍길동",
        bank_name="KDT은행",
        masked_account_number="110-***-123456",
        status=status,
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=expires_in),
    )


def _history(recipient_account_id, name="홍길동"):
    return SimpleNamespace(
        fixed_data={
            "recipient_account_id": str(recipient_account_id),
            "recipient_name": name,
            "amount": 10_000,
        }
    )


@pytest.fixture(autouse=True)
def _silence_audit(monkeypatch):
    async def _record(session, context, **kwargs):
        return None

    monkeypatch.setattr(transfer_service.financial_audit_service, "record", _record)


def _patch_stack(
    monkeypatch,
    *,
    owned,
    any_accounts=None,
    candidate=None,
    history=None,
    balance=1_000_000,
):
    """Prepare 경로 협력 객체 일괄 대체. 반환 dict 로 부수효과를 관찰한다."""
    marks = {"candidate_consumed": False, "fixed_data": None}
    any_accounts = any_accounts or {}

    async def _get_owned(session, user_id, account_id):
        return owned.get(account_id)

    async def _get_any(session, account_id):
        return any_accounts.get(account_id)

    async def _get_candidate(session, candidate_id):
        return candidate

    async def _consume(session, cand):
        marks["candidate_consumed"] = True
        return cand

    async def _get_history(session, user_id):
        return history or []

    async def _read_balance(account):
        return balance

    async def _daily(session, user_id, since):
        return []

    async def _create_pending(session, context, operation, fixed_data, **kwargs):
        assert operation is ConfirmationOperation.EXTERNAL_TRANSFER
        marks["fixed_data"] = fixed_data
        return SimpleNamespace(
            id=uuid4(),
            fixed_data=fixed_data,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=300),
        )

    monkeypatch.setattr(transfer_service, "get_owned_account", _get_owned)
    monkeypatch.setattr(transfer_service, "get_account_by_id", _get_any)
    monkeypatch.setattr(transfer_service, "get_recipient_candidate_by_id", _get_candidate)
    monkeypatch.setattr(transfer_service, "mark_candidate_consumed", _consume)
    monkeypatch.setattr(transfer_service, "get_executed_external_transfers", _get_history)
    monkeypatch.setattr(transfer_service, "read_available_balance", _read_balance)
    monkeypatch.setattr(transfer_service, "get_executed_transfers_since", _daily)
    monkeypatch.setattr(transfer_service.confirmation_service, "create_pending", _create_pending)
    return marks


def _req_candidate(from_acct, candidate, amount=50_000):
    return ExternalTransferPrepareRequest(
        from_account_id=str(from_acct.id),
        to_recipient_candidate_id=str(candidate.id),
        amount=amount,
        currency="KRW",
    )


def _req_recipient(from_acct, recipient_id, amount=50_000):
    return ExternalTransferPrepareRequest(
        from_account_id=str(from_acct.id),
        to_recipient_id=str(recipient_id),
        amount=amount,
        currency="KRW",
    )


# ── 신규 수취인(후보) 경로 ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_prepare_with_candidate_ready_and_warns(monkeypatch):
    ctx = _ctx()
    from_acct = _acct()
    recipient = _acct(account_number="110-222-123456")
    cand = _candidate(ctx.user_id, recipient.id)
    marks = _patch_stack(
        monkeypatch,
        owned={from_acct.id: from_acct},
        any_accounts={recipient.id: recipient},
        candidate=cand,
    )

    data = await transfer_service.prepare_external_transfer(_NO_SESSION, ctx, _req_candidate(from_acct, cand))

    assert data.outcome == "ready_for_confirmation"
    view = data.confirmation_view
    assert view is not None
    # 신규 수취인 위험 표시(계약 14.4).
    assert view.variant == "warning"
    assert view.warning_codes == ["NEW_RECIPIENT"]
    assert view.recipient.name == "홍*동"  # 이름 마스킹
    assert view.recipient.masked_account_number == "110-***-123456"
    # 후보는 1회용 — 소비 처리.
    assert marks["candidate_consumed"] is True
    # fixed_data 는 #5 resolve 의 이력 원천 계약.
    assert marks["fixed_data"]["recipient_account_id"] == str(recipient.id)
    assert marks["fixed_data"]["recipient_name"] == "홍길동"


@pytest.mark.asyncio
async def test_prepare_with_expired_candidate_410(monkeypatch):
    ctx = _ctx()
    from_acct = _acct()
    cand = _candidate(ctx.user_id, uuid4(), expires_in=-1)
    _patch_stack(monkeypatch, owned={from_acct.id: from_acct}, candidate=cand)

    with pytest.raises(AgentToolError) as exc:
        await transfer_service.prepare_external_transfer(_NO_SESSION, ctx, _req_candidate(from_acct, cand))
    assert exc.value.status_code == 410
    assert exc.value.code == "RECIPIENT_CANDIDATE_EXPIRED"


@pytest.mark.asyncio
async def test_prepare_with_consumed_candidate_410(monkeypatch):
    ctx = _ctx()
    from_acct = _acct()
    cand = _candidate(ctx.user_id, uuid4(), status="consumed")
    _patch_stack(monkeypatch, owned={from_acct.id: from_acct}, candidate=cand)

    with pytest.raises(AgentToolError) as exc:
        await transfer_service.prepare_external_transfer(_NO_SESSION, ctx, _req_candidate(from_acct, cand))
    assert exc.value.code == "RECIPIENT_CANDIDATE_EXPIRED"


@pytest.mark.asyncio
async def test_prepare_candidate_lost_consume_race_410(monkeypatch):
    """C6: 조건부 소비에서 진 요청(동시 Prepare 가 방금 소비)은 재검증 유도(410)."""
    ctx = _ctx()
    from_acct = _acct()
    recipient = _acct(account_number="110-222-123456")
    cand = _candidate(ctx.user_id, recipient.id)
    _patch_stack(
        monkeypatch,
        owned={from_acct.id: from_acct},
        any_accounts={recipient.id: recipient},
        candidate=cand,
    )

    # 소비 선점에서 진다(rowcount 0).
    async def _lost(session, candidate):
        return False

    monkeypatch.setattr(transfer_service, "mark_candidate_consumed", _lost)

    with pytest.raises(AgentToolError) as exc:
        await transfer_service.prepare_external_transfer(_NO_SESSION, ctx, _req_candidate(from_acct, cand))
    assert exc.value.status_code == 410
    assert exc.value.code == "RECIPIENT_CANDIDATE_EXPIRED"


@pytest.mark.asyncio
async def test_prepare_with_other_users_candidate_404(monkeypatch):
    ctx = _ctx()
    from_acct = _acct()
    cand = _candidate(uuid4(), uuid4())  # 다른 사용자의 후보
    _patch_stack(monkeypatch, owned={from_acct.id: from_acct}, candidate=cand)

    with pytest.raises(AgentToolError) as exc:
        await transfer_service.prepare_external_transfer(_NO_SESSION, ctx, _req_candidate(from_acct, cand))
    assert exc.value.status_code == 404
    assert exc.value.code == "RECIPIENT_NOT_FOUND"


# ── 기존 수취인(이력) 경로 ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_prepare_with_history_recipient_ready_default(monkeypatch):
    ctx = _ctx()
    from_acct = _acct()
    recipient = _acct(account_number="110-222-123456")
    _patch_stack(
        monkeypatch,
        owned={from_acct.id: from_acct},
        any_accounts={recipient.id: recipient},
        history=[_history(recipient.id)],
    )

    data = await transfer_service.prepare_external_transfer(_NO_SESSION, ctx, _req_recipient(from_acct, recipient.id))

    assert data.outcome == "ready_for_confirmation"
    view = data.confirmation_view
    assert view is not None
    # 기존 수취인은 위험 표시 없음.
    assert view.variant == "default"
    assert view.warning_codes == []


@pytest.mark.asyncio
async def test_prepare_recipient_not_in_history_404(monkeypatch):
    """이력에 없는 계좌 id 는 거부 — 임의 계좌 열거 차단."""
    ctx = _ctx()
    from_acct = _acct()
    stranger = _acct()
    _patch_stack(
        monkeypatch,
        owned={from_acct.id: from_acct},
        any_accounts={stranger.id: stranger},
        history=[],  # 이력 없음
    )

    with pytest.raises(AgentToolError) as exc:
        await transfer_service.prepare_external_transfer(_NO_SESSION, ctx, _req_recipient(from_acct, stranger.id))
    assert exc.value.code == "RECIPIENT_NOT_FOUND"


@pytest.mark.asyncio
async def test_prepare_inactive_recipient_is_correction(monkeypatch):
    ctx = _ctx()
    from_acct = _acct()
    recipient = _acct(active=False)
    _patch_stack(
        monkeypatch,
        owned={from_acct.id: from_acct},
        any_accounts={recipient.id: recipient},
        history=[_history(recipient.id)],
    )

    data = await transfer_service.prepare_external_transfer(_NO_SESSION, ctx, _req_recipient(from_acct, recipient.id))

    assert data.outcome == "correction_required"
    assert data.reason == "recipient_not_verified"
    assert data.correction_view is not None
    assert data.correction_view.allowed_change_targets == ["recipient"]


@pytest.mark.asyncio
async def test_prepare_self_recipient_is_correction(monkeypatch):
    """본인 계좌로의 타인송금은 수취인 재선택 유도(본인이체 Workflow 대상)."""
    ctx = _ctx()
    from_acct = _acct(user_id=ctx.user_id)
    own_other = _acct(user_id=ctx.user_id)
    _patch_stack(
        monkeypatch,
        owned={from_acct.id: from_acct},
        any_accounts={own_other.id: own_other},
        history=[_history(own_other.id)],
    )

    data = await transfer_service.prepare_external_transfer(_NO_SESSION, ctx, _req_recipient(from_acct, own_other.id))

    assert data.outcome == "correction_required"
    assert data.reason == "recipient_not_verified"


@pytest.mark.asyncio
async def test_prepare_insufficient_balance_correction(monkeypatch):
    ctx = _ctx()
    from_acct = _acct()
    recipient = _acct()
    _patch_stack(
        monkeypatch,
        owned={from_acct.id: from_acct},
        any_accounts={recipient.id: recipient},
        history=[_history(recipient.id)],
        balance=10,
    )

    data = await transfer_service.prepare_external_transfer(_NO_SESSION, ctx, _req_recipient(from_acct, recipient.id))

    assert data.outcome == "correction_required"
    assert data.reason == "insufficient_balance"
    assert data.correction_view is not None
    assert data.correction_view.allowed_change_targets == ["from_account", "amount"]


# ── 요청 스키마(XOR) ─────────────────────────────────────────────────────────


def test_request_rejects_both_recipient_refs():
    with pytest.raises(ValidationError):
        ExternalTransferPrepareRequest(
            from_account_id="a",
            to_recipient_id="r",
            to_recipient_candidate_id="c",
            amount=1000,
            currency="KRW",
        )


def test_request_rejects_no_recipient_ref():
    with pytest.raises(ValidationError):
        ExternalTransferPrepareRequest(from_account_id="a", amount=1000, currency="KRW")


# ── #8 Execute ───────────────────────────────────────────────────────────────


def _exec_confirmation(from_acct, recipient, amount=50_000):
    return SimpleNamespace(
        id=uuid4(),
        operation=ConfirmationOperation.EXTERNAL_TRANSFER,
        fixed_data={
            "from_account_id": str(from_acct.id),
            "recipient_account_id": str(recipient.id),
            "recipient_name": "홍길동",
            "amount": amount,
            "fee": 0,
            "currency": "KRW",
        },
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=300),
    )


def _patch_execute_stack(monkeypatch, conf, auth, *, owned, any_accounts, balance):
    marks = {"executed": False, "conf_invalidated": False, "auth_invalidated": False}

    async def _load_conf(session, context, cid, operation):
        assert operation is ConfirmationOperation.EXTERNAL_TRANSFER
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

    async def _get_owned(session, user_id, account_id):
        return owned.get(account_id)

    async def _get_any(session, account_id):
        return any_accounts.get(account_id)

    async def _read_balance(account):
        return balance

    async def _daily(session, user_id, since):
        return []

    monkeypatch.setattr(transfer_service.confirmation_service, "load_for_execute", _load_conf)
    monkeypatch.setattr(transfer_service.auth_context_service, "load_verified", _load_auth)
    monkeypatch.setattr(transfer_service.confirmation_service, "mark_executed", _mark)
    monkeypatch.setattr(transfer_service.confirmation_service, "invalidate", _invalidate_conf)
    monkeypatch.setattr(transfer_service.auth_context_service, "invalidate", _invalidate_auth)
    monkeypatch.setattr(transfer_service, "get_owned_account", _get_owned)
    monkeypatch.setattr(transfer_service, "get_account_by_id", _get_any)
    monkeypatch.setattr(transfer_service, "read_available_balance", _read_balance)
    monkeypatch.setattr(transfer_service, "get_executed_transfers_since", _daily)
    return marks


class _FakeLedger:
    def __init__(self, error=False):
        self.error = error
        self.calls = []

    async def transfer(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise transfer_service.FinancialServiceError("down")
        return {"transfer_id": "txn_ext_123", "status": "success"}


def _exec_req(conf):
    return TransferExecuteRequest(confirmation_id=str(conf.id), auth_context_id=str(uuid4()))


@pytest.mark.asyncio
async def test_execute_external_completed(monkeypatch):
    ctx = _ctx()
    from_acct = _acct(user_id=ctx.user_id)
    recipient = _acct(account_number="110-222-123456")
    conf = _exec_confirmation(from_acct, recipient)
    auth = SimpleNamespace(id=uuid4(), confirmation_id=conf.id)
    marks = _patch_execute_stack(
        monkeypatch,
        conf,
        auth,
        owned={from_acct.id: from_acct},
        any_accounts={recipient.id: recipient},
        balance=1_000_000,
    )
    fake = _FakeLedger()
    monkeypatch.setattr(transfer_service, "get_financial_client", lambda: fake)

    data = await transfer_service.execute_external_transfer(_NO_SESSION, ctx, _exec_req(conf))

    assert data.outcome == "completed"
    assert data.transaction_id == "txn_ext_123"
    assert marks["executed"] is True
    call = fake.calls[0]
    # 계정계 멱등성 키는 confirmation_id 기반 결정적 키(계약 24.2).
    assert call["idempotency_key"] == f"external_transfer_execute:{conf.id}"
    assert call["sender_account_number"] == from_acct.account_number
    assert call["receiver_account_number"] == recipient.account_number
    assert call["amount"] == 50_000


@pytest.mark.asyncio
async def test_execute_external_expired_auth_requires_reauth(monkeypatch):
    """인증만 만료 → 재인증 유도, Confirmation 은 유지(계약 16.5)."""
    ctx = _ctx()
    from_acct = _acct(user_id=ctx.user_id)
    recipient = _acct()
    conf = _exec_confirmation(from_acct, recipient)
    marks = _patch_execute_stack(
        monkeypatch,
        conf,
        None,  # load_verified → None = 만료
        owned={from_acct.id: from_acct},
        any_accounts={recipient.id: recipient},
        balance=1_000_000,
    )

    data = await transfer_service.execute_external_transfer(_NO_SESSION, ctx, _exec_req(conf))

    assert data.outcome == "reauthentication_required"
    assert data.reason == "auth_context_expired"
    assert marks["conf_invalidated"] is False
    assert marks["executed"] is False


@pytest.mark.asyncio
async def test_execute_external_recipient_now_inactive_invalidates(monkeypatch):
    """실행 직전 수취인 비활성 → correction + 승인·인증 재사용 불가(계약 16.4)."""
    ctx = _ctx()
    from_acct = _acct(user_id=ctx.user_id)
    recipient = _acct(active=False)
    conf = _exec_confirmation(from_acct, recipient)
    auth = SimpleNamespace(id=uuid4(), confirmation_id=conf.id)
    marks = _patch_execute_stack(
        monkeypatch,
        conf,
        auth,
        owned={from_acct.id: from_acct},
        any_accounts={recipient.id: recipient},
        balance=1_000_000,
    )

    data = await transfer_service.execute_external_transfer(_NO_SESSION, ctx, _exec_req(conf))

    assert data.outcome == "correction_required"
    assert data.reason == "recipient_not_verified"
    assert marks["conf_invalidated"] is True
    assert marks["auth_invalidated"] is True
    assert marks["executed"] is False


@pytest.mark.asyncio
async def test_execute_external_insufficient_balance_invalidates(monkeypatch):
    ctx = _ctx()
    from_acct = _acct(user_id=ctx.user_id)
    recipient = _acct()
    conf = _exec_confirmation(from_acct, recipient)
    auth = SimpleNamespace(id=uuid4(), confirmation_id=conf.id)
    marks = _patch_execute_stack(
        monkeypatch,
        conf,
        auth,
        owned={from_acct.id: from_acct},
        any_accounts={recipient.id: recipient},
        balance=10,  # 승인 이후 잔액 감소
    )

    data = await transfer_service.execute_external_transfer(_NO_SESSION, ctx, _exec_req(conf))

    assert data.outcome == "correction_required"
    assert data.reason == "insufficient_balance"
    assert marks["conf_invalidated"] is True
    assert marks["auth_invalidated"] is True


@pytest.mark.asyncio
async def test_execute_external_ledger_outage_is_technical_error(monkeypatch):
    ctx = _ctx()
    from_acct = _acct(user_id=ctx.user_id)
    recipient = _acct()
    conf = _exec_confirmation(from_acct, recipient)
    auth = SimpleNamespace(id=uuid4(), confirmation_id=conf.id)
    marks = _patch_execute_stack(
        monkeypatch,
        conf,
        auth,
        owned={from_acct.id: from_acct},
        any_accounts={recipient.id: recipient},
        balance=1_000_000,
    )
    monkeypatch.setattr(transfer_service, "get_financial_client", lambda: _FakeLedger(error=True))

    with pytest.raises(AgentToolError) as exc:
        await transfer_service.execute_external_transfer(_NO_SESSION, ctx, _exec_req(conf))
    assert exc.value.code == "BACKEND_TEMPORARY_ERROR"
    assert exc.value.retryable is True
    assert marks["executed"] is False  # 실행 확정 전 실패


# ── 라우터 게이트 ────────────────────────────────────────────────────────────


def test_external_execute_requires_service_token(client):
    response = client.post(
        "/api/v1/agent-tools/transfers/external",
        json={"confirmation_id": "c", "auth_context_id": "a"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_SERVICE_TOKEN"


def test_external_prepare_requires_service_token(client):
    response = client.post(
        "/api/v1/agent-tools/transfers/external:prepare",
        json={
            "from_account_id": "a",
            "to_recipient_id": "r",
            "amount": 1000,
            "currency": "KRW",
        },
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_SERVICE_TOKEN"
