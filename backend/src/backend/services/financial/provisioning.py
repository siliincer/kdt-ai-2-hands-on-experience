"""회원가입 시 계정계 계좌 프로비저닝 (Phase 2, 결정 A/D).

계정계 장애/에러는 삼켜서(best-effort) 회원가입이 계정계 outage 로 실패하지 않게
한다(결정 D). 실패 시 매핑 없이 진행하며, 이후 balance/transactions 는 빈 상태로
흡수된다. (mock 일원화, 작업 B: 항상 계정계 http 로 프로비저닝한다.)
"""

import logging
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from ...models.user import User
from ...repository.account_repository import (
    create_mapped_account,
    has_mapped_account,
)
from .constants import _SIGNUP_SEED_BALANCE
from .financial_client import FinancialServiceError, get_financial_client

logger = logging.getLogger(__name__)


async def provision_account_for_user(session: AsyncSession, user: User) -> str | None:
    """신규 유저에게 계정계 계좌를 붙인다. 성공 시 external_account_id, 아니면 None.

    - 이미 매핑됨: 멱등적으로 건너뜀(None).
    - 계정계 장애: 삼키고 None(회원가입은 계속, 결정 D).
    """
    if await has_mapped_account(session, user.id):
        return None

    owner = (user.name or user.email or "user").strip()
    try:
        created = await get_financial_client().create_account(owner=owner, initial_balance=_SIGNUP_SEED_BALANCE)
    except FinancialServiceError:
        # 결정 D: 계정계 outage 가 회원가입을 깨지 않는다. 매핑은 나중에 보강.
        logger.warning("account provisioning skipped: financial service unavailable")
        return None

    external_id = created["account_id"]
    # 계정계가 부여한 실제 계좌번호/은행명 저장(송금·balance 뷰에서 재사용).
    # 응답에 없으면(구버전 계정계) 로컬 임시번호로 대체.
    account_number = created.get("account_number") or f"MFS{uuid4().hex[:12].upper()}"
    await create_mapped_account(
        session,
        user_id=user.id,
        external_account_id=external_id,
        account_number=account_number,
        bank_name=created.get("bank_name"),
        balance=created.get("balance", 0),
        currency=created.get("currency", "KRW"),
    )
    return external_id
