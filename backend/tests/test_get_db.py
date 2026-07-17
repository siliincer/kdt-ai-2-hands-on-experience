"""get_db 의존성의 예외 방어 검증 (R1).

DB 없이 AsyncSessionLocal 을 가짜로 대체해, yield 이후 예외가 나면 rollback 후
재전파되고 세션 close(풀 반환)가 항상 호출되는지 확인한다.
"""

import pytest

import backend.db.postgres as postgres


class _FakeSession:
    def __init__(self) -> None:
        self.rolled_back = False
        self.committed = False
        self.closed = False  # CM __aexit__ 가 세팅(세션 close = 풀 반환)

    async def rollback(self) -> None:
        self.rolled_back = True

    async def commit(self) -> None:
        self.committed = True


class _FakeSessionCM:
    """async with AsyncSessionLocal() as session 을 흉내낸다."""

    def __init__(self, session: _FakeSession) -> None:
        self._session = session

    async def __aenter__(self) -> _FakeSession:
        return self._session

    async def __aexit__(self, *exc) -> bool:
        self._session.closed = True
        return False  # 예외를 삼키지 않는다(그대로 전파)


@pytest.fixture
def fake_session(monkeypatch):
    session = _FakeSession()
    monkeypatch.setattr(postgres, "AsyncSessionLocal", lambda: _FakeSessionCM(session))
    return session


@pytest.mark.asyncio
async def test_exception_triggers_rollback_and_reraises(fake_session):
    gen = postgres.get_db()
    await gen.__anext__()  # yield 지점까지 진행

    with pytest.raises(ValueError):
        # 라우터/서비스에서 예외가 난 상황을 재현.
        await gen.athrow(ValueError("boom"))

    assert fake_session.rolled_back is True
    assert fake_session.committed is False
    assert fake_session.closed is True  # 세션 close(풀 반환) 보장


@pytest.mark.asyncio
async def test_normal_flow_does_not_rollback(fake_session):
    gen = postgres.get_db()
    await gen.__anext__()

    with pytest.raises(StopAsyncIteration):
        await gen.__anext__()  # 정상 종료

    assert fake_session.rolled_back is False
    assert fake_session.closed is True
