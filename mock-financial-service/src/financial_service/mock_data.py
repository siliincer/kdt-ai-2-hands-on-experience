"""Shared mock dataset — Accounts, Cards, and CardProduct catalog.

5 Accounts, 8 Cards (1-2 per Account, each FK-linked to a real Account).
20 CardProduct rows (4 per each of 5 categories), standalone — no FK to Card.
Fixed UUIDs for determinism across seed/demo/pytest consumers.
"""

from __future__ import annotations

import json

from .models import Account, Card, CardProduct

# ── Accounts ──────────────────────────────────────────────────────────────────
# 5 rows, fixed UUIDs

MOCK_ACCOUNTS: list[dict] = [
    {
        "account_id": "acct-0001-0000-0000-000000000001",
        "owner": "김민준",
        "currency": "KRW",
    },
    {
        "account_id": "acct-0002-0000-0000-000000000002",
        "owner": "이서연",
        "currency": "KRW",
    },
    {
        "account_id": "acct-0003-0000-0000-000000000003",
        "owner": "박지호",
        "currency": "KRW",
    },
    {
        "account_id": "acct-0004-0000-0000-000000000004",
        "owner": "최수아",
        "currency": "KRW",
    },
    {
        "account_id": "acct-0005-0000-0000-000000000005",
        "owner": "정도윤",
        "currency": "KRW",
    },
]

# ── Cards ─────────────────────────────────────────────────────────────────────
# 8 rows total, 1-2 per Account, each FK → MOCK_ACCOUNTS[*].account_id

MOCK_CARDS: list[dict] = [
    # ACC-001: 2 cards
    {
        "card_id": "card-0001-0000-0000-000000000001",
        "account_id": "acct-0001-0000-0000-000000000001",
        "limit": 1_000_000,
        "currency": "KRW",
    },
    {
        "card_id": "card-0002-0000-0000-000000000002",
        "account_id": "acct-0001-0000-0000-000000000001",
        "limit": 500_000,
        "currency": "KRW",
    },
    # ACC-002: 1 card
    {
        "card_id": "card-0003-0000-0000-000000000003",
        "account_id": "acct-0002-0000-0000-000000000002",
        "limit": 2_000_000,
        "currency": "KRW",
    },
    # ACC-003: 2 cards
    {
        "card_id": "card-0004-0000-0000-000000000004",
        "account_id": "acct-0003-0000-0000-000000000003",
        "limit": 1_500_000,
        "currency": "KRW",
    },
    {
        "card_id": "card-0005-0000-0000-000000000005",
        "account_id": "acct-0003-0000-0000-000000000003",
        "limit": 800_000,
        "currency": "KRW",
    },
    # ACC-004: 2 cards
    {
        "card_id": "card-0006-0000-0000-000000000006",
        "account_id": "acct-0004-0000-0000-000000000004",
        "limit": 3_000_000,
        "currency": "KRW",
    },
    {
        "card_id": "card-0007-0000-0000-000000000007",
        "account_id": "acct-0004-0000-0000-000000000004",
        "limit": 1_200_000,
        "currency": "KRW",
    },
    # ACC-005: 1 card
    {
        "card_id": "card-0008-0000-0000-000000000008",
        "account_id": "acct-0005-0000-0000-000000000005",
        "limit": 700_000,
        "currency": "KRW",
    },
]


def make_account_rows() -> list[Account]:
    """Return Account ORM instances (not yet committed)."""
    return [Account(**d) for d in MOCK_ACCOUNTS]


def make_card_rows() -> list[Card]:
    """Return Card ORM instances (not yet committed).

    Accounts must already exist in the session before flushing cards.
    """
    return [Card(**d) for d in MOCK_CARDS]


# ── CardProduct catalog ────────────────────────────────────────────────────────
# 20 rows, 4 per each of 5 categories — standalone, NO FK to Card.
# Categories: 외식 | 쇼핑 | 여행 | 웹구독 | 마트/편의점

MOCK_CARD_PRODUCTS: list[dict] = [
    # ── 외식 (Dining) ──────────────────────────────────────────────────────────
    {
        "card_product_id": "cp-0001-0000-0000-000000000001",
        "product_name": "다이닝 플러스 카드",
        "category": "외식",
        "annual_fee": 30000,
        "benefits": json.dumps(
            [
                "외식 결제 5% 캐시백 (월 최대 10,000원)",
                "레스토랑 예약 우선 제공",
                "생일 월 외식 10% 추가 할인",
            ],
            ensure_ascii=False,
        ),
    },
    {
        "card_product_id": "cp-0001-0000-0000-000000000002",
        "product_name": "푸드러버 배달 카드",
        "category": "외식",
        "annual_fee": 15000,
        "benefits": json.dumps(
            [
                "배달 앱(배민·쿠팡이츠) 10% 할인 (월 최대 5,000원)",
                "배달료 면제 쿠폰 월 2매",
                "편의점 야식 결제 3% 적립",
            ],
            ensure_ascii=False,
        ),
    },
    {
        "card_product_id": "cp-0001-0000-0000-000000000003",
        "product_name": "미식가 골드 카드",
        "category": "외식",
        "annual_fee": 50000,
        "benefits": json.dumps(
            [
                "레스토랑/카페 결제 7% 포인트 적립 (무제한)",
                "미슐랭 가이드 제휴 레스토랑 20% 할인",
                "연간 외식 누적 300만 원 초과 시 5만 포인트 보너스",
            ],
            ensure_ascii=False,
        ),
    },
    {
        "card_product_id": "cp-0001-0000-0000-000000000004",
        "product_name": "카페앤밀 일상 카드",
        "category": "외식",
        "annual_fee": 0,
        "benefits": json.dumps(
            [
                "카페·음식점 결제 3% 캐시백 (월 최대 3,000원)",
                "스타벅스/투썸 제휴 음료 1+1 월 1회",
                "연회비 무료",
            ],
            ensure_ascii=False,
        ),
    },
    # ── 쇼핑 (Shopping) ────────────────────────────────────────────────────────
    {
        "card_product_id": "cp-0002-0000-0000-000000000001",
        "product_name": "쇼핑 마스터 카드",
        "category": "쇼핑",
        "annual_fee": 20000,
        "benefits": json.dumps(
            [
                "온라인 쇼핑 8% 캐시백 (월 최대 8,000원)",
                "쿠팡 로켓배송 무료 쿠폰 월 3매",
                "주요 오픈마켓 추가 5% 할인 쿠폰",
            ],
            ensure_ascii=False,
        ),
    },
    {
        "card_product_id": "cp-0002-0000-0000-000000000002",
        "product_name": "패션 프리미엄 카드",
        "category": "쇼핑",
        "annual_fee": 40000,
        "benefits": json.dumps(
            [
                "백화점 결제 6% 할인 (월 최대 15,000원)",
                "신세계·롯데·현대 백화점 주차 2시간 무료",
                "브랜드 아울렛 입장 우선권",
            ],
            ensure_ascii=False,
        ),
    },
    {
        "card_product_id": "cp-0002-0000-0000-000000000003",
        "product_name": "이커머스 플러스 카드",
        "category": "쇼핑",
        "annual_fee": 10000,
        "benefits": json.dumps(
            [
                "쿠팡/네이버쇼핑/11번가 5% 포인트 적립",
                "무이자 할부 3개월 (월 50만 원 이상 결제 시)",
                "신규 가입 첫 달 온라인 쇼핑 10% 추가 할인",
            ],
            ensure_ascii=False,
        ),
    },
    {
        "card_product_id": "cp-0002-0000-0000-000000000004",
        "product_name": "올인원 쇼핑 카드",
        "category": "쇼핑",
        "annual_fee": 0,
        "benefits": json.dumps(
            [
                "온·오프라인 쇼핑 통합 4% 캐시백 (월 최대 4,000원)",
                "연회비 무료",
                "해외직구 결제 관세 서포트 서비스",
            ],
            ensure_ascii=False,
        ),
    },
    # ── 여행 (Travel) ──────────────────────────────────────────────────────────
    {
        "card_product_id": "cp-0003-0000-0000-000000000001",
        "product_name": "트래블 프리미엄 카드",
        "category": "여행",
        "annual_fee": 100000,
        "benefits": json.dumps(
            [
                "해외 결제 수수료(1.5%) 전액 면제",
                "공항 라운지 무료 이용 연 4회",
                "여행자 보험 자동 가입 (최대 3억 원)",
            ],
            ensure_ascii=False,
        ),
    },
    {
        "card_product_id": "cp-0003-0000-0000-000000000002",
        "product_name": "마일리지 플러스 카드",
        "category": "여행",
        "annual_fee": 80000,
        "benefits": json.dumps(
            [
                "항공권·마일리지 적립 2배 (1,000원당 2마일)",
                "대한항공·아시아나 제휴 마일리지 보너스 연 5,000마일",
                "항공권 취소 수수료 면제 (연 1회)",
            ],
            ensure_ascii=False,
        ),
    },
    {
        "card_product_id": "cp-0003-0000-0000-000000000003",
        "product_name": "호텔 앤 에어 카드",
        "category": "여행",
        "annual_fee": 60000,
        "benefits": json.dumps(
            [
                "호텔 예약 10% 할인 (아고다·부킹닷컴 제휴)",
                "항공권 결제 5% 캐시백 (월 최대 20,000원)",
                "해외 ATM 출금 수수료 면제 월 2회",
            ],
            ensure_ascii=False,
        ),
    },
    {
        "card_product_id": "cp-0003-0000-0000-000000000004",
        "product_name": "글로벌 여행 카드",
        "category": "여행",
        "annual_fee": 30000,
        "benefits": json.dumps(
            [
                "해외 환전 수수료 50% 할인",
                "해외 결제 3% 포인트 적립 (무제한)",
                "국제선 수하물 분실 보험 (최대 100만 원)",
            ],
            ensure_ascii=False,
        ),
    },
    # ── 웹구독 (Web Subscription) ──────────────────────────────────────────────
    {
        "card_product_id": "cp-0004-0000-0000-000000000001",
        "product_name": "디지털 라이프 카드",
        "category": "웹구독",
        "annual_fee": 0,
        "benefits": json.dumps(
            [
                "OTT(넷플릭스·왓챠·티빙) 결제 30% 할인 (월 최대 6,000원)",
                "연회비 무료",
                "디지털 구독 자동갱신 결제 3% 추가 적립",
            ],
            ensure_ascii=False,
        ),
    },
    {
        "card_product_id": "cp-0004-0000-0000-000000000002",
        "product_name": "스트리밍 플러스 카드",
        "category": "웹구독",
        "annual_fee": 5000,
        "benefits": json.dumps(
            [
                "음악 스트리밍(멜론·스포티파이) 20% 캐시백",
                "영상 스트리밍 결제 20% 캐시백 (통합 월 최대 4,000원)",
                "게임 구독(Xbox·PS) 10% 할인",
            ],
            ensure_ascii=False,
        ),
    },
    {
        "card_product_id": "cp-0004-0000-0000-000000000003",
        "product_name": "테크 구독 카드",
        "category": "웹구독",
        "annual_fee": 10000,
        "benefits": json.dumps(
            [
                "클라우드(iCloud·Google One·Dropbox) 15% 할인",
                "앱마켓 구독 결제 10% 포인트 적립",
                "소프트웨어 구독(Adobe·MS365) 5% 캐시백",
            ],
            ensure_ascii=False,
        ),
    },
    {
        "card_product_id": "cp-0004-0000-0000-000000000004",
        "product_name": "메가 구독 카드",
        "category": "웹구독",
        "annual_fee": 0,
        "benefits": json.dumps(
            [
                "모든 온라인 구독 서비스 10% 캐시백 (월 최대 5,000원)",
                "연회비 무료",
                "구독 서비스 관리 앱 무료 제공",
            ],
            ensure_ascii=False,
        ),
    },
    # ── 마트/편의점 (Mart/Convenience) ────────────────────────────────────────
    {
        "card_product_id": "cp-0005-0000-0000-000000000001",
        "product_name": "마트 킹 카드",
        "category": "마트/편의점",
        "annual_fee": 15000,
        "benefits": json.dumps(
            [
                "대형마트(이마트·홈플러스·롯데마트) 7% 캐시백 (월 최대 7,000원)",
                "마트 주차 1시간 무료",
                "신선식품 배송 무료 쿠폰 월 2매",
            ],
            ensure_ascii=False,
        ),
    },
    {
        "card_product_id": "cp-0005-0000-0000-000000000002",
        "product_name": "편의 생활 카드",
        "category": "마트/편의점",
        "annual_fee": 0,
        "benefits": json.dumps(
            [
                "편의점(CU·GS25·세븐일레븐) 10% 할인 (월 최대 3,000원)",
                "연회비 무료",
                "편의점 ATM 출금 수수료 무료",
            ],
            ensure_ascii=False,
        ),
    },
    {
        "card_product_id": "cp-0005-0000-0000-000000000003",
        "product_name": "그로서리 플러스 카드",
        "category": "마트/편의점",
        "annual_fee": 10000,
        "benefits": json.dumps(
            [
                "마트·편의점 통합 5% 포인트 적립 (무제한)",
                "온라인 마트(마켓컬리·SSG) 추가 3% 적립",
                "월 10만 원 이상 결제 시 500포인트 보너스",
            ],
            ensure_ascii=False,
        ),
    },
    {
        "card_product_id": "cp-0005-0000-0000-000000000004",
        "product_name": "홈마켓 온라인 카드",
        "category": "마트/편의점",
        "annual_fee": 20000,
        "benefits": json.dumps(
            [
                "온라인 마트(쿠팡로켓프레시·마켓컬리) 8% 캐시백 (월 최대 8,000원)",
                "새벽배송 무료 쿠폰 월 3매",
                "오프라인 마트 결제 3% 캐시백",
            ],
            ensure_ascii=False,
        ),
    },
]

CARD_PRODUCT_CATEGORIES = ("외식", "쇼핑", "여행", "웹구독", "마트/편의점")


def make_card_product_rows() -> list[CardProduct]:
    """Return CardProduct ORM instances (not yet committed).

    Standalone catalog — no FK to Card or Account.
    20 rows, 4 per each of 5 categories.
    """
    return [CardProduct(**d) for d in MOCK_CARD_PRODUCTS]


# ── Schema validation ──────────────────────────────────────────────────────────

_ACCOUNT_SCHEMA: dict = {
    "account_id": str,
    "owner": str,
    "currency": str,
}

_CARD_SCHEMA: dict = {
    "card_id": str,
    "account_id": str,
    "limit": int,
    "currency": str,
}

_CARD_PRODUCT_SCHEMA: dict = {
    "card_product_id": str,
    "product_name": str,
    "category": str,
    "annual_fee": int,
    "benefits": str,  # JSON-encoded list
}


def _validate_row(row: dict, schema: dict, label: str) -> list[str]:
    """Return list of validation errors for *row* against *schema*."""
    errors: list[str] = []
    for field, expected_type in schema.items():
        if field not in row:
            errors.append(f"{label}[{row}]: missing field '{field}'")
        elif not isinstance(row[field], expected_type):
            errors.append(
                f"{label}: field '{field}' expected {expected_type.__name__}, "
                f"got {type(row[field]).__name__}"
            )
    return errors


def validate_dataset() -> list[str]:
    """Validate all mock data rows against their schemas and referential integrity.

    Returns a (possibly empty) list of error strings.
    Callers should assert ``not validate_dataset()`` to confirm data is clean.
    """
    errors: list[str] = []

    # ── Account rows ──────────────────────────────────────────────────────────
    for i, row in enumerate(MOCK_ACCOUNTS):
        errors.extend(_validate_row(row, _ACCOUNT_SCHEMA, f"Account[{i}]"))

    # non-empty owner/currency
    for i, row in enumerate(MOCK_ACCOUNTS):
        if row.get("owner", "").strip() == "":
            errors.append(f"Account[{i}]: owner is empty")
        if row.get("currency", "").strip() == "":
            errors.append(f"Account[{i}]: currency is empty")

    # unique account_id
    acct_ids = [r["account_id"] for r in MOCK_ACCOUNTS]
    if len(acct_ids) != len(set(acct_ids)):
        errors.append("MOCK_ACCOUNTS: duplicate account_id values found")

    # ── Card rows ─────────────────────────────────────────────────────────────
    valid_account_ids: set[str] = {r["account_id"] for r in MOCK_ACCOUNTS}

    for i, row in enumerate(MOCK_CARDS):
        errors.extend(_validate_row(row, _CARD_SCHEMA, f"Card[{i}]"))

    # FK: every card.account_id must reference a real Account
    for i, row in enumerate(MOCK_CARDS):
        if row.get("account_id") not in valid_account_ids:
            errors.append(
                f"Card[{i}] (card_id={row.get('card_id')}): "
                f"account_id '{row.get('account_id')}' not found in MOCK_ACCOUNTS"
            )

    # card limit must be positive
    for i, row in enumerate(MOCK_CARDS):
        if row.get("limit", 0) <= 0:
            errors.append(f"Card[{i}]: limit must be positive, got {row.get('limit')}")

    # unique card_id
    card_ids = [r["card_id"] for r in MOCK_CARDS]
    if len(card_ids) != len(set(card_ids)):
        errors.append("MOCK_CARDS: duplicate card_id values found")

    # ── CardProduct rows ──────────────────────────────────────────────────────
    for i, row in enumerate(MOCK_CARD_PRODUCTS):
        errors.extend(_validate_row(row, _CARD_PRODUCT_SCHEMA, f"CardProduct[{i}]"))

    # category restricted
    allowed_cats = set(CARD_PRODUCT_CATEGORIES)
    for i, row in enumerate(MOCK_CARD_PRODUCTS):
        cat = row.get("category", "")
        if cat not in allowed_cats:
            errors.append(
                f"CardProduct[{i}]: category '{cat}' not in allowed set {allowed_cats}"
            )

    # benefits must be valid JSON list with >= 1 item
    for i, row in enumerate(MOCK_CARD_PRODUCTS):
        try:
            parsed = json.loads(row.get("benefits", "null"))
        except (json.JSONDecodeError, TypeError):
            errors.append(f"CardProduct[{i}]: benefits is not valid JSON")
            continue
        if not isinstance(parsed, list) or len(parsed) < 1:
            errors.append(f"CardProduct[{i}]: benefits must be a non-empty JSON array")

    # annual_fee non-negative
    for i, row in enumerate(MOCK_CARD_PRODUCTS):
        if row.get("annual_fee", -1) < 0:
            errors.append(f"CardProduct[{i}]: annual_fee must be >= 0")

    # unique card_product_id
    cp_ids = [r["card_product_id"] for r in MOCK_CARD_PRODUCTS]
    if len(cp_ids) != len(set(cp_ids)):
        errors.append("MOCK_CARD_PRODUCTS: duplicate card_product_id values found")

    # ── Count constraints ─────────────────────────────────────────────────────
    if len(MOCK_ACCOUNTS) != 5:
        errors.append(f"Expected 5 Accounts, got {len(MOCK_ACCOUNTS)}")

    if not (5 <= len(MOCK_CARDS) <= 10):
        errors.append(f"Expected 5-10 Cards, got {len(MOCK_CARDS)}")

    if len(MOCK_CARD_PRODUCTS) != 20:
        errors.append(f"Expected 20 CardProducts, got {len(MOCK_CARD_PRODUCTS)}")

    # cards-per-account: 1–2 each
    from collections import Counter as _Counter

    cards_per_acct = _Counter(r["account_id"] for r in MOCK_CARDS)
    for acct_id in valid_account_ids:
        n = cards_per_acct.get(acct_id, 0)
        if not (1 <= n <= 2):
            errors.append(
                f"Account {acct_id} has {n} cards; expected 1-2"
            )

    # 4 per category
    cat_counts = _Counter(r["category"] for r in MOCK_CARD_PRODUCTS)
    for cat in CARD_PRODUCT_CATEGORIES:
        if cat_counts.get(cat, 0) != 4:
            errors.append(
                f"Category '{cat}' has {cat_counts.get(cat, 0)} products; expected 4"
            )

    return errors
