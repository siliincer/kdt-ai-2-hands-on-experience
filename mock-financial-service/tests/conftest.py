"""Test fixtures — in-memory SQLite with StaticPool (single connection shared)."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event as sqla_event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from financial_service.database import Base, get_db
from financial_service.app import create_app
from financial_service.migrations import apply_audit_triggers


@pytest.fixture()
def db_engine():
    # StaticPool: all sessions share one in-memory connection
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @sqla_event.listens_for(engine, "connect")
    def set_pragma(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(bind=engine)
    apply_audit_triggers(engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture()
def client(db_engine):
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
