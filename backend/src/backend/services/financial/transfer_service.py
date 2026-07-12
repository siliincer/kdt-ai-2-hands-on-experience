"""계정계 송금 실행 (Phase 2, 결정 C/D).

읽기=정보계, 쓰기=계정계(POST /transfers). 승인(HITL) 이후 실제로 원장을 움직인다.
이 서비스는 재사용 가능한 인프라다 — 현재는 mock_agent_driver 가 호출하고,
실제 Agent 연동 후에는 Agent 웹훅 경로가 같은 함수를 호출하면 된다.

장애 격리(결정 D): http 모드가 아니거나 매핑/수취계좌가 없거나 계정계 장애면
None 을 반환한다. 호출부는 None 을 "실제 이체 미실행"으로 취급하고 챗 UX 를 이어간다.
"""

import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ...core.load_environment_var import settings
from ...repository.account_repository import get_primary_mapped_account
from .financial_client import FinancialServiceError, get_financial_client

logger = logging.getLogger(__name__)


def _use_http() -> bool:
    return settings.FINANCIAL_CLIENT.strip().lower() == "http"


async def execute_external_transfer(
    session: AsyncSession,
    user_id: UUID,
    amount: int,
    idempotency_key: str,
) -> dict | None:
    """user 의 매핑 계좌에서 데모 수취처로 송금. 성공 시 계정계 응답, 아니면 None.

    sender = user 첫 매핑 계좌의 account_number, receiver = 데모 은행명+계좌번호 설정
    (계정계 신 계약: 계좌번호+은행명 기반). idempotency_key = 승인당 고정값.
    """
    if not _use_http():
        return None

    sender = await get_primary_mapped_account(session, user_id)
    # TODO: 이건 모킹이고, 데모 수취처(은행명+계좌번호)로 이체를
    # 실제 계좌 확인으로 수행할 것, agent를 위한 api 제공?
    receiver_bank = settings.FINANCIAL_DEMO_RECEIVER_BANK_NAME.strip()
    receiver_number = settings.FINANCIAL_DEMO_RECEIVER_ACCOUNT_NUMBER.strip()
    if sender is None or not sender.account_number:
        return None
    if not receiver_bank or not receiver_number:
        return None
    if sender.account_number == receiver_number:  # SELF_TRANSFER 방지(422 회피)
        return None

    try:
        return await get_financial_client().transfer(
            sender_account_number=sender.account_number,
            receiver_bank_name=receiver_bank,
            receiver_account_number=receiver_number,
            amount=amount,
            idempotency_key=idempotency_key,
        )
    except FinancialServiceError:
        # 결정 D: 계정계 장애/거절(잔액부족 등)이 챗 흐름을 깨지 않는다.
        logger.warning("external transfer skipped: financial service error")
        return None
