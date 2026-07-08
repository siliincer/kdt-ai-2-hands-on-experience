from fastapi import APIRouter, Depends

from ..models.user import User
from ..schemas.response import CommonResponse
from ..schemas.ui import BalanceData
from ..security.jwt import get_current_user
from ..services.ui_service import get_balance_view
from ..utils.build_response import success_response

ui_router = APIRouter(prefix="/ui", tags=["UI Data"])


@ui_router.get("/balance", response_model=CommonResponse[BalanceData])
async def read_balance(current_user: User = Depends(get_current_user)):
    """자산 현황 카드 데이터 (component:balance 시그널 후 FE 가 조회, ADR-002)."""
    data = await get_balance_view(current_user.id)
    return success_response(message="자산 현황을 조회했습니다.", data=data)
