"""계좌 목록(API-ACCOUNT-LIST)·잔액 조회(API-BALANCE-QUERY) 비즈니스 로직.

- 목록: Backend 로컬 accounts 테이블(사용자 소유 매핑 계좌) 정본.
- 잔액: http 모드는 계정계(정보계), mock 모드는 로컬 Account.balance 캐시에서 읽는다.
  hold 개념이 없어 available_balance = balance 로 시작한다(D7).
- Agent에는 전체 계좌번호를 노출하지 않고 마스킹값만 반환한다(계약 2·9·10장).
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from ...core.agent_exceptions import AgentToolError
from ...models.account import Account
from ...repository.account_repository import (
    get_mapped_accounts,
    get_owned_accounts_by_ids,
)
from ...schemas.agent_tools.account import (
    AccountCapability,
    AccountListData,
    AccountListItem,
    AccountResolutionOutcome,
    BalanceQueryData,
    BalanceResultItem,
)
from ...schemas.execution_context import ResolvedExecutionContext
from ...utils.masking import mask_account_number
from ...utils.parsing import parse_uuid_list
from .balance_reader import read_balance


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


def _resolve_accounts(
    candidates: list[Account],
    *,
    all_accounts_requested: bool,
    prefer_default: bool = False,
) -> tuple[AccountResolutionOutcome, list[str]]:
    """필터된 후보로 계좌 해소 결과를 판정한다(계약 9.2).

    - 후보 0개: no_accounts.
    - 전체 요청이거나 후보 1개: resolved(확정 account_ids).
    - prefer_default=True(힌트 없는 출금 계좌 해소): 후보 2개+ 라도 기본 출금 계좌
      (is_default)가 정확히 1개면 그 계좌로 resolved. 사용자가 정한 기본 계좌를 존중해
      매번 선택을 묻지 않는다(계약 20.5, 유저당 default 1개 보장).
    - 그 외 후보 2개+: selection_required(사용자 선택 필요, account_ids 없음).
    """
    if not candidates:
        return "no_accounts", []
    if all_accounts_requested or len(candidates) == 1:
        return "resolved", [str(a.id) for a in candidates]
    if prefer_default:
        defaults = [a for a in candidates if a.is_default]
        if len(defaults) == 1:
            return "resolved", [str(defaults[0].id)]
    return "selection_required", []


async def list_accounts(
    session: AsyncSession,
    context: ResolvedExecutionContext,
    account_hint: str | None,
    account_capability: AccountCapability | None,
    limit: int,
    *,
    resolve_selection: bool = False,
    all_accounts_requested: bool = False,
    exclude_account_ids: list[str] | None = None,
    force_selection: bool = False,
) -> AccountListData:
    """사용자 소유 계좌를 검색·필터해 반환한다.

    account_capability 가 주어지면 활성 계좌만 반환한다(Backend 가 상태 판단).
    단일 은행 샌드박스라 capability 별 세부 거래 가능 여부는 활성 여부로 근사한다.

    resolve_selection=True 면 후보로부터 계좌 해소 결과(account_resolution_outcome·
    account_ids)를 함께 채운다(계약 9.2). Agent read/transfer 워크플로우가 이 값으로
    바로 조회할지(resolved)·사용자에게 선택을 물을지(selection_required)를 결정한다.

    force_selection=True 면 기본 출금 계좌가 있어도 자동 확정하지 않고 항상
    selection_required 를 반환한다. 승인 화면에서 사용자가 명시적으로 "계좌 변경"을
    눌러 들어온 경우 사용 — prefer_default 로 매번 같은 기본 계좌가 자동 확정되면
    선택 화면 자체가 뜨지 않아 그 버튼이 무효해진다.
    """
    accounts = await get_mapped_accounts(session, context.user_id)

    # TODO(capability): withdraw/deposit/settings 별 세부 판단. 현재는 활성 근사.
    if account_capability is not None:
        accounts = [a for a in accounts if a.active]

    if exclude_account_ids:
        excluded = set(exclude_account_ids)
        accounts = [a for a in accounts if str(a.id) not in excluded]

    if account_hint:
        accounts = [a for a in accounts if _matches_hint(a, account_hint)]

    # 해소는 필터된 전체 후보 기준으로 판정하고, 반환 목록만 limit 를 적용한다.
    items = [_to_list_item(a) for a in accounts[:limit]]
    if not resolve_selection:
        return AccountListData(accounts=items)

    # 힌트 없는 출금 계좌 해소(송금 from-account)에서는 사용자의 기본 출금 계좌를 존중한다.
    # force_selection 이면 이 자동 확정을 끄고 항상 선택 화면을 보여준다.
    prefer_default = account_capability == AccountCapability.WITHDRAW and not account_hint and not force_selection
    outcome, resolved_ids = _resolve_accounts(
        accounts,
        all_accounts_requested=all_accounts_requested,
        prefer_default=prefer_default,
    )
    return AccountListData(
        accounts=items,
        account_resolution_outcome=outcome,
        account_ids=resolved_ids,
    )


def _invalid_account_ids() -> AgentToolError:
    return AgentToolError.invalid_request("account_ids 형식이 올바르지 않습니다.")


async def _resolve_balance(account: Account) -> int:
    """계좌 잔액. 모드 분기와 계정계 404 처리는 balance_reader 가 담당한다."""
    return await read_balance(account)


async def query_balances(
    session: AsyncSession,
    context: ResolvedExecutionContext,
    account_ids: list[str],
) -> BalanceQueryData:
    """복수 계좌 잔액을 조회한다. 소유권 검증 실패 시 전체 거절(계약 10.4)."""
    parsed = parse_uuid_list(account_ids, _invalid_account_ids)
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
