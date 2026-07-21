"""신규 수취 계좌 검증 비즈니스 로직 (Frontend 전용, D5).

계정계에는 계좌번호 조회 API 가 없어(D4: 미변경) 동일은행 타 owner(D6) = 다른 로컬
사용자의 `accounts` 행을 계좌번호로 조회해 검증한다. 예금주명 = `User.name`.
TODO(계정계): 계좌번호 기반 계좌·예금주 조회 API 가 생기면 계정계 검증으로 위임한다.

검증 성공 시 사용자·Chat Session·만료시간에 묶인 후보를 발급하고, 원문 계좌번호는
응답·저장 모두에서 제외한다(마스킹본만 보관).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..repository.account_repository import get_account_by_number
from ..repository.recipient_candidate_repository import create_recipient_candidate
from ..schemas.recipient_candidate import (
    RecipientCandidateVerifyData,
    RecipientCandidateVerifyRequest,
)
from ..utils.masking import mask_account_number, mask_person_name
from .agent_tools.bank_resolver import resolve_owned_account_bank
from .agent_tools.policy_constants import RECIPIENT_CANDIDATE_TTL_SECONDS
from .chat_session_service import verify_chat_session_owner

_NOT_FOUND_MESSAGE = "수취 계좌를 확인할 수 없습니다."


async def verify_recipient_candidate(
    session: AsyncSession,
    user_id: UUID,
    req: RecipientCandidateVerifyRequest,
) -> RecipientCandidateVerifyData:
    """계좌번호로 수취 계좌를 검증하고 단기 후보 참조를 발급한다.

    실패 응답은 계좌 존재 여부를 구분하지 않는다(타 사용자 계좌 탐색 방지):
    미존재·비활성·은행 불일치 모두 같은 404 메시지를 쓴다.
    """
    await verify_chat_session_owner(session, user_id, req.chat_session_id)

    account = await get_account_by_number(session, req.account_number.strip())
    if account is None or not account.active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND_MESSAGE
        )
    if req.bank_name and account.bank_name and req.bank_name != account.bank_name:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND_MESSAGE
        )
    # 본인 계좌는 타인송금 수취처가 아니다(본인이체 Workflow 대상).
    if account.user_id == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="본인 계좌로는 타인송금을 할 수 없습니다.",
        )

    resolved_name = (account.user.name if account.user else None) or "예금주"
    expires_at = datetime.now(timezone.utc) + timedelta(
        seconds=RECIPIENT_CANDIDATE_TTL_SECONDS
    )
    candidate = await create_recipient_candidate(
        session,
        user_id=user_id,
        chat_session_id=req.chat_session_id,
        recipient_account_id=account.id,
        resolved_name=resolved_name,
        bank_name=resolve_owned_account_bank(account),
        masked_account_number=mask_account_number(account.account_number),
        expires_at=expires_at,
    )
    return RecipientCandidateVerifyData(
        recipient_candidate_id=str(candidate.id),
        name=mask_person_name(candidate.resolved_name),
        bank_name=candidate.bank_name,
        masked_account_number=candidate.masked_account_number,
        status=candidate.status,
        expires_at=candidate.expires_at,
    )
