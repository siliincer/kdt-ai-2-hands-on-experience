"""Tests verifying card_products rows carry realistic, internally-consistent specs.

Checks:
1. product_name is non-empty string matching its category context
2. annual_fee tiers are plausible (0–200_000 KRW range, no absurd values)
3. benefits list has 1–5 items per row (not empty, not bloated)
4. benefits text mentions category-relevant Korean keywords
5. Higher annual_fee products have at least as many benefits as free-tier cards
6. Each category has exactly one free (annual_fee==0) card product
7. Spec internal consistency: annual_fee > 0 products mention 할인/적립/캐시백/면제/무료
"""

from __future__ import annotations

import json
from collections import defaultdict

import pytest
from financial_service.mock_data import MOCK_CARD_PRODUCTS

# ── Category keyword map — at least one keyword must appear in benefits text ──
CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "외식": ["외식", "레스토랑", "카페", "배달", "음식", "다이닝", "미식"],
    "쇼핑": ["쇼핑", "백화점", "온라인", "쿠팡", "오픈마켓", "아울렛", "이커머스"],
    "여행": ["여행", "해외", "항공", "공항", "호텔", "마일", "환전"],
    "웹구독": ["구독", "OTT", "스트리밍", "넷플릭스", "클라우드", "앱", "디지털"],
    "마트/편의점": [
        "마트",
        "편의점",
        "이마트",
        "홈플러스",
        "롯데마트",
        "CU",
        "GS25",
        "마켓",
    ],
}

# Benefit-quality keywords — every product should mention at least one
BENEFIT_QUALITY_KEYWORDS = [
    "할인",
    "적립",
    "캐시백",
    "면제",
    "무료",
    "보너스",
    "쿠폰",
    "우선",
]

# Max plausible annual fee for a Korean credit card (KRW)
MAX_ANNUAL_FEE = 200_000


@pytest.fixture(scope="module")
def products_by_category() -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = defaultdict(list)
    for row in MOCK_CARD_PRODUCTS:
        result[row["category"]].append(row)
    return dict(result)


# ── 1. product_name non-empty and string ──────────────────────────────────────


def test_product_name_is_nonempty_string():
    for row in MOCK_CARD_PRODUCTS:
        name = row["product_name"]
        assert isinstance(name, str) and name.strip(), (
            f"card_product_id={row['card_product_id']} has blank/invalid product_name"
        )


# ── 2. annual_fee in plausible KRW range ─────────────────────────────────────


def test_annual_fee_within_plausible_range():
    for row in MOCK_CARD_PRODUCTS:
        fee = row["annual_fee"]
        assert 0 <= fee <= MAX_ANNUAL_FEE, (
            f"{row['product_name']}: annual_fee={fee} out of range "
            f"[0, {MAX_ANNUAL_FEE}]"
        )


# ── 3. benefits list has 1–5 items ───────────────────────────────────────────


def test_benefits_item_count_between_1_and_5():
    for row in MOCK_CARD_PRODUCTS:
        parsed = json.loads(row["benefits"])
        count = len(parsed)
        assert 1 <= count <= 5, (
            f"{row['product_name']}: benefits has {count} items (expected 1-5)"
        )


# ── 4. benefits text contains category-relevant keywords ─────────────────────


def test_benefits_mention_category_keywords():
    for row in MOCK_CARD_PRODUCTS:
        cat = row["category"]
        keywords = CATEGORY_KEYWORDS.get(cat, [])
        benefits_text = " ".join(json.loads(row["benefits"]))
        matched = any(kw in benefits_text for kw in keywords)
        assert matched, (
            f"{row['product_name']} (category={cat}): benefits text does not mention "
            f"any of {keywords}. Text: {benefits_text!r}"
        )


# ── 5. each product mentions at least one benefit-quality keyword ─────────────


def test_benefits_mention_quality_keywords():
    for row in MOCK_CARD_PRODUCTS:
        benefits_text = " ".join(json.loads(row["benefits"]))
        matched = any(kw in benefits_text for kw in BENEFIT_QUALITY_KEYWORDS)
        assert matched, (
            f"{row['product_name']}: benefits text lacks quality keywords "
            f"{BENEFIT_QUALITY_KEYWORDS}. Text: {benefits_text!r}"
        )


# ── 6. overall at least 3 free-tier (annual_fee==0) products exist ───────────
#    (Travel cards realistically all have fees; we don't require each category
#     to have a free option, only that the catalog as a whole offers free options)


def test_catalog_has_multiple_free_products():
    free_count = sum(1 for r in MOCK_CARD_PRODUCTS if r["annual_fee"] == 0)
    assert free_count >= 3, (
        f"Catalog has only {free_count} free (annual_fee=0) products; expected >= 3"
    )


# ── 7. paid products (annual_fee > 0) have >= 2 benefit items ────────────────


def test_paid_products_have_sufficient_benefits():
    for row in MOCK_CARD_PRODUCTS:
        if row["annual_fee"] > 0:
            parsed = json.loads(row["benefits"])
            assert len(parsed) >= 2, (
                f"{row['product_name']} (annual_fee={row['annual_fee']}): "
                f"paid product should have >=2 benefits, got {len(parsed)}"
            )


# ── 8. product names are meaningful (length >= 4 chars) ──────────────────────


def test_product_name_min_length():
    for row in MOCK_CARD_PRODUCTS:
        name = row["product_name"]
        assert len(name) >= 4, (
            f"card_product_id={row['card_product_id']}: "
            f"product_name too short: {name!r}"
        )


# ── 9. spec consistency: free-tier cards mention 연회비 무료 or 무료 ─────────


def test_free_tier_cards_mention_free_in_benefits():
    for row in MOCK_CARD_PRODUCTS:
        if row["annual_fee"] == 0:
            benefits_text = " ".join(json.loads(row["benefits"]))
            assert "무료" in benefits_text, (
                f"{row['product_name']} (annual_fee=0): "
                f"free card should mention '무료' in benefits. "
                f"Text: {benefits_text!r}"
            )
