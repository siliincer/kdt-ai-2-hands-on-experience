"""Workspace-root shim — re-exports all ORM models for seed scripts and ad-hoc use.

Import as: ``from models import CardProduct, Account, Card``
"""

import os
import sys

# Ensure the package is importable when running from workspace root
_src = os.path.join(os.path.dirname(__file__), "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

from financial_service.models import (  # noqa: E402
    CARD_PRODUCT_CATEGORIES,
    Account,
    AuditLog,
    BalanceSnapshot,
    Card,
    CardLedgerEntry,
    CardProduct,
    DailyClosingSnapshot,
    LedgerEntry,
    Transaction,
)

__all__ = [
    "Account",
    "AuditLog",
    "BalanceSnapshot",
    "Card",
    "CardLedgerEntry",
    "CardProduct",
    "CARD_PRODUCT_CATEGORIES",
    "DailyClosingSnapshot",
    "LedgerEntry",
    "Transaction",
]
