"""기본 출금 계좌·계좌 별칭 변경 검증 (#11~#14, 계약 19~22장).

repository/Confirmation/Audit 를 monkeypatch 해 DB 없이 outcome 분기를 검증한다.
업무 판정은 예외가 아니라 outcome 으로 나와야 한다(D2').
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.agent_exceptions import AgentToolError
from backend.models.confirmation import ConfirmationOperation
from backend.schemas.agent_tools.setting import (
    AccountAliasPrepareRequest,
    DefaultAccountPrepareRequest,
    ExecuteByConfirmationRequest,
)
from backend.schemas.execution_context import ResolvedExecutionContext
from backend.services.agent_tools import setting_service

_NO_SESSION = cast(AsyncSession, None)


def _ctx() -> ResolvedExecutionContext:
    return ResolvedExecutionContext(
        execution_context_id=uuid4(),
        user_id=uuid4(),
        chat_session_id=uuid4(),
        agent_thread_id="thread_1",
        scopes=["settings:write"],
        timezone="Asia/Seoul",
    )


def _acct(**overrides):
    base = dict(
        id=uuid4(),
        user_id=uuid4(),
        account_number="3333-12-1234567",
        bank_name="카카오뱅크",
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


def _confirmation(fixed_data, operation=ConfirmationOperation.DEFAULT_ACCOUNT_CHANGE):
    return SimpleNamespace(
        id=uuid4(),
        operation=operation,
        fixed_data=fixed_data,
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=300),
    )


@pytest.fixture(autouse=True)
def _silence_audit(monkeypatch):
    async def _record(session, context, **kwargs):
        return None

    monkeypatch.setattr(setting_service.financial_audit_service, "record", _record)


def _patch_owned(monkeypatch, account):
    async def _get(session, user_id, account_id):
        return account

    monkeypatch.setattr(setting_service, "get_owned_account", _get)


def _patch_confirmation_create(monkeypatch, confirmation):
    async def _create(session, context, operation, fixed_data, **kwargs):
        return confirmation

    monkeypatch.setattr(setting_service.confirmation_service, "create_pending", _create)


# ── #11 기본계좌 Prepare ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_prepare_default_ready_for_confirmation(monkeypatch):
    ctx = _ctx()
    target = _acct(is_default=False, alias="급여")
    current = _acct(is_default=True, alias="생활비 통장")
    _patch_owned(monkeypatch, target)

    async def _get_default(session, user_id):
        return current

    monkeypatch.setattr(setting_service, "get_default_account", _get_default)
    _patch_confirmation_create(
        monkeypatch, _confirmation({"account_id": str(target.id)})
    )

    data = await setting_service.prepare_default_account(
        _NO_SESSION, ctx, DefaultAccountPrepareRequest(account_id=str(target.id))
    )

    assert data.outcome == "ready_for_confirmation"
    assert data.confirmation_id
    view = data.confirmation_view
    assert view is not None
    assert view.new_default_account.account_id == str(target.id)
    assert view.current_default_account is not None
    assert view.current_default_account.account_alias == "생활비 통장"
    # 전체 계좌번호는 노출하지 않는다.
    assert view.new_default_account.masked_account_number == "3333-**-1234567"


@pytest.mark.asyncio
async def test_prepare_default_already_default_is_unchanged(monkeypatch):
    account = _acct(is_default=True)
    _patch_owned(monkeypatch, account)

    data = await setting_service.prepare_default_account(
        _NO_SESSION, _ctx(), DefaultAccountPrepareRequest(account_id=str(account.id))
    )

    assert data.outcome == "unchanged"
    assert data.account_id == str(account.id)
    assert data.confirmation_id is None  # Confirmation 미생성


@pytest.mark.asyncio
async def test_prepare_default_inactive_is_correction(monkeypatch):
    account = _acct(active=False)
    _patch_owned(monkeypatch, account)

    data = await setting_service.prepare_default_account(
        _NO_SESSION, _ctx(), DefaultAccountPrepareRequest(account_id=str(account.id))
    )

    assert data.outcome == "correction_required"
    assert data.reason == "account_not_eligible"
    assert data.correction_view is not None
    assert data.correction_view.allowed_change_targets == ["account"]


@pytest.mark.asyncio
async def test_prepare_default_unowned_denied(monkeypatch):
    _patch_owned(monkeypatch, None)

    with pytest.raises(AgentToolError) as exc:
        await setting_service.prepare_default_account(
            _NO_SESSION, _ctx(), DefaultAccountPrepareRequest(account_id=str(uuid4()))
        )
    assert exc.value.code == "ACCOUNT_ACCESS_DENIED"


# ── #12 기본계좌 Execute ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_execute_default_completed(monkeypatch):
    ctx = _ctx()
    account = _acct()
    conf = _confirmation({"account_id": str(account.id)})
    applied = {}

    async def _load(session, context, cid, operation):
        assert operation is ConfirmationOperation.DEFAULT_ACCOUNT_CHANGE
        return conf

    async def _set_default(session, user_id, acct):
        applied["account_id"] = acct.id
        return acct

    async def _mark(session, confirmation):
        applied["executed"] = True
        return confirmation

    monkeypatch.setattr(setting_service.confirmation_service, "load_for_execute", _load)
    _patch_owned(monkeypatch, account)
    monkeypatch.setattr(setting_service, "set_default_account", _set_default)
    monkeypatch.setattr(setting_service.confirmation_service, "mark_executed", _mark)

    data = await setting_service.execute_default_account(
        _NO_SESSION, ctx, ExecuteByConfirmationRequest(confirmation_id=str(conf.id))
    )

    assert data.outcome == "completed"
    assert data.account_id == str(account.id)
    assert data.completed_at is not None
    assert applied["account_id"] == account.id
    assert applied["executed"] is True


@pytest.mark.asyncio
async def test_execute_default_inactive_invalidates_confirmation(monkeypatch):
    account = _acct(active=False)
    conf = _confirmation({"account_id": str(account.id)})
    invalidated = {}

    async def _load(session, context, cid, operation):
        return conf

    async def _invalidate(session, confirmation):
        invalidated["done"] = True
        return confirmation

    monkeypatch.setattr(setting_service.confirmation_service, "load_for_execute", _load)
    monkeypatch.setattr(setting_service.confirmation_service, "invalidate", _invalidate)
    _patch_owned(monkeypatch, account)

    data = await setting_service.execute_default_account(
        _NO_SESSION, _ctx(), ExecuteByConfirmationRequest(confirmation_id=str(conf.id))
    )

    assert data.outcome == "correction_required"
    assert data.reason == "account_not_eligible"
    assert invalidated["done"] is True  # 기존 Confirmation 재사용 불가 처리


# ── #13 별칭 Prepare ─────────────────────────────────────────────────────────


def _patch_alias_dup(monkeypatch, exists: bool):
    async def _exists(session, user_id, alias, exclude_account_id):
        return exists

    monkeypatch.setattr(setting_service, "alias_exists_for_user", _exists)


@pytest.mark.asyncio
async def test_prepare_alias_ready(monkeypatch):
    account = _acct(alias="생활비 통장")
    _patch_owned(monkeypatch, account)
    _patch_alias_dup(monkeypatch, False)
    _patch_confirmation_create(
        monkeypatch,
        _confirmation(
            {"account_id": str(account.id), "alias": "여행 자금"},
            ConfirmationOperation.ACCOUNT_ALIAS_CHANGE,
        ),
    )

    data = await setting_service.prepare_account_alias(
        _NO_SESSION,
        _ctx(),
        AccountAliasPrepareRequest(account_id=str(account.id), alias="  여행   자금 "),
    )

    assert data.outcome == "ready_for_confirmation"
    assert data.confirmation_view is not None
    assert data.confirmation_view.alias == "여행 자금"  # 정규화됨
    # 계약 21.4: 별칭 화면의 계좌 정보에는 기존 별칭을 담지 않는다.
    assert not hasattr(data.confirmation_view.account, "account_alias")


@pytest.mark.asyncio
async def test_prepare_alias_same_is_unchanged(monkeypatch):
    account = _acct(alias="여행 자금")
    _patch_owned(monkeypatch, account)
    _patch_alias_dup(monkeypatch, False)

    data = await setting_service.prepare_account_alias(
        _NO_SESSION,
        _ctx(),
        AccountAliasPrepareRequest(account_id=str(account.id), alias="여행  자금"),
    )

    assert data.outcome == "unchanged"
    assert data.alias == "여행 자금"
    assert data.confirmation_id is None


@pytest.mark.asyncio
async def test_prepare_alias_too_long_is_correction(monkeypatch):
    account = _acct()
    _patch_owned(monkeypatch, account)
    _patch_alias_dup(monkeypatch, False)

    data = await setting_service.prepare_account_alias(
        _NO_SESSION,
        _ctx(),
        AccountAliasPrepareRequest(account_id=str(account.id), alias="가" * 50),
    )

    assert data.outcome == "correction_required"
    assert data.reason == "alias_not_allowed"
    assert data.correction_view is not None
    assert data.correction_view.allowed_change_targets == ["alias"]


@pytest.mark.asyncio
async def test_prepare_alias_forbidden_word_is_correction(monkeypatch):
    account = _acct()
    _patch_owned(monkeypatch, account)
    _patch_alias_dup(monkeypatch, False)

    data = await setting_service.prepare_account_alias(
        _NO_SESSION,
        _ctx(),
        AccountAliasPrepareRequest(account_id=str(account.id), alias="관리자 계좌"),
    )

    assert data.outcome == "correction_required"
    assert data.reason == "alias_not_allowed"


@pytest.mark.asyncio
async def test_prepare_alias_duplicate_is_correction(monkeypatch):
    account = _acct()
    _patch_owned(monkeypatch, account)
    _patch_alias_dup(monkeypatch, True)  # 다른 계좌가 이미 사용

    data = await setting_service.prepare_account_alias(
        _NO_SESSION,
        _ctx(),
        AccountAliasPrepareRequest(account_id=str(account.id), alias="비상금"),
    )

    assert data.outcome == "correction_required"
    assert data.reason == "alias_not_allowed"


# ── #14 별칭 Execute ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_execute_alias_completed(monkeypatch):
    account = _acct(alias="생활비 통장")
    conf = _confirmation(
        {"account_id": str(account.id), "alias": "여행 자금"},
        ConfirmationOperation.ACCOUNT_ALIAS_CHANGE,
    )
    applied = {}

    async def _load(session, context, cid, operation):
        assert operation is ConfirmationOperation.ACCOUNT_ALIAS_CHANGE
        return conf

    async def _set_alias(session, acct, alias):
        applied["alias"] = alias
        return acct

    async def _mark(session, confirmation):
        applied["executed"] = True
        return confirmation

    monkeypatch.setattr(setting_service.confirmation_service, "load_for_execute", _load)
    _patch_owned(monkeypatch, account)
    _patch_alias_dup(monkeypatch, False)
    monkeypatch.setattr(setting_service, "set_account_alias", _set_alias)
    monkeypatch.setattr(setting_service.confirmation_service, "mark_executed", _mark)

    data = await setting_service.execute_account_alias(
        _NO_SESSION, _ctx(), ExecuteByConfirmationRequest(confirmation_id=str(conf.id))
    )

    assert data.outcome == "completed"
    assert data.alias == "여행 자금"
    assert data.account_id == str(account.id)
    # Confirmation 에 고정된 별칭을 반영한다(요청 본문에 별칭이 없음).
    assert applied["alias"] == "여행 자금"
    assert applied["executed"] is True


@pytest.mark.asyncio
async def test_execute_alias_now_duplicated_invalidates(monkeypatch):
    account = _acct()
    conf = _confirmation(
        {"account_id": str(account.id), "alias": "비상금"},
        ConfirmationOperation.ACCOUNT_ALIAS_CHANGE,
    )
    invalidated = {}

    async def _load(session, context, cid, operation):
        return conf

    async def _invalidate(session, confirmation):
        invalidated["done"] = True
        return confirmation

    monkeypatch.setattr(setting_service.confirmation_service, "load_for_execute", _load)
    monkeypatch.setattr(setting_service.confirmation_service, "invalidate", _invalidate)
    _patch_owned(monkeypatch, account)
    _patch_alias_dup(monkeypatch, True)  # 승인 이후 다른 계좌가 선점

    data = await setting_service.execute_account_alias(
        _NO_SESSION, _ctx(), ExecuteByConfirmationRequest(confirmation_id=str(conf.id))
    )

    assert data.outcome == "correction_required"
    assert data.reason == "alias_not_allowed"
    assert invalidated["done"] is True


# ── 라우터: 인증 + Idempotency-Key 게이트 ────────────────────────────────────


@pytest.mark.parametrize(
    "path,body",
    [
        ("/api/v1/agent-tools/settings/default-account:prepare", {"account_id": "a"}),
        (
            "/api/v1/agent-tools/settings/default-account",
            {"confirmation_id": "c"},
        ),
        (
            "/api/v1/agent-tools/settings/account-alias:prepare",
            {"account_id": "a", "alias": "여행"},
        ),
        ("/api/v1/agent-tools/settings/account-alias", {"confirmation_id": "c"}),
    ],
)
def test_setting_endpoints_require_service_token(client, path, body):
    response = client.post(path, json=body)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_SERVICE_TOKEN"
