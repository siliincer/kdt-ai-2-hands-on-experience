"""chat_sessions 소유권 검증 / 부트스트랩 (비즈니스 로직).

SSE 티켓 발급(sse_api)과 Chat API(chat_api)가 공유한다.
DB 접근은 repository(chat_repository)에 위임하고, 여기서는 검증·오케스트레이션만 한다.
SSE connect 핸들러는 DB를 쓰지 않으므로 소유권 검증은 이 요청 계층에서 끝낸다.
"""

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..repository.chat_repository import create_chat_session, get_chat_session


async def resolve_chat_session(
    session: AsyncSession, user_id: UUID, chat_session_id: UUID | None
) -> UUID:
    """chat_session_id 를 확정한다.

    - 주어지면: 이 유저 소유인지 검증(불일치 → 404).
    - 없으면: 유저용 chat_sessions row 를 새로 만들어 부트스트랩.
    """
    if chat_session_id is not None:
        await _assert_owner(session, user_id, chat_session_id)
        return chat_session_id

    new_session = await create_chat_session(session, user_id)
    return new_session.id


async def verify_chat_session_owner(
    session: AsyncSession, user_id: UUID, chat_session_id: UUID
) -> None:
    """기존 세션의 소유권만 검증(생성하지 않음). approve 등에서 사용."""
    await _assert_owner(session, user_id, chat_session_id)


async def _assert_owner(
    session: AsyncSession, user_id: UUID, chat_session_id: UUID
) -> None:
    if await get_chat_session(session, chat_session_id, user_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="해당 대화 세션을 찾을 수 없습니다.",
        )
