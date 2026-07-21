"""신규 수취 계좌 검증 API (Frontend 전용, D5 / integration-contract 15.1 D).

- POST /api/v1/recipient-candidates:verify

Agent Tool API 가 아니다 — Frontend Bearer Token(사용자 인증)과 Chat Session 소유권을
검증한다. 계좌번호 원문은 이 API 까지만 도달하고, 이후 흐름(Agent 재개·Prepare)은
`recipient_candidate_id` 참조만 사용한다.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.postgres import get_db
from ..models.user import User
from ..schemas.recipient_candidate import (
    RecipientCandidateVerifyData,
    RecipientCandidateVerifyRequest,
)
from ..schemas.response import CommonResponse
from ..security.jwt import get_current_user
from ..services.recipient_candidate_service import verify_recipient_candidate
from ..utils.build_response import success_response

recipient_candidate_router = APIRouter(tags=["Recipient Candidates"])


@recipient_candidate_router.post(
    "/recipient-candidates:verify",
    response_model=CommonResponse[RecipientCandidateVerifyData],
)
async def verify_recipient_candidate_endpoint(
    payload: RecipientCandidateVerifyRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """계좌번호로 수취 계좌를 검증하고 recipient_candidate_id 를 발급한다."""
    data = await verify_recipient_candidate(session, current_user.id, payload)
    return success_response(message="수취 계좌를 확인했습니다.", data=data)
