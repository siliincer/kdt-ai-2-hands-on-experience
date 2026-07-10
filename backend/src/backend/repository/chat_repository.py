from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.chat_message import ChatMessage
from ..models.chat_session import ChatSession


async def get_chat_session(
    session: AsyncSession, chat_session_id: UUID, user_id: UUID
) -> ChatSession | None:
    stmt = select(ChatSession).where(
        ChatSession.id == chat_session_id,
        ChatSession.user_id == user_id,
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def create_chat_session(session: AsyncSession, user_id: UUID) -> ChatSession:
    chat_session = ChatSession(user_id=user_id)
    session.add(chat_session)
    await session.commit()
    await session.refresh(chat_session)
    return chat_session


async def add_chat_message(
    session: AsyncSession, session_id: UUID, role: str, message: str
) -> ChatMessage:
    chat_message = ChatMessage(session_id=session_id, role=role, message=message)
    session.add(chat_message)
    await session.commit()
    await session.refresh(chat_message)
    return chat_message
