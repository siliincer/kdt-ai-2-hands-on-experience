"""데모용 — 특정 유저의 기본 출금 계좌 지정을 전부 해제한다.

기본 계좌가 하나도 없는 상태를 재현해서 "기본 계좌 미설정 시 계좌 선택 화면이
뜨고, 설정 후에는 바로 넘어간다"는 데모 시나리오를 보여줄 때 쓴다. is_default는
DB에 유일성 제약이 없는 평범한 boolean이라 전부 false로 둬도 안전하다.

사용법:
    cd backend && uv run python scripts/unset_default_account.py qa1@email.com
"""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import select, update

from backend.db.postgres import AsyncSessionLocal
from backend.models.account import Account
from backend.models.user import User


async def main(email: str) -> None:
    async with AsyncSessionLocal() as session:
        user = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if user is None:
            print(f"[unset_default_account] 유저를 찾을 수 없습니다: {email}")
            return

        result = await session.execute(
            update(Account).where(Account.user_id == user.id, Account.is_default.is_(True)).values(is_default=False)
        )
        await session.commit()
        print(f"[unset_default_account] {email}: 기본 계좌 {result.rowcount}개 해제 완료.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("사용법: uv run python scripts/unset_default_account.py <email>")
        raise SystemExit(1)
    asyncio.run(main(sys.argv[1]))
