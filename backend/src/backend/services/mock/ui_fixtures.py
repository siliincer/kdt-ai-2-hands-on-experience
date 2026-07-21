"""UI Data API 목 픽스처 (mock 분리 원칙, BE_Coding).

TODO(BE): 향후 ui_service 가 실제 데이터 소스 조회로 교체될 때 이 파일을 제거한다.
값은 backend/docs/agent_ui_event_spec.md §4b 스키마와 일치한다.
"""

from ...schemas.ui import (
    AccountDetailData,
    AccountDetailInfo,
    AccountSummary,
    BalanceData,
    BarCatDatum,
    BudgetData,
    BudgetItem,
    CardsData,
    CatTxDatum,
    ChangeItem,
    CreditCard,
    MonthlySpendDatum,
    PieDatum,
    RecentTxItem,
    SpendingData,
    SubscriptionItem,
    TransactionItem,
    TransactionsData,
)

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

ACCOUNT_DETAIL_FIXTURE = AccountDetailData(
    account=AccountDetailInfo(
        bank="신한은행",
        alias="입출금통장",
        tail="4200",
        balance=8_200_000,
    ),
    recent=[
        RecentTxItem(
            name="급여 입금",
            emoji="💰",
            date="06.25 09:00",
            amount=3_200_000,
            type="in",
        ),
        RecentTxItem(
            name="월세 이서연",
            emoji="🏠",
            date="06.01 09:00",
            amount=-550_000,
            type="out",
        ),
        RecentTxItem(
            name="스타벅스",
            emoji="☕",
            date="06.28 14:23",
            amount=-7_500,
            type="out",
        ),
    ],
)

SPENDING_FIXTURE = SpendingData(
    pie=[
        PieDatum(name="식비", value=38, color="#2DD4BF", amount=474_000),
        PieDatum(name="교통비", value=22, color="#3B82F6", amount=274_000),
        PieDatum(name="고정비", value=28, color="#FF0000", amount=349_000),
        PieDatum(name="사치비", value=12, color="#F97316", amount=150_000),
    ],
    bar=[
        BarCatDatum(
            name="식비",
            change=12,
            prev=406_714,
            curr=455_520,
            added=[
                ChangeItem(name="배달의민족", amount=28_500),
                ChangeItem(name="맥도날드 (신규)", amount=12_400),
            ],
            removed=[ChangeItem(name="CU 편의점", amount=8_000)],
        ),
        BarCatDatum(
            name="교통비",
            change=-8,
            prev=278_511,
            curr=256_230,
            added=[],
            removed=[
                ChangeItem(name="택시 이용 감소", amount=15_000),
                ChangeItem(name="주유비 감소", amount=8_000),
            ],
        ),
        BarCatDatum(
            name="고정비",
            change=3,
            prev=483_713,
            curr=498_225,
            added=[ChangeItem(name="삼성화재 보험", amount=15_000)],
            removed=[],
        ),
        BarCatDatum(
            name="사치비",
            change=-22,
            prev=274_007,
            curr=213_525,
            added=[],
            removed=[
                ChangeItem(name="무신사 쇼핑", amount=35_000),
                ChangeItem(name="올리브영 감소", amount=25_000),
            ],
        ),
    ],
    monthly=[
        MonthlySpendDatum(month="1월", amount=1_100_000),
        MonthlySpendDatum(month="2월", amount=980_000),
        MonthlySpendDatum(month="3월", amount=1_350_000),
        MonthlySpendDatum(month="4월", amount=1_420_000),
        MonthlySpendDatum(month="5월", amount=1_120_000),
        MonthlySpendDatum(month="6월", amount=1_247_000),
    ],
    catTx={
        "식비": [
            CatTxDatum(name="스타벅스", date="06.28", amount=7_500),
            CatTxDatum(name="배달의민족", date="06.22", amount=28_500),
            CatTxDatum(name="맥도날드", date="06.15", amount=12_400),
            CatTxDatum(name="GS25", date="06.10", amount=4_200),
        ],
        "교통비": [
            CatTxDatum(name="카카오T 택시", date="06.24", amount=13_200),
            CatTxDatum(name="T-money 충전", date="06.20", amount=30_000),
            CatTxDatum(name="GS칼텍스", date="06.05", amount=65_000),
        ],
        "고정비": [
            CatTxDatum(name="월세", date="06.01", amount=550_000),
            CatTxDatum(name="KT 통신비", date="06.05", amount=55_000),
            CatTxDatum(name="전기·가스", date="06.10", amount=89_000),
        ],
        "사치비": [
            CatTxDatum(name="올리브영", date="06.21", amount=85_000),
            CatTxDatum(name="무신사", date="06.08", amount=79_000),
        ],
    },
)


def _tx(  # noqa: PLR0913 - 픽스처 헬퍼(목 데이터 생성 전용)
    id_: int,
    name: str,
    emoji: str,
    date: str,
    month: str,
    day: int,
    amount: int,
    type_: str,
    category: str,
) -> TransactionItem:
    return TransactionItem(
        id=id_,
        name=name,
        emoji=emoji,
        date=date,
        month=month,
        day=day,
        amount=amount,
        type=type_,
        category=category,
    )


TRANSACTIONS_FIXTURE = TransactionsData(
    months=["2025-06", "2025-05", "2025-04", "2025-03", "2025-02"],
    items=[
        _tx(
            601,
            "급여 입금",
            "💰",
            "06.25 09:00",
            "2025-06",
            25,
            3_200_000,
            "in",
            "수입",
        ),
        _tx(
            602,
            "월세 이서연",
            "🏠",
            "06.01 09:00",
            "2025-06",
            1,
            -550_000,
            "out",
            "고정비",
        ),
        _tx(
            603, "KT 통신비", "📱", "06.05 00:01", "2025-06", 5, -55_000, "out", "기타"
        ),
        _tx(604, "스타벅스", "☕", "06.28 14:23", "2025-06", 28, -7_500, "out", "식비"),
        _tx(
            605,
            "카카오T 택시",
            "🚕",
            "06.24 22:41",
            "2025-06",
            24,
            -13_200,
            "out",
            "교통비",
        ),
        _tx(
            606,
            "쿠팡 로켓배송",
            "📦",
            "06.23 11:05",
            "2025-06",
            23,
            -42_800,
            "out",
            "쇼핑",
        ),
        _tx(
            607, "Spotify", "🎵", "06.15 00:01", "2025-06", 15, -10_900, "out", "고정비"
        ),
        _tx(
            608, "Netflix", "🎬", "06.20 00:01", "2025-06", 20, -17_000, "out", "고정비"
        ),
        _tx(
            609,
            "올리브영",
            "💄",
            "06.21 15:30",
            "2025-06",
            21,
            -85_000,
            "out",
            "사치비",
        ),
        _tx(
            501,
            "급여 입금",
            "💰",
            "05.25 09:00",
            "2025-05",
            25,
            3_200_000,
            "in",
            "수입",
        ),
        _tx(
            502,
            "월세 이서연",
            "🏠",
            "05.01 09:00",
            "2025-05",
            1,
            -550_000,
            "out",
            "고정비",
        ),
        _tx(
            503, "KT 통신비", "📱", "05.05 00:01", "2025-05", 5, -55_000, "out", "기타"
        ),
        _tx(504, "스타벅스", "☕", "05.28 10:00", "2025-05", 28, -7_500, "out", "식비"),
        _tx(
            505, "Spotify", "🎵", "05.15 00:01", "2025-05", 15, -10_900, "out", "고정비"
        ),
        _tx(
            506, "Netflix", "🎬", "05.20 00:01", "2025-05", 20, -17_000, "out", "고정비"
        ),
        _tx(
            507, "무신사", "👗", "05.14 14:00", "2025-05", 14, -79_000, "out", "사치비"
        ),
        _tx(
            401,
            "급여 입금",
            "💰",
            "04.25 09:00",
            "2025-04",
            25,
            3_200_000,
            "in",
            "수입",
        ),
        _tx(
            402,
            "월세 이서연",
            "🏠",
            "04.01 09:00",
            "2025-04",
            1,
            -550_000,
            "out",
            "고정비",
        ),
        _tx(
            403, "KT 통신비", "📱", "04.05 00:01", "2025-04", 5, -55_000, "out", "기타"
        ),
        _tx(404, "스타벅스", "☕", "04.28 09:30", "2025-04", 28, -7_500, "out", "식비"),
        _tx(
            301,
            "급여 입금",
            "💰",
            "03.25 09:00",
            "2025-03",
            25,
            3_200_000,
            "in",
            "수입",
        ),
        _tx(
            302,
            "월세 이서연",
            "🏠",
            "03.01 09:00",
            "2025-03",
            1,
            -550_000,
            "out",
            "고정비",
        ),
        _tx(
            303, "KT 통신비", "📱", "03.05 00:01", "2025-03", 5, -55_000, "out", "기타"
        ),
        _tx(
            201,
            "급여 입금",
            "💰",
            "02.25 09:00",
            "2025-02",
            25,
            3_200_000,
            "in",
            "수입",
        ),
        _tx(
            202,
            "월세 이서연",
            "🏠",
            "02.01 09:00",
            "2025-02",
            1,
            -550_000,
            "out",
            "고정비",
        ),
        _tx(
            203, "KT 통신비", "📱", "02.05 00:01", "2025-02", 5, -55_000, "out", "기타"
        ),
    ],
)

BUDGET_FIXTURE = BudgetData(
    budgetItems=[
        BudgetItem(cat="식비", used=400_000, total=500_000),
        BudgetItem(cat="교통비", used=80_000, total=200_000),
        BudgetItem(cat="쇼핑", used=240_000, total=200_000),
    ],
    subItems=[
        SubscriptionItem(name="Netflix", amount=13_900, active=True),
        SubscriptionItem(name="멜론", amount=10_900, active=False),
        SubscriptionItem(name="Spotify", amount=10_900, active=True),
    ],
)

CARDS_FIXTURE = CardsData(
    cards=[
        CreditCard(
            name="신한 Deep Dream",
            num="5412 3456 7890 1234",
            exp="11/27",
            bg="linear-gradient(135deg,#0F1E3D 0%,#1a3a6b 60%,#2DD4BF 100%)",
        ),
        CreditCard(
            name="카카오 체크카드",
            num="9432 0011 2345 6789",
            exp="03/26",
            bg="linear-gradient(135deg,#FAE100 0%,#F59E0B 100%)",
        ),
    ],
)
