"""수취 은행명 해석 (D6 의 교체 지점).

계정계는 현재 단일 은행("KDT은행")이라 타인송금도 동일은행 타 owner 계좌로 처리한다.
다은행을 도입하면 이 모듈의 함수만 교체(또는 deprecated 처리)하면 되도록, 은행명을
읽는 경로를 여기로 모은다. 호출부는 은행명을 직접 하드코딩하지 않는다.

경로별 해석 함수를 나눠 둔다:
1. `resolve_owned_account_bank` — 내가 소유한 계좌(로컬 매핑에 bank_name 보유).
본인이체·타인송금의 출금 계좌에 사용한다.
2. 신규 수취 계좌 후보(recipient_candidate) 경로는 Stage 6 에서 추가한다.
"""

from __future__ import annotations

from ...models.account import Account
from .policy_constants import DEFAULT_BANK_NAME


def resolve_owned_account_bank(account: Account) -> str:
    """소유 계좌의 은행명. 매핑에 값이 없으면 계정계 단일 은행명으로 대체한다.

    TODO(D6): 다은행 도입 시 fallback 을 제거하고 계좌별 은행명을 필수로 만든다.
    """
    return account.bank_name or DEFAULT_BANK_NAME
