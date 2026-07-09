"""UI Data API 비즈니스 로직 (BFF, ADR-002).

FE 가 component 시그널을 받은 뒤 카드 데이터를 조회하는 계층.
현재는 목 픽스처를 반환한다. 향후 정보계(postgres/redis) 및
mock-financial-service(계정계) 조회로 교체한다.
"""

from uuid import UUID

from ..schemas.ui import BalanceData
from .mock.ui_fixtures import BALANCE_FIXTURE


async def get_balance_view(user_id: UUID) -> BalanceData:
    """사용자 자산 현황 view model.

    TODO: mock-financial-service(계정계) 잔액 조회 + 정보계 캐시로 교체.
    """
    # 현재는 유저 무관 목 데이터
    _ = user_id
    return BALANCE_FIXTURE
