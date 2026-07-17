"""추가 인증 Context 생명주기(계약 15·16·18장).

    Prepare/승인 완료 → create_for_confirmation (PENDING)
    Frontend 인증     → Backend 가 검증 후 mark_verified (Stage 7 에서 연결)
    Execute 직전      → load_verified 로 재검증

Agent 에는 인증 Assertion·PIN·생체 결과 원문을 절대 반환하지 않는다(계약 15.4).
Agent 는 인증 상태를 폴링하지 않고, Backend 가 검증한 재개 값으로만 Execute 로 이동한다.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ..core.agent_exceptions import AgentToolError
from ..models.auth_context import AuthContext, AuthContextStatus
from ..models.confirmation import Confirmation
from ..repository.auth_context_repository import (
    create_auth_context,
    get_active_auth_context,
    get_auth_context_by_id,
    set_auth_context_status,
)
from ..schemas.execution_context import ResolvedExecutionContext
from .agent_tools.policy_constants import (
    AUTH_AVAILABLE_METHODS,
    AUTH_CONTEXT_TTL_SECONDS,
)


async def create_for_confirmation(
    session: AsyncSession,
    context: ResolvedExecutionContext,
    confirmation: Confirmation,
) -> AuthContext:
    """승인된 Confirmation 에 대한 인증 시도를 준비한다.

    같은 Confirmation 에 아직 살아있는 인증 시도가 있으면 중복 생성하지 않고 그대로
    재사용한다(계약 15.4). 인증 실패·만료 후에는 활성 건이 없으므로 새로 만들어진다.
    """
    now = datetime.now(timezone.utc)
    existing = await get_active_auth_context(session, confirmation.id, now)
    if existing is not None:
        return existing

    return await create_auth_context(
        session,
        confirmation_id=confirmation.id,
        user_id=context.user_id,
        available_methods=list(AUTH_AVAILABLE_METHODS),
        expires_at=now + timedelta(seconds=AUTH_CONTEXT_TTL_SECONDS),
    )


def _parse_id(raw: str) -> UUID:
    try:
        return UUID(raw)
    except (ValueError, AttributeError) as exc:
        # 존재 여부를 노출하지 않고 인증 재요청으로 유도한다.
        raise AgentToolError.auth_required() from exc


async def load_verified(
    session: AsyncSession,
    context: ResolvedExecutionContext,
    auth_context_id: str,
    confirmation: Confirmation,
) -> AuthContext | None:
    """Execute 직전 인증 재검증.

    반환값 의미:
    - `AuthContext`: 검증된 유효한 인증 → Execute 진행
    - `None`: **만료됨** → 호출부는 `reauthentication_required`(200) 로 응답해야 한다
      (Confirmation 은 유효하므로 Agent 가 새 Auth Context 만 만들면 된다, 계약 16.5).

    미존재·다른 사용자·다른 Confirmation·미검증(PENDING/FAILED/CANCELLED)은
    `AUTH_REQUIRED`(409) 로 던진다.
    """
    auth_context = await get_auth_context_by_id(session, _parse_id(auth_context_id))
    if auth_context is None:
        raise AgentToolError.auth_required()
    if auth_context.user_id != context.user_id:
        raise AgentToolError.auth_required()
    if auth_context.confirmation_id != confirmation.id:
        raise AgentToolError.auth_required()

    # 만료는 오류가 아니라 재인증 사유다(Confirmation 은 그대로 유효).
    if auth_context.status is AuthContextStatus.EXPIRED:
        return None
    if auth_context.expires_at <= datetime.now(timezone.utc):
        return None

    if auth_context.status is not AuthContextStatus.VERIFIED:
        raise AgentToolError.auth_required()
    return auth_context


async def mark_verified(
    session: AsyncSession, auth_context: AuthContext
) -> AuthContext:
    """Frontend 인증 결과가 검증되면 호출한다(Backend 가 검증한 뒤에만)."""
    return await set_auth_context_status(
        session,
        auth_context,
        AuthContextStatus.VERIFIED,
        verified_at=datetime.now(timezone.utc),
    )


async def invalidate(session: AsyncSession, auth_context: AuthContext) -> AuthContext:
    """실행 조건이 바뀌어 기존 인증을 재사용할 수 없게 처리한다(계약 16.4)."""
    return await set_auth_context_status(
        session, auth_context, AuthContextStatus.EXPIRED
    )
