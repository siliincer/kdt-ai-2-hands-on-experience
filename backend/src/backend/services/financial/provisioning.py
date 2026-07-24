"""회원가입 시 계정계 계좌 프로비저닝 (Phase 2, 결정 A/D).

계정계 장애/에러는 삼켜서(best-effort) 회원가입이 계정계 outage 로 실패하지 않게
한다(결정 D). 실패 시 매핑 없이 진행하며, 이후 balance/transactions 는 빈 상태로
흡수된다. (mock 일원화, 작업 B: 항상 계정계 http 로 프로비저닝한다.)
"""

import logging
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.account import Account
from ...models.user import User
from ...repository.account_repository import (
    create_mapped_account,
    has_mapped_account,
)
from .constants import _SIGNUP_SEED_BALANCE, SUPPORTED_BANK_NAMES
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


def normalize_bank_name(raw: str) -> str:
    """입력 은행명을 지원 목록의 정식 표기로 정규화한다. 미지원이면 400.

    공백·대소문자 차이를 흡수한다(예: "kdt은행" → "KDT은행").
    """
    text = (raw or "").replace(" ", "")
    for bank in SUPPORTED_BANK_NAMES:
        if text.casefold() == bank.replace(" ", "").casefold():
            return bank
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"지원하지 않는 은행이에요. 사용 가능: {', '.join(SUPPORTED_BANK_NAMES)}",
    )


async def add_account_for_user(session: AsyncSession, user: User, bank_name: str) -> Account:
    """사용자에게 지정 은행의 부계좌를 1개 추가한다(회원가입 프로비저닝과 같은 기본값).

    은행명은 지원 목록으로 정규화하고, 계정계에 계좌를 만든 뒤 로컬 Account 로 매핑한다.
    계정계 장애는 여기서는 삼키지 않는다 — 사용자가 명시적으로 요청한 동작이라 실패를 알려야 한다.
    """
    resolved_bank = normalize_bank_name(bank_name)
    owner = (user.name or user.email or "user").strip()
    try:
        created = await get_financial_client().create_account(
            owner=owner,
            initial_balance=_SIGNUP_SEED_BALANCE,
            bank_name=resolved_bank,
        )
    except FinancialServiceError as exc:
        logger.warning("account add failed: financial service error")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="계좌 추가에 실패하였습니다. 나중에 다시 시도해주세요.",
        ) from exc

    account_number = created.get("account_number") or f"MFS{uuid4().hex[:12].upper()}"
    return await create_mapped_account(
        session,
        user_id=user.id,
        external_account_id=created["account_id"],
        account_number=account_number,
        # 계정계가 돌려준 값을 우선하되, 없으면 요청 은행명을 쓴다(양쪽 표기 일치).
        bank_name=created.get("bank_name") or resolved_bank,
        balance=created.get("balance", 0),
        currency=created.get("currency", "KRW"),
    )
