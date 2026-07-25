"""통합 데모 시나리오용 전용 시드 스크립트.

기존 QA 페르소나(seed_qa_personas.py, qa1/qa2/qa3)는 다른 팀원의 QA·e2e 테스트가
그 고정 계좌 구성에 의존하므로 건드리지 않는다. 데모는 별도 로그인
(demo@email.com)으로 분리해서, 발표 중 실수로 기존 QA 상태를 깨뜨리지 않는다.

준비하는 것:
- 데모 사용자 김지훈: 신한은행 5,300,000 / 국민은행 2,000,000 / 토스뱅크 8,000,000,
  기본 출금 계좌는 미설정(장면5에서 발표 중 직접 설정하는 게 데모 포인트다).
- 고유 수취인 홍길동 1명(완료된 타인송금 이력 1건).
- 동명이인 수취인 김민수 2명(국민은행·신한은행 각 1건 완료 이력) — 이름 자동확정이
  "여러 후보라 선택 필요"로 분기하는 걸 보여주기 위함.

주의(발표 전 확인 사항, 코드로 못 채우는 갭):
- mock-financial-service 거래내역 데이터셋(mock_data.py)은 2026-07-10까지만
  고정돼 있어 "이번 달" 조회 시나리오(장면10~12)는 이 데모 계좌로는 재현 안 된다.
  거래내역/배민 지출 장면은 기존 QA 페르소나 중 데이터가 있는 과거월로 대체하거나
  발표에서 스킵한다.
- 동명이인 후보를 이름·은행·마스킹계좌로 나열해 보여주는 화면은 현재 Agent가
  이 후보 목록을 프론트로 안 보내서(recent_recipients 미채움) 실제로는 "최근 수취인
  없음 + 계좌번호 직접 입력" 화면만 뜬다. "선택 필요"로 분기하는 것 자체는 이 시드로
  재현되니, 화면 목업과 다르다는 점만 발표 중 구두로 짚고 넘어간다.

재실행해도 안전하다(이메일/은행명 기준으로 이미 있으면 건너뛴다).

사용법:
    cd backend && uv run python scripts/seed_demo_scenario.py
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from backend.core.load_environment_var import settings
from backend.core.security import get_password_hash
from backend.db.postgres import AsyncSessionLocal
from backend.models.account import Account
from backend.models.chat_session import ChatSession
from backend.models.confirmation import Confirmation, ConfirmationOperation, ConfirmationStatus
from backend.models.execution_context import ExecutionContext, ExecutionContextStatus
from backend.models.user import User
from backend.repository.user_repository import get_user_by_email
from backend.services.financial.financial_client import get_financial_client

# 비밀번호는 여기 상수만 바꾸면 다음 실행부터 바로 반영된다(min_length=8 필요).
_PASSWORD = "12345678"  # lgtm[py/hardcoded-credentials]

_DEMO_USER_EMAIL = "demo@email.com"
_DEMO_USER_NAME = "김지훈"

# (bank_name, alias, initial_balance) — 기본 출금 계좌는 만들지 않는다(데모 장면5 포인트).
_DEMO_ACCOUNTS: list[tuple[str, str, int]] = [
    ("신한은행", "급여 계좌", 5_300_000),
    ("국민은행", "비상금 계좌", 2_000_000),
    ("토스뱅크", "저축 계좌", 8_000_000),
]

# 수취인 placeholder 유저 — 로그인 용도가 아니라 Account.user_id FK를 채우기 위함.
_RECIPIENTS: list[dict[str, str]] = [
    {
        "email": "demo-recipient-honggildong@email.internal",
        "name": "홍길동",
        "bank_name": "우리은행",
        "recipient_name": "홍길동",
    },
    {
        "email": "demo-recipient-kimminsu-kb@email.internal",
        "name": "김민수",
        "bank_name": "국민은행",
        "recipient_name": "김민수",
    },
    {
        "email": "demo-recipient-kimminsu-shinhan@email.internal",
        "name": "김민수",
        "bank_name": "신한은행",
        "recipient_name": "김민수",
    },
]


async def _get_or_create_user(session, email: str, name: str) -> User:
    user = await get_user_by_email(session, email)
    if user is not None:
        return user
    user = User(email=email, password_hash=get_password_hash(_PASSWORD), name=name)
    session.add(user)
    await session.flush()
    return user


async def _get_account_by_bank(session, user_id, bank_name: str) -> Account | None:
    stmt = select(Account).where(Account.user_id == user_id, Account.bank_name == bank_name)
    result = await session.execute(stmt)
    return result.scalars().first()


async def _ensure_account(
    session,
    *,
    user: User,
    bank_name: str,
    alias: str,
    initial_balance: int,
) -> Account:
    """이미 해당 은행 계좌가 있으면 재사용, 없으면 계정계에 새로 만들어 매핑한다."""
    existing = await _get_account_by_bank(session, user.id, bank_name)
    if existing is not None:
        return existing

    created = await get_financial_client().create_account(
        owner=user.name or user.email,
        initial_balance=initial_balance,
        bank_name=bank_name,
    )
    account = Account(
        user_id=user.id,
        external_account_id=created["account_id"],
        account_number=created["account_number"],
        bank_name=created.get("bank_name") or bank_name,
        balance=created.get("balance", initial_balance),
        currency=created.get("currency", "KRW"),
        active=True,
        alias=alias,
        account_type="checking",
        is_default=False,
    )
    session.add(account)
    await session.flush()
    return account


async def _ensure_recipient_history(
    session,
    *,
    sender: User,
    from_account: Account,
    recipient_account: Account,
    recipient_name: str,
    amount: int,
) -> None:
    """수취인 자동확정(#5, resolve_recipient) 테스트용 완료된 타인송금 이력을 만든다.

    Backend는 "실행 완료된 타인송금 Confirmation"의 fixed_data(recipient_account_id·
    recipient_name)를 이력 원천으로 쓴다(영속 recipients 테이블 없음, D5).
    """
    stmt = select(Confirmation).where(
        Confirmation.user_id == sender.id,
        Confirmation.status == ConfirmationStatus.EXECUTED,
        Confirmation.operation == ConfirmationOperation.EXTERNAL_TRANSFER,
    )
    result = await session.execute(stmt)
    for existing in result.scalars().all():
        if existing.fixed_data.get("recipient_account_id") == str(recipient_account.id):
            return  # 이미 있음(재실행 안전)

    now = datetime.now(timezone.utc)
    chat_session = ChatSession(user_id=sender.id)
    session.add(chat_session)
    await session.flush()

    execution_context = ExecutionContext(
        user_id=sender.id,
        chat_session_id=chat_session.id,
        scopes=["account:read", "transfer:request", "settings:write"],
        status=ExecutionContextStatus.COMPLETED,
        expires_at=now + timedelta(hours=1),
    )
    session.add(execution_context)
    await session.flush()

    confirmation = Confirmation(
        execution_context_id=execution_context.id,
        user_id=sender.id,
        operation=ConfirmationOperation.EXTERNAL_TRANSFER,
        status=ConfirmationStatus.EXECUTED,
        fixed_data={
            "from_account_id": str(from_account.id),
            "recipient_account_id": str(recipient_account.id),
            "recipient_name": recipient_name,
            "amount": amount,
            "fee": 0,
            "currency": "KRW",
        },
        expires_at=now - timedelta(days=3) + timedelta(hours=1),
        approved_at=now - timedelta(days=3),
        executed_at=now - timedelta(days=3),
    )
    session.add(confirmation)


async def main() -> None:
    base_url = settings.MOCK_FINANCIAL_SERVICE_URL
    async with AsyncSessionLocal() as session:
        demo_user = await _get_or_create_user(session, _DEMO_USER_EMAIL, _DEMO_USER_NAME)

        demo_accounts: list[Account] = []
        for bank_name, alias, balance in _DEMO_ACCOUNTS:
            account = await _ensure_account(
                session,
                user=demo_user,
                bank_name=bank_name,
                alias=alias,
                initial_balance=balance,
            )
            demo_accounts.append(account)
        shinhan_account = next(a for a in demo_accounts if a.bank_name == "신한은행")

        recipient_accounts: dict[str, Account] = {}
        for spec in _RECIPIENTS:
            recipient_user = await _get_or_create_user(session, spec["email"], spec["name"])
            recipient_account = await _ensure_account(
                session,
                user=recipient_user,
                bank_name=spec["bank_name"],
                alias=f"{spec['name']} 계좌",
                initial_balance=0,
            )
            recipient_accounts[spec["email"]] = recipient_account

        # 각 수취인에게 1건씩 완료 이력을 남겨 이름 자동확정이 동작하게 한다.
        # 출금 계좌는 아무 계좌나 상관없다(신한은행 계좌 사용) — 기본 출금 계좌
        # 자체는 데모 장면5에서 발표 중 직접 설정하므로 여기서는 미설정 유지.
        for spec in _RECIPIENTS:
            await _ensure_recipient_history(
                session,
                sender=demo_user,
                from_account=shinhan_account,
                recipient_account=recipient_accounts[spec["email"]],
                recipient_name=spec["recipient_name"],
                amount=30_000,
            )

        await session.commit()

    print("[seed_demo_scenario] 완료.")
    print(f"  로그인: {_DEMO_USER_EMAIL} / [REDACTED]")
    print("  계좌: 신한은행 5,300,000 / 국민은행 2,000,000 / 토스뱅크 8,000,000 (기본계좌 미설정)")
    print("  수취인: 홍길동(고유), 김민수 x2(국민은행/신한은행, 동명이인)")
    print(f"  mock-financial-service: {base_url}")


if __name__ == "__main__":
    asyncio.run(main())
