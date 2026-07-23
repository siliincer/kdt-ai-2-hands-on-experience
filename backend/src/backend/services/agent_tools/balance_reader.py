"""계좌 잔액 읽기 공통 로직.

잔액의 정본은 계정계(정보계)다. 계정계 원장이 잔액의 단일 출처이므로 로컬
`Account.balance` 캐시로 대체하지 않는다(mock 일원화, 작업 B).

hold 개념이 계정계에 없어 출금 가능 잔액은 잔액과 동일하다(D7).
TODO(계정계): hold(출금 보류) 도입 시 available_balance 를 분리해서 받아야 한다.
"""

from __future__ import annotations

from ...core.agent_exceptions import AgentToolError
from ...models.account import Account
from ..financial import get_financial_client


async def read_balance(account: Account) -> int:
    """계좌 잔액을 조회한다. 계정계 404(계좌 없음)는 ACCOUNT_NOT_FOUND 로 번역한다."""
    if not account.external_account_id:
        raise AgentToolError.account_not_found()
    result = await get_financial_client().get_balance(account.external_account_id)
    if result is None:
        raise AgentToolError.account_not_found()
    return int(result["balance"])


async def read_available_balance(account: Account) -> int:
    """출금 가능 잔액. 현재는 hold 가 없어 잔액과 같다(D7)."""
    return await read_balance(account)
