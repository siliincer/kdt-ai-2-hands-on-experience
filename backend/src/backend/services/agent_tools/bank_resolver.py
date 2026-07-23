"""수취 은행명 해석 (D6 의 교체 지점).

계정계는 다은행(계좌마다 실제 은행명)을 표현한다. 은행명을 읽는 경로를 여기로
모아 호출부가 은행명을 직접 하드코딩하지 않게 한다.

경로별 해석 함수를 나눠 둔다:
1. `resolve_owned_account_bank` — 내가 소유한 계좌(로컬 매핑에 bank_name 보유).
본인이체·타인송금의 출금 계좌에 사용한다.
2. 신규 수취 계좌 후보(recipient_candidate) 경로는 Stage 6 에서 추가한다.
"""

from __future__ import annotations

from ...models.account import Account
from .policy_constants import DEFAULT_BANK_NAME


def resolve_owned_account_bank(account: Account) -> str:
    """소유 계좌의 은행명. 매핑에 값이 없는 예외적인 경우에만 대체값을 쓴다."""
    return account.bank_name or DEFAULT_BANK_NAME
