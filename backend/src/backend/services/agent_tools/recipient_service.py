"""수취인 자동 확정 로직 (#5, 계약 13장 / D5).

영속 recipients 테이블 없이, 사용자의 **실행 완료된 타인송금 Confirmation** 의
`fixed_data`(recipient_account_id·recipient_name)를 이력 원천으로 사용한다.
자동 확정 규칙(계약 13.5):
- 이름 정규화 후 정확히 일치하는 결과만 사용(부분 일치·유사 검색 미사용)
- 동일 수취 계좌의 반복 거래는 하나로 중복 제거
- 사용할 수 없는 수취인(계좌 소실·비활성) 제외
- 남은 고유 수취인이 정확히 하나일 때만 resolved

TODO(계정계): 거래 이력에 상대방 정보가 생기면 계정계 이력 기반으로 위임 가능(9.1절).
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ...repository.account_repository import get_account_by_id
from ...repository.confirmation_repository import get_executed_external_transfers
from ...schemas.agent_tools.recipient import (
    RecipientResolveData,
    RecipientResolveRequest,
    ResolveOutcome,
    SelectionReason,
)
from ...schemas.execution_context import ResolvedExecutionContext


def normalize_person_name(name: str) -> str:
    """이름 정규화: 모든 공백 제거 + 소문자. 정확 일치 비교 전용(계약 13.5)."""
    return "".join(name.split()).lower()


async def resolve_recipient(
    session: AsyncSession,
    context: ResolvedExecutionContext,
    req: RecipientResolveRequest,
) -> RecipientResolveData:
    """이름 힌트를 기존 거래 수취인 하나로 확정할 수 있는지 판단한다."""
    hint = normalize_person_name(req.recipient_name_hint)
    executed = await get_executed_external_transfers(session, context.user_id)

    # fixed_data 에서 수취인 참조 추출 + 이름 정확 일치 + 계좌 단위 중복 제거.
    matched_account_ids: set[str] = set()
    for confirmation in executed:
        fixed = confirmation.fixed_data
        account_id = fixed.get("recipient_account_id")
        name = fixed.get("recipient_name")
        if not account_id or not name:
            continue
        if normalize_person_name(str(name)) != hint:
            continue
        matched_account_ids.add(str(account_id))

    # 사용할 수 없거나 제한된 수취인 제외(계좌 소실·비활성).
    usable: list[str] = []
    for account_id in matched_account_ids:
        account = await get_account_by_id(session, UUID(account_id))
        if account is not None and account.active:
            usable.append(account_id)

    if len(usable) == 1:
        return RecipientResolveData(outcome=ResolveOutcome.RESOLVED, to_recipient_id=usable[0])
    return RecipientResolveData(
        outcome=ResolveOutcome.SELECTION_REQUIRED,
        selection_reason=(SelectionReason.MULTIPLE_MATCHES if usable else SelectionReason.NO_MATCH),
    )
