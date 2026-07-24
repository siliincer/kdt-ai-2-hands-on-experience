"""계좌 추가 API.

Agent 워크플로우가 아직 없어서, FE 슬래시 명령 `/add_account <은행명>` 이 이 엔드포인트를
직접 호출한다(임시 UX). 은행명 검증·계정계 생성·로컬 매핑은 Backend 가 담당한다.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.postgres import get_db
from ..models.user import User
from ..schemas.account import AccountAddData, AccountAddRequest
from ..schemas.response import CommonResponse
from ..security.jwt import get_current_user
from ..services.financial.provisioning import add_account_for_user
from ..utils.build_response import success_response
from ..utils.masking import mask_account_number

account_router = APIRouter(prefix="/accounts", tags=["Accounts"])


@account_router.post("", response_model=CommonResponse[AccountAddData])
async def add_account(
    payload: AccountAddRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """지정 은행의 부계좌 1개를 추가한다(회원가입 프로비저닝과 같은 기본 설정)."""
    account = await add_account_for_user(session, current_user, payload.bank_name)
    return success_response(
        message=f"{account.bank_name} 계좌 1개가 추가되었습니다.",
        data=AccountAddData(
            account_id=str(account.id),
            bank_name=account.bank_name or payload.bank_name,
            masked_account_number=mask_account_number(account.account_number),
            balance=account.balance,
            currency=account.currency,
        ),
    )
