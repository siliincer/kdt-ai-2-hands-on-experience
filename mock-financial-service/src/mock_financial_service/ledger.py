"""인메모리 원장 (Fake Money).

agent/src/agent/data/mock_bank.py와 동일한 시드다 — 두 서비스가 각자의
프로세스에서 독립 원장을 가지므로 직접 import하지 않고 복제해 둔다.
DB 도입 시 이 모듈만 교체하면 된다.
"""

from __future__ import annotations

import copy

_SEED_ACCOUNTS: dict[str, list[dict]] = {
    "user_001": [
        {
            "account_id": "acc_001",
            "account_name": "입출금통장",
            "balance": 1_250_000,
            "currency": "KRW",
            "is_default": True,
        },
        {
            "account_id": "acc_002",
            "account_name": "생활비통장",
            "balance": 430_000,
            "currency": "KRW",
            "is_default": False,
        },
    ]
}

_SEED_RECIPIENTS: dict[str, list[dict]] = {
    "user_001": [
        {
            "recipient_id": "rec_001",
            "name": "김철수",
            "bank": "국민은행",
            "account_number": "123-456-789012",
        },
        {
            "recipient_id": "rec_002",
            "name": "이영희",
            "bank": "신한은행",
            "account_number": "110-123-456789",
        },
    ]
}

ACCOUNTS: dict[str, list[dict]] = copy.deepcopy(_SEED_ACCOUNTS)
RECIPIENTS: dict[str, list[dict]] = copy.deepcopy(_SEED_RECIPIENTS)
AUDIT_LOGS: list[dict] = []


def reset() -> None:
    """원장을 시드 상태로 복원한다 (테스트용)."""
    ACCOUNTS.clear()
    ACCOUNTS.update(copy.deepcopy(_SEED_ACCOUNTS))
    RECIPIENTS.clear()
    RECIPIENTS.update(copy.deepcopy(_SEED_RECIPIENTS))
    AUDIT_LOGS.clear()
