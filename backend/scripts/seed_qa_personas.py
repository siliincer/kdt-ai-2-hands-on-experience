"""QA 테스트용 페르소나 유저를 mock-financial-service 계좌에 연결한다.

mock-financial-service(계정계)의 시드 페르소나(김지훈/박서연/최수아)를 backend 로컬
유저로 만들고 accounts 테이블에 매핑한다. 은행명/계좌번호/잔액은 하드코딩하지 않고
mock-financial-service를 직접 조회해서 채운다 — 계정계 쪽 은행명을 바꿔서 테스트하고
있어도(예: KDT은행 -> 신한은행) 항상 실제 값과 일치하게 재현된다.

QA 재현 목적 전용 스크립트다. 비밀번호는 데모용 평문 상수라 운영 환경에서 절대
재사용하면 안 된다 — 로컬 개발 DB에서만 실행한다.

사전 조건:
- mock-financial-service가 로컬에서 떠 있어야 한다(기본 http://localhost:8002).
- Postgres에 backend 마이그레이션이 최신까지 적용돼 있어야 한다.

사용법:
    cd backend && uv run python scripts/seed_qa_personas.py

재실행해도 안전하다(이메일/external_account_id 기준으로 있으면 갱신만 한다).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import httpx
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

# 계정계(mock-financial-service)의 실제 external_account_id — mock_data.py 시드 기준
# 고정값이다(persona 5명 + 김지훈 부계좌 2개, docs/qa-workflow-e2e-test-report.md 참고).
_ACCOUNT_ID_KIMJIHUN = "acct-0001-0000-0000-000000000001"
_ACCOUNT_ID_KIMJIHUN_SHINHAN_SUB = "acct-0001-0000-0000-000000000011"
_ACCOUNT_ID_KIMJIHUN_HANA_SUB = "acct-0001-0000-0000-000000000012"
_ACCOUNT_ID_PARKSEOYEON = "acct-0002-0000-0000-000000000002"
_ACCOUNT_ID_CHOISUA = "acct-0004-0000-0000-000000000004"

# 비밀번호는 여기 상수만 바꾸면 다음 실행부터 바로 반영된다(min_length=8 필요).
_PASSWORD = "12345678"

_PERSONAS: list[dict[str, str | bool]] = [
    {
        "email": "qa1@email.com",
        "name": "김지훈",
        "external_account_id": _ACCOUNT_ID_KIMJIHUN,
        "alias": "김지훈 주계좌",
        "is_default": True,
    },
    {
        "email": "qa1@email.com",
        "name": "김지훈",
        "external_account_id": _ACCOUNT_ID_KIMJIHUN_SHINHAN_SUB,
        "alias": "신한 부계좌",
        "is_default": False,
    },
    {
        "email": "qa1@email.com",
        "name": "김지훈",
        "external_account_id": _ACCOUNT_ID_KIMJIHUN_HANA_SUB,
        "alias": "하나 부계좌",
        "is_default": False,
    },
    {
        "email": "qa2@email.com",
        "name": "박서연",
        "external_account_id": _ACCOUNT_ID_PARKSEOYEON,
        "alias": "박서연 주계좌",
        "is_default": True,
    },
    {
        "email": "qa3@email.com",
        "name": "최수아",
        "external_account_id": _ACCOUNT_ID_CHOISUA,
        "alias": "최수아 주계좌",
        "is_default": True,
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


async def _fetch_ledger_account(client: httpx.AsyncClient, external_account_id: str) -> dict:
    response = await client.get(f"/api/v1/accounts/{external_account_id}")
    response.raise_for_status()
    return response.json()


async def _upsert_account(session, *, user_id, ledger: dict, alias: str, is_default: bool) -> Account:
    stmt = select(Account).where(Account.external_account_id == ledger["account_id"])
    result = await session.execute(stmt)
    account = result.scalar_one_or_none()
    if account is None:
        account = Account(
            user_id=user_id,
            external_account_id=ledger["account_id"],
            account_number=ledger["account_number"],
            bank_name=ledger["bank_name"],
            balance=ledger["balance"],
            currency=ledger.get("currency", "KRW"),
            active=True,
            alias=alias,
            account_type="checking",
            is_default=is_default,
        )
        session.add(account)
        await session.flush()
        return account
    account.user_id = user_id
    account.account_number = ledger["account_number"]
    account.bank_name = ledger["bank_name"]
    account.balance = ledger["balance"]
    account.alias = alias
    account.is_default = is_default
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
    recipient_name)를 이력 원천으로 쓴다(영속 recipients 테이블 없음, D5). 이게 없으면
    "OO에게 송금해줘" 발화가 항상 수취인 선택 화면부터 다시 시작한다.
    """
    stmt = select(Confirmation).where(
        Confirmation.user_id == sender.id,
        Confirmation.status == ConfirmationStatus.EXECUTED,
        Confirmation.operation == ConfirmationOperation.EXTERNAL_TRANSFER,
    )
    result = await session.execute(stmt)
    for existing in result.scalars().all():
        if existing.fixed_data.get("recipient_name") == recipient_name:
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
    async with httpx.AsyncClient(base_url=base_url, timeout=10.0) as client, AsyncSessionLocal() as session:
        users_by_email: dict[str, User] = {}
        default_accounts_by_email: dict[str, Account] = {}
        for persona in _PERSONAS:
            email = str(persona["email"])
            if email not in users_by_email:
                users_by_email[email] = await _get_or_create_user(session, email, str(persona["name"]))
            user = users_by_email[email]

            ledger = await _fetch_ledger_account(client, str(persona["external_account_id"]))
            account = await _upsert_account(
                session,
                user_id=user.id,
                ledger=ledger,
                alias=str(persona["alias"]),
                is_default=bool(persona["is_default"]),
            )
            if persona["is_default"]:
                default_accounts_by_email[email] = account

        # 김지훈 -> 박서연 수취인 자동확정용 완료 이력("박서연에게 송금해줘"가 바로
        # 승인 단계로 가도록). 두 계좌가 이번에 준비됐을 때만 만든다.
        kimjihun_account = default_accounts_by_email.get("qa1@email.com")
        parkseoyeon_account = default_accounts_by_email.get("qa2@email.com")
        if kimjihun_account is not None and parkseoyeon_account is not None:
            await _ensure_recipient_history(
                session,
                sender=users_by_email["qa1@email.com"],
                from_account=kimjihun_account,
                recipient_account=parkseoyeon_account,
                recipient_name="박서연",
                amount=30000,
            )

        await session.commit()

    print("[seed_qa_personas] 완료. 로그인 정보(비밀번호 전부 동일):")
    print(f"  password: {_PASSWORD}")
    for email in dict.fromkeys(str(p["email"]) for p in _PERSONAS):
        print(f"  - {email}")


if __name__ == "__main__":
    asyncio.run(main())
