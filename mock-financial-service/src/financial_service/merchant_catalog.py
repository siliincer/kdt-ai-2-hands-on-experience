"""가맹점 → 소비 카테고리 매핑의 단일 출처.

실제 은행 시스템엔 없는 개념이지만, mock 장부로 소비 분석을 하려면 카드결제
(CardLedgerEntry)에 카테고리가 필요하다. mock_data.py의 시드 데이터와, 실제로
merchant_name이 채워지는 모든 경로가 같은 매핑을 참조하도록 여기 한 곳에 둔다.

`models.CARD_PRODUCT_CATEGORIES`(카드 *상품* 마케팅 카테고리, 예: "여행 카드")와는
별개 개념 — 라벨이 겹쳐도("외식", "쇼핑", "여행") 재사용하지 않는다.
"""

from __future__ import annotations

MERCHANTS_BY_CATEGORY: dict[str, list[str]] = {
    "외식": [
        "연남동 파스타",
        "김밥천국",
        "교촌치킨",
        "스타벅스",
        "새마을식당",
        "본죽",
    ],
    "마트/편의점": ["이마트", "홈플러스", "롯데마트", "GS25", "CU편의점", "세븐일레븐"],
    "쇼핑": ["쿠팡", "무신사", "29CM", "네이버쇼핑", "올리브영"],
    "여행": ["대한항공", "아고다", "야놀자", "여기어때"],
    "배달": ["배달의민족", "쿠팡이츠", "요기요"],
    "교통": ["티머니", "카카오T", "SRT"],
    "취미/문화": ["교보문고", "다이소", "네이버페이 - 굿즈샵", "스팀"],
}

# 역인덱스 — 모듈 로드 시 1회 계산
MERCHANT_CATEGORY: dict[str, str] = {
    merchant: category
    for category, merchants in MERCHANTS_BY_CATEGORY.items()
    for merchant in merchants
}


def category_for_merchant(merchant_name: str | None) -> str | None:
    """가맹점명으로 소비 카테고리를 조회한다. 카탈로그 밖 이름이거나 None이면 None."""
    if merchant_name is None:
        return None
    return MERCHANT_CATEGORY.get(merchant_name)
