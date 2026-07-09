"""UI Data API 목 픽스처 (mock 분리 원칙, BE_Coding).

TODO: 향후 ui_service 가 실제 데이터 소스 조회로 교체될 때 이 파일을 제거한다.
값은 backend/docs/agent_ui_event_spec.md §4b 스키마와 일치한다.
"""

from ...schemas.ui import AccountSummary, BalanceData

BALANCE_FIXTURE = BalanceData(
    total=12_850_000,
    accounts=[
        AccountSummary(
            id=1,
            bank="신한은행",
            alias="입출금통장",
            tail="4200",
            balance=8_200_000,
            color="#0052A3",
        ),
        AccountSummary(
            id=2,
            bank="카카오뱅크",
            alias="세이프박스",
            tail="1234",
            balance=4_650_000,
            color="#FAE100",
        ),
    ],
)
