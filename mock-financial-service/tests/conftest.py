"""Test fixtures — in-memory SQLite with StaticPool (single connection shared)."""

import pytest
from fastapi.testclient import TestClient
from financial_service.app import create_app
from financial_service.database import Base, get_db
from financial_service.migrations import apply_audit_triggers
from sqlalchemy import create_engine
from sqlalchemy import event as sqla_event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


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
    testing_session = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)

    def override_get_db():
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c


# ── Canonical mock-data fixtures ───────────────────────────────────────────────
# These expose the shared canonical dataset (dicts) from financial_service.mock_data.
# Same dataset consumed by dev-DB seed, demo fixtures, and pytest tests.


@pytest.fixture()
def accounts() -> list[dict]:
    """Return canonical list of 5 Account dicts (no DB required)."""
    from financial_service.mock_data import MOCK_ACCOUNTS

    return list(MOCK_ACCOUNTS)


@pytest.fixture()
def cards() -> list[dict]:
    """Return canonical list of 5-10 Card dicts with valid account_id FKs."""
    from financial_service.mock_data import MOCK_CARDS

    return list(MOCK_CARDS)


@pytest.fixture()
def card_products() -> list[dict]:
    """Return canonical list of 20 CardProduct dicts (standalone, no Card FK)."""
    from financial_service.mock_data import MOCK_CARD_PRODUCTS

    return list(MOCK_CARD_PRODUCTS)
