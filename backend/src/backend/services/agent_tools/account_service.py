"""계좌 목록(API-ACCOUNT-LIST)·잔액 조회(API-BALANCE-QUERY) 비즈니스 로직.

- 목록: Backend 로컬 accounts 테이블(사용자 소유 매핑 계좌) 정본.
- 잔액: http 모드는 계정계(정보계), mock 모드는 로컬 Account.balance 캐시에서 읽는다.
  hold 개념이 없어 available_balance = balance 로 시작한다(D7).
- Agent 에는 전체 계좌번호를 노출하지 않고 마스킹값만 반환한다(계약 2·9·10장).
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ...core.agent_exceptions import AgentToolError
from ...core.load_environment_var import settings
from ...models.account import Account
from ...repository.account_repository import (
    get_mapped_accounts,
    get_owned_accounts_by_ids,
)
from ...schemas.agent_tools.account import (
    AccountCapability,
    AccountListData,
    AccountListItem,
    BalanceQueryData,
    BalanceResultItem,
)
from ...schemas.execution_context import ResolvedExecutionContext
from ...utils.masking import mask_account_number
from ..financial import get_financial_client


def _use_http() -> bool:
    return settings.FINANCIAL_CLIENT.strip().lower() == "http"


def _matches_hint(account: Account, hint: str) -> bool:
    """account_hint 검색 범위를 은행명·별칭·계좌 유형으로 제한한다(계약 9.5)."""
    needle = hint.strip().lower()
    haystacks = [account.bank_name, account.alias, account.account_type]
    return any(h is not None and needle in h.lower() for h in haystacks)


def _to_list_item(account: Account) -> AccountListItem:
    return AccountListItem(
        account_id=str(account.id),
        bank_name=account.bank_name,
        account_alias=account.alias,
        account_type=account.account_type,
        masked_account_number=mask_account_number(account.account_number),
        currency=account.currency,
        is_default=account.is_default,
        status="active" if account.active else "inactive",
    )


async def list_accounts(
    session: AsyncSession,
    context: ResolvedExecutionContext,
    account_hint: str | None,
    account_capability: AccountCapability | None,
    limit: int,
) -> AccountListData:
    """사용자 소유 계좌를 검색·필터해 반환한다.

    account_capability 가 주어지면 활성 계좌만 반환한다(Backend 가 상태 판단).
    단일 은행 샌드박스라 capability 별 세부 거래 가능 여부는 활성 여부로 근사한다.
    """
    accounts = await get_mapped_accounts(session, context.user_id)

    # TODO(capability): withdraw/deposit/settings 별 세부 판단. 현재는 활성 근사.
    if account_capability is not None:
        accounts = [a for a in accounts if a.active]

    if account_hint:
        accounts = [a for a in accounts if _matches_hint(a, account_hint)]

    accounts = accounts[:limit]
    return AccountListData(accounts=[_to_list_item(a) for a in accounts])


def _parse_account_ids(raw_ids: list[str]) -> list[UUID]:
    try:
        return [UUID(raw) for raw in raw_ids]
    except (ValueError, AttributeError) as exc:
        raise AgentToolError.invalid_request(
            "account_ids 형식이 올바르지 않습니다."
        ) from exc


async def _resolve_balance(account: Account) -> int:
    """계좌 잔액을 조회한다. http=계정계, mock=로컬 캐시. 계정계 404 는 계좌 없음."""
    if not _use_http():
        return account.balance
    if not account.external_account_id:
        raise AgentToolError.account_not_found()
    result = await get_financial_client().get_balance(account.external_account_id)
    if result is None:
        raise AgentToolError.account_not_found()
    return int(result["balance"])


async def query_balances(
    session: AsyncSession,
    context: ResolvedExecutionContext,
    account_ids: list[str],
) -> BalanceQueryData:
    """복수 계좌 잔액을 조회한다. 소유권 검증 실패 시 전체 거절(계약 10.4)."""
    parsed = _parse_account_ids(account_ids)
    owned = await get_owned_accounts_by_ids(session, context.user_id, parsed)

    # 한 계좌라도 소유·접근 검증에 실패하면 부분 결과 없이 전체 거절.
    if len(owned) != len(parsed):
        raise AgentToolError.account_access_denied()

    by_id = {account.id: account for account in owned}
    as_of = datetime.now(timezone.utc)

    results: list[BalanceResultItem] = []
    for account_id in parsed:
        account = by_id[account_id]
        balance = await _resolve_balance(account)
        results.append(
            BalanceResultItem(
                account_id=str(account.id),
                bank_name=account.bank_name,
                account_alias=account.alias,
                masked_account_number=mask_account_number(account.account_number),
                balance=balance,
                available_balance=balance,
                currency=account.currency,
                as_of=as_of,
            )
        )
    return BalanceQueryData(balance_results=results)
