"""Shared mock dataset — Accounts, Cards, CardProduct catalog, and 4 months of
persona-driven transaction history.

5 Accounts, 8 Cards (1-2 per Account, each FK-linked to a real Account).
20 CardProduct rows (4 per each of 5 categories), standalone — no FK to Card.
7 biller Accounts + 1 external-source Account (payroll/peer-transfer origin).
~100 Transactions / ~200 LedgerEntries / ~400 CardLedgerEntries spanning
2026-03-10 ~ 2026-07-10, driven by 3 consumption personas (see
RealFinance_소비페르소나.md) and generated deterministically by
_build_transaction_dataset() — no OS/wall-clock randomness, so re-running
this module always yields identical mock data.
"""

from __future__ import annotations

import json
import random
from datetime import date, datetime, timezone

from .models import (
    Account,
    Card,
    CardLedgerEntry,
    CardProduct,
    LedgerEntry,
    Transaction,
)

# ── Accounts ──────────────────────────────────────────────────────────────────
# 5 rows, fixed UUIDs

MOCK_ACCOUNTS: list[dict] = [
    {
        "account_id": "acct-0001-0000-0000-000000000001",
        "owner": "김지훈",
        "alias": "김지훈 생활비통장",
        "account_number": "110-001-000001",
        "currency": "KRW",
    },
    {
        "account_id": "acct-0002-0000-0000-000000000002",
        "owner": "박서연",
        "alias": "박서연 메인통장",
        "account_number": "110-002-000002",
        "currency": "KRW",
    },
    {
        "account_id": "acct-0003-0000-0000-000000000003",
        "owner": "이도윤",
        "alias": "이도윤 프리랜서통장",
        "account_number": "110-003-000003",
        "currency": "KRW",
    },
    {
        "account_id": "acct-0004-0000-0000-000000000004",
        "owner": "최수아",
        "alias": "최수아 통장",
        "account_number": "110-004-000004",
        "currency": "KRW",
    },
    {
        "account_id": "acct-0005-0000-0000-000000000005",
        "owner": "정도윤",
        "alias": "정도윤 통장",
        "account_number": "110-005-000005",
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
    """Return Account ORM instances (not yet committed).

    balance is injected from MOCK_FINAL_BALANCES (computed by
    _build_transaction_dataset()) so every row satisfies the canonical
    Account.balance invariant on creation, not just default=0.
    """
    return [
        Account(**d, balance=MOCK_FINAL_BALANCES.get(d["account_id"], 0))
        for d in MOCK_ACCOUNTS
    ]


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


# ── Biller Accounts ────────────────────────────────────────────────────────────
# Receiver accounts for general payments (통신비/헬스장/학원비/관리비).
# Kept DISTINCT from user-owned MOCK_ACCOUNTS (acct-0001..0005).
# Fixed UUIDs — prefix acct-b to avoid collision with user accounts.

MOCK_BILLER_ACCOUNTS: list[dict] = [
    {
        "account_id": "acct-b001-0000-0000-000000000001",
        "owner": "통신사",
        "alias": "통신비·구독료 자동납부",
        "account_number": "990-001-000001",
        "currency": "KRW",
    },
    {
        "account_id": "acct-b002-0000-0000-000000000002",
        "owner": "헬스장",
        "alias": "헬스장 회비",
        "account_number": "990-002-000002",
        "currency": "KRW",
    },
    {
        "account_id": "acct-b003-0000-0000-000000000003",
        "owner": "학원",
        "alias": "자녀 학원비",
        "account_number": "990-003-000003",
        "currency": "KRW",
    },
    {
        "account_id": "acct-b004-0000-0000-000000000004",
        "owner": "관리사무소",
        "alias": "월세·관리비",
        "account_number": "990-004-000004",
        "currency": "KRW",
    },
    {
        "account_id": "acct-b005-0000-0000-000000000005",
        "owner": "저축은행",
        "alias": "저축 이체",
        "account_number": "990-005-000005",
        "currency": "KRW",
    },
    {
        "account_id": "acct-b006-0000-0000-000000000006",
        "owner": "증권사",
        "alias": "투자 자동이체",
        "account_number": "990-006-000006",
        "currency": "KRW",
    },
    {
        "account_id": "acct-b007-0000-0000-000000000007",
        "owner": "대출은행",
        "alias": "대출이자",
        "account_number": "990-007-000007",
        "currency": "KRW",
    },
]

# Convenience lookup: biller name → account_id
BILLER_ACCOUNT_ID: dict[str, str] = {
    row["owner"]: row["account_id"] for row in MOCK_BILLER_ACCOUNTS
}


def make_biller_account_rows() -> list[Account]:
    """Return biller Account ORM instances (not yet committed).

    balance is injected from MOCK_FINAL_BALANCES so billers reflect the
    total they actually received (canonical Account.balance invariant).

    These are payment-receiver accounts for general payments (통신비, 헬스장,
    학원비, 관리비).  They are distinct from user-owned MOCK_ACCOUNTS so that
    existing card-service tests that assert exactly 5 user accounts are unaffected.
    """
    return [
        Account(**d, balance=MOCK_FINAL_BALANCES.get(d["account_id"], 0))
        for d in MOCK_BILLER_ACCOUNTS
    ]


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
            errors.append(f"Account {acct_id} has {n} cards; expected 1-2")

    # 4 per category
    cat_counts = _Counter(r["category"] for r in MOCK_CARD_PRODUCTS)
    for cat in CARD_PRODUCT_CATEGORIES:
        if cat_counts.get(cat, 0) != 4:
            errors.append(
                f"Category '{cat}' has {cat_counts.get(cat, 0)} products; expected 4"
            )

    return errors


# ── 4-month persona-driven transaction history (2026-03-10 ~ 2026-07-10) ──────
# Source spec: RealFinance_소비페르소나.md (3 personas).
#
# Persona → Account mapping:
#   acct-0001 (김지훈) — 안정형 직장인 (salary day 25)
#   acct-0002 (박서연) — 재테크 워킹맘 (salary day 21)
#   acct-0003 (이도윤) — 불안정 프리랜서 (irregular income + risk signals)
#   acct-0004 / acct-0005 — 페르소나 미지정, 김지훈 패턴의 축소판 기본값
#
# Category → transaction-type mapping (per persona doc):
#   주거비/저축/투자/대출이자 → account transfer (Transaction, no card)
#   통신비/구독료/헬스장/학원비/관리비 → general payment (Transaction, to biller)
#   식비/쇼핑/여행/문화/교통/편의점 → card payment (CardLedgerEntry) — no
#     account-balance effect until settlement (settlement gen. out of scope)
#
# All transactions/ledger-entries/card-charges below are produced by
# _build_transaction_dataset(), a deterministic generator (fixed schedules +
# seeded `random.Random` per account/month — no wall-clock or OS randomness),
# so re-running this module always yields byte-identical mock data. This
# keeps running_balance correct by construction: balances are computed by
# walking one global chronological event timeline rather than hand-typed.

_TELECOM_BILLER = "acct-b001-0000-0000-000000000001"  # 통신사 (통신비+구독료)
_GYM_BILLER = "acct-b002-0000-0000-000000000002"  # 헬스장
_ACADEMY_BILLER = "acct-b003-0000-0000-000000000003"  # 학원
_MGMT_BILLER = "acct-b004-0000-0000-000000000004"  # 관리사무소 (월세+관리비)
_SAVINGS_BILLER = "acct-b005-0000-0000-000000000005"  # 저축은행
_INVEST_BILLER = "acct-b006-0000-0000-000000000006"  # 증권사
_LOAN_BILLER = "acct-b007-0000-0000-000000000007"  # 대출은행

_ACCT1 = "acct-0001-0000-0000-000000000001"  # 김지훈
_ACCT2 = "acct-0002-0000-0000-000000000002"  # 박서연
_ACCT3 = "acct-0003-0000-0000-000000000003"  # 이도윤
_ACCT4 = "acct-0004-0000-0000-000000000004"
_ACCT5 = "acct-0005-0000-0000-000000000005"

# (year, month, first_day, last_day) — clipped to 2026-03-10 ~ 2026-07-10
_MONTH_WINDOWS: list[tuple[int, int, int, int]] = [
    (2026, 3, 10, 31),
    (2026, 4, 1, 30),
    (2026, 5, 1, 31),
    (2026, 6, 1, 30),
    (2026, 7, 1, 10),
]

_STARTING_BALANCE: dict[str, int] = {
    _ACCT1: 3_000_000,
    _ACCT2: 8_000_000,
    _ACCT3: 1_200_000,
    _ACCT4: 2_500_000,
    _ACCT5: 2_500_000,
}

# Cards owned by each account (round-robin target for card charges).
_ACCOUNT_CARDS: dict[str, list[str]] = {}
for _row in MOCK_CARDS:
    _ACCOUNT_CARDS.setdefault(_row["account_id"], []).append(_row["card_id"])

# Merchant name pools per spending category — picked via the same seeded
# random.Random used for amounts/dates, so merchant assignment stays
# deterministic too.
_MERCHANTS_DINING = [
    "연남동 파스타",
    "김밥천국",
    "교촌치킨",
    "스타벅스",
    "새마을식당",
    "본죽",
]
_MERCHANTS_MART = ["이마트", "홈플러스", "롯데마트", "GS25", "CU편의점", "세븐일레븐"]
_MERCHANTS_SHOPPING = ["쿠팡", "무신사", "29CM", "네이버쇼핑", "올리브영"]
_MERCHANTS_TRAVEL = ["대한항공", "아고다", "야놀자", "여기어때"]
_MERCHANTS_DELIVERY = ["배달의민족", "쿠팡이츠", "요기요"]
_MERCHANTS_TRANSIT = ["티머니", "카카오T", "SRT"]
_MERCHANTS_HOBBY = ["교보문고", "다이소", "네이버페이 - 굿즈샵", "스팀"]


def _dt(year: int, month: int, day: int, hour: int = 9, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


def _clip_day(day: int, last_day: int) -> int:
    """Clamp *day* into [1, last_day] so fixed-day events never overflow a
    short month."""
    return max(1, min(day, last_day))


class _Counter:
    """Monotonic id-sequence generator for mock rows (module-private)."""

    def __init__(self) -> None:
        self._n = 0

    def next(self) -> int:
        self._n += 1
        return self._n


def _build_transaction_dataset() -> tuple[
    list[dict], list[dict], list[dict], dict[str, int]
]:
    """Deterministically build 4 months of persona-driven transaction history.

    Returns (transactions, ledger_entries, card_ledger_entries, final_balances)
    as plain dict rows ready for ``Transaction(**d)`` / ``LedgerEntry(**d)`` /
    ``CardLedgerEntry(**d)``. Card charges never touch account balances
    (mirrors the app's card deferred-settlement design — see Card docstring
    in models.py); only account-transfer / general-payment events do.

    ``final_balances`` maps every account_id that appears as a sender or
    receiver (user, biller, or external-source) to its ending balance after
    the full chronological walk — this is the canonical ``Account.balance``
    value each row must be seeded with (see Account.balance docstring in
    models.py: it must always equal SUM(CREDIT) - SUM(DEBIT) over
    ledger_entries, so mock rows have to satisfy the same invariant).
    """
    seq = _Counter()
    balance: dict[str, int] = dict(_STARTING_BALANCE)
    # events: (date, kind, account_id, receiver_or_card, amount, status, merchant)
    # merchant is None for "transfer" kind; a merchant/store label for "card".
    events: list[tuple[date, str, str, str, int, str, str | None]] = []

    def add_transfer(
        d: date, sender: str, receiver: str, amount: int, status: str = "success"
    ) -> None:
        events.append((d, "transfer", sender, receiver, amount, status, None))

    def add_card(
        d: date, account_id: str, amount: int, merchant: str, card_index: int = 0
    ) -> None:
        cards = _ACCOUNT_CARDS.get(account_id)
        if not cards:
            return
        card_id = cards[card_index % len(cards)]
        events.append((d, "card", account_id, card_id, amount, "success", merchant))

    # ── 김지훈 (acct-0001) — 안정형 직장인, salary day 25 ─────────────────────
    for y, m, first, last in _MONTH_WINDOWS:
        rnd = random.Random(f"{_ACCT1}-{y}{m:02d}")
        if first <= 25 <= last:
            add_transfer(date(y, m, 25), "SALARY", _ACCT1, 2_450_000)
            add_transfer(
                date(y, m, _clip_day(26, last)), _ACCT1, _SAVINGS_BILLER, 370_000
            )
            add_transfer(date(y, m, _clip_day(27, last)), _ACCT1, _MGMT_BILLER, 540_000)
            add_transfer(
                date(y, m, _clip_day(27, last)), _ACCT1, _TELECOM_BILLER, 120_000
            )
            add_transfer(date(y, m, _clip_day(28, last)), _ACCT1, _GYM_BILLER, 100_000)
        # 카드결제: 외식 10건 / 마트-편의점 4건 / 쇼핑 2건
        for _ in range(10):
            d = rnd.randint(first, last)
            add_card(
                date(y, m, d),
                _ACCT1,
                rnd.randint(8_000, 15_000),
                rnd.choice(_MERCHANTS_DINING),
                card_index=0,
            )
        for _ in range(4):
            d = rnd.randint(first, last)
            add_card(
                date(y, m, d),
                _ACCT1,
                rnd.randint(15_000, 60_000),
                rnd.choice(_MERCHANTS_MART),
                card_index=1,
            )
        for _ in range(2):
            d = rnd.randint(first, last)
            add_card(
                date(y, m, d),
                _ACCT1,
                rnd.randint(30_000, 80_000),
                rnd.choice(_MERCHANTS_SHOPPING),
                card_index=0,
            )
    # 4개월 중 1회 여행 특별 소비 + 1회 경조사비 송금
    add_card(
        date(2026, 5, 16), _ACCT1, 260_000, rnd.choice(_MERCHANTS_TRAVEL), card_index=1
    )
    add_transfer(date(2026, 6, 20), _ACCT1, _ACCT2, 100_000)  # 경조사비

    # ── 박서연 (acct-0002) — 재테크 워킹맘, salary day 21 ─────────────────────
    for y, m, first, last in _MONTH_WINDOWS:
        rnd = random.Random(f"{_ACCT2}-{y}{m:02d}")
        if first <= 21 <= last:
            add_transfer(date(y, m, 21), "SALARY", _ACCT2, 4_200_000)
            add_transfer(date(y, m, _clip_day(21, last)), _ACCT2, _LOAN_BILLER, 630_000)
            add_transfer(date(y, m, _clip_day(22, last)), _ACCT2, _MGMT_BILLER, 170_000)
            add_transfer(
                date(y, m, _clip_day(22, last)), _ACCT2, _ACADEMY_BILLER, 420_000
            )
            add_transfer(
                date(y, m, _clip_day(23, last)), _ACCT2, _INVEST_BILLER, 840_000
            )
            add_transfer(
                date(y, m, _clip_day(23, last)), _ACCT2, _SAVINGS_BILLER, 340_000
            )
        # 카드결제: 마트 대량구매 5건(주1회) / 외식(야근 배달 등) 6건 / 쇼핑 2건
        for _ in range(5):
            d = rnd.randint(first, last)
            add_card(
                date(y, m, d),
                _ACCT2,
                rnd.randint(100_000, 200_000),
                rnd.choice(_MERCHANTS_MART),
                card_index=0,
            )
        for _ in range(6):
            d = rnd.randint(first, last)
            add_card(
                date(y, m, d),
                _ACCT2,
                rnd.randint(15_000, 60_000),
                rnd.choice(_MERCHANTS_DINING + _MERCHANTS_DELIVERY),
                card_index=0,
            )
        for _ in range(2):
            d = rnd.randint(first, last)
            add_card(
                date(y, m, d),
                _ACCT2,
                rnd.randint(50_000, 250_000),
                rnd.choice(_MERCHANTS_SHOPPING),
                card_index=0,
            )
    add_card(
        date(2026, 4, 12), _ACCT2, 480_000, rnd.choice(_MERCHANTS_TRAVEL), card_index=0
    )  # 가족 여행/명절 지출 급증

    # ── 이도윤 (acct-0003) — 불안정 프리랜서, 불규칙 입금 + 리스크 신호 ────────
    for y, m, first, last in _MONTH_WINDOWS:
        rnd = random.Random(f"{_ACCT3}-{y}{m:02d}")
        income_day = rnd.randint(max(first, 5), min(last, 20))
        add_transfer(
            date(y, m, income_day), "SALARY", _ACCT3, rnd.randint(1_500_000, 2_800_000)
        )
        # 배달음식 18건 / 편의점 8건 / 온라인쇼핑·취미 3건 / 교통 4건
        for _ in range(18):
            d = rnd.randint(first, last)
            add_card(
                date(y, m, d),
                _ACCT3,
                rnd.randint(15_000, 28_000),
                rnd.choice(_MERCHANTS_DELIVERY),
                card_index=0,
            )
        for _ in range(8):
            d = rnd.randint(first, last)
            add_card(
                date(y, m, d),
                _ACCT3,
                rnd.randint(3_000, 7_000),
                rnd.choice(_MERCHANTS_MART),
                card_index=0,
            )
        for _ in range(3):
            d = rnd.randint(first, last)
            add_card(
                date(y, m, d),
                _ACCT3,
                rnd.randint(10_000, 40_000),
                rnd.choice(_MERCHANTS_SHOPPING + _MERCHANTS_HOBBY),
                card_index=0,
            )
        for _ in range(4):
            d = rnd.randint(first, last)
            add_card(
                date(y, m, d),
                _ACCT3,
                rnd.randint(3_000, 12_000),
                rnd.choice(_MERCHANTS_TRANSIT),
                card_index=0,
            )
    # 보복소비 클러스터: 하루 3건 몰림 (5월)
    for amt in (90_000, 120_000, 60_000):
        add_card(
            date(2026, 5, 23),
            _ACCT3,
            amt,
            rnd.choice(_MERCHANTS_SHOPPING),
            card_index=0,
        )
    # 지인에게 급하게 소액 이체받기 (계좌간송금 입금, 비정기)
    add_transfer(date(2026, 6, 28), "FRIEND", _ACCT3, 200_000)
    # 리스크 신호 3건: 결제 실패 → 재시도 성공 (일반결제)
    add_transfer(date(2026, 4, 15), _ACCT3, _TELECOM_BILLER, 65_000, status="failure")
    add_transfer(date(2026, 4, 17), _ACCT3, _TELECOM_BILLER, 65_000)
    add_transfer(date(2026, 5, 10), _ACCT3, _TELECOM_BILLER, 18_900, status="failure")
    add_transfer(date(2026, 5, 11), _ACCT3, _TELECOM_BILLER, 18_900)
    add_transfer(date(2026, 6, 1), _ACCT3, _MGMT_BILLER, 350_000, status="failure")
    add_transfer(date(2026, 6, 3), _ACCT3, _MGMT_BILLER, 350_000)
    # 월세(고정) — 리스크 신호가 없는 달만 정상 청구
    for y, m, first, last in _MONTH_WINDOWS:
        if (y, m) in ((2026, 6),):
            continue  # already covered by the fail/retry pair above
        add_transfer(date(y, m, _clip_day(3, last)), _ACCT3, _MGMT_BILLER, 520_000)
        if (y, m) != (2026, 4):  # April covered by the fail/retry pair above
            add_transfer(
                date(y, m, _clip_day(14, last)), _ACCT3, _TELECOM_BILLER, 130_000
            )

    # ── acct-0004 / acct-0005 — 페르소나 미지정, 김지훈 축소판 기본값 ─────────
    for acct, salary_day in ((_ACCT4, 25), (_ACCT5, 10)):
        for y, m, first, last in _MONTH_WINDOWS:
            rnd = random.Random(f"{acct}-{y}{m:02d}")
            if first <= salary_day <= last:
                add_transfer(date(y, m, salary_day), "SALARY", acct, 2_000_000)
                add_transfer(
                    date(y, m, _clip_day(salary_day + 1, last)),
                    acct,
                    _MGMT_BILLER,
                    400_000,
                )
                add_transfer(
                    date(y, m, _clip_day(salary_day + 1, last)),
                    acct,
                    _TELECOM_BILLER,
                    100_000,
                )
                add_transfer(
                    date(y, m, _clip_day(salary_day + 2, last)),
                    acct,
                    _SAVINGS_BILLER,
                    200_000,
                )
            for _ in range(6):
                d = rnd.randint(first, last)
                add_card(
                    date(y, m, d),
                    acct,
                    rnd.randint(8_000, 20_000),
                    rnd.choice(_MERCHANTS_DINING),
                    card_index=0,
                )
            for _ in range(3):
                d = rnd.randint(first, last)
                add_card(
                    date(y, m, d),
                    acct,
                    rnd.randint(15_000, 50_000),
                    rnd.choice(_MERCHANTS_MART),
                    card_index=0,
                )
            for _ in range(1):
                d = rnd.randint(first, last)
                add_card(
                    date(y, m, d),
                    acct,
                    rnd.randint(30_000, 70_000),
                    rnd.choice(_MERCHANTS_SHOPPING),
                    card_index=0,
                )

    # ── Chronological walk: build Transaction / LedgerEntry / CardLedgerEntry rows ──
    events.sort(key=lambda e: (e[0], 0 if e[1] == "card" else 1))

    transactions: list[dict] = []
    ledger_entries: list[dict] = []
    card_ledger_entries: list[dict] = []

    for ev_date, kind, a, b, amount, status, merchant in events:
        n = seq.next()
        created_at = _dt(ev_date.year, ev_date.month, ev_date.day)

        if kind == "card":
            card_ledger_entries.append(
                {
                    "card_ledger_entry_id": f"cle-mock-{n:06d}",
                    "card_id": b,
                    "amount": amount,
                    "idempotency_key": f"mock-card-{n:06d}",
                    "merchant_name": merchant,
                    "created_at": created_at,
                }
            )
            continue

        # "transfer" (account transfer / general payment / income / risk signal)
        sender_key = (
            "acct-b099-0000-0000-000000000099" if a in ("SALARY", "FRIEND") else a
        )
        # External payroll/friend sources are not modeled as a real Account —
        # use a shared external-source placeholder so the FK target still
        # resolves to an existing Account without polluting the 5 user / 7
        # biller accounts. Registered in MOCK_EXTERNAL_SOURCE_ACCOUNTS below.
        transactions.append(
            {
                "transaction_id": f"txn-mock-{n:06d}",
                "idempotency_key": f"mock-tx-{n:06d}",
                "payload_hash": f"{n:064x}"[-64:],
                "sender_account_id": sender_key,
                "receiver_account_id": b,
                "amount": amount,
                "status": status,
                "settlement_type": None,
                "settlement_card_id": None,
                "settlement_watermark_rowid": None,
                "created_at": created_at,
            }
        )

        if status != "success":
            continue  # failure rows: no ledger movement

        balance[sender_key] = balance.get(sender_key, 0) - amount
        balance[b] = balance.get(b, 0) + amount

        ledger_entries.append(
            {
                "entry_id": f"le-mock-{n:06d}-d",
                "transaction_id": f"txn-mock-{n:06d}",
                "account_id": sender_key,
                "entry_type": "DEBIT",
                "amount": amount,
                "running_balance": balance[sender_key],
                "created_at": created_at,
            }
        )
        ledger_entries.append(
            {
                "entry_id": f"le-mock-{n:06d}-c",
                "transaction_id": f"txn-mock-{n:06d}",
                "account_id": b,
                "entry_type": "CREDIT",
                "amount": amount,
                "running_balance": balance[b],
                "created_at": created_at,
            }
        )

    return transactions, ledger_entries, card_ledger_entries, dict(balance)


# External payroll-deposit / peer-transfer source. Not a "biller" (money flows
# IN from here, not out to it) — kept separate from MOCK_BILLER_ACCOUNTS so
# biller-only queries (e.g. "list payment recipients") stay clean.
MOCK_EXTERNAL_SOURCE_ACCOUNTS: list[dict] = [
    {
        "account_id": "acct-b099-0000-0000-000000000099",
        "owner": "외부입금원(급여/지인송금)",
        "alias": "급여·지인 입금",
        "account_number": "999-000-000099",
        "currency": "KRW",
    },
]


def make_external_source_account_rows() -> list[Account]:
    """Return the external-source Account row (payroll deposits, peer transfers).

    balance is injected from MOCK_FINAL_BALANCES so it satisfies the same
    canonical-balance invariant as every other Account row (see Account.balance
    docstring in models.py). This account only ever sends money (DEBIT), so
    its balance is expected to be deeply negative — it represents value
    entering the modeled system from outside, not a real funded account.
    """
    return [
        Account(**d, balance=MOCK_FINAL_BALANCES.get(d["account_id"], 0))
        for d in MOCK_EXTERNAL_SOURCE_ACCOUNTS
    ]


(
    MOCK_TRANSACTIONS,
    MOCK_LEDGER_ENTRIES,
    MOCK_CARD_LEDGER_ENTRIES,
    MOCK_FINAL_BALANCES,
) = _build_transaction_dataset()


def make_transaction_rows() -> list[Transaction]:
    """Return Transaction ORM instances for the 4-month mock history.

    Requires MOCK_ACCOUNTS, MOCK_BILLER_ACCOUNTS, and
    MOCK_EXTERNAL_SOURCE_ACCOUNTS to already exist (sender/receiver FKs).
    """
    return [Transaction(**d) for d in MOCK_TRANSACTIONS]


def make_ledger_entry_rows() -> list[LedgerEntry]:
    """Return LedgerEntry ORM instances (paired DEBIT/CREDIT per Transaction).

    Parent Transaction rows must be flushed first (FK).
    """
    return [LedgerEntry(**d) for d in MOCK_LEDGER_ENTRIES]


def make_card_ledger_entry_rows() -> list[CardLedgerEntry]:
    """Return CardLedgerEntry ORM instances for the 4-month mock card spend.

    Card charges never touch account balances (deferred settlement) —
    only account-transfer/general-payment Transactions do.
    """
    return [CardLedgerEntry(**d) for d in MOCK_CARD_LEDGER_ENTRIES]
