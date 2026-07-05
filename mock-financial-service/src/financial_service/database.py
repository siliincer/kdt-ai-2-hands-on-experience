"""Database engine and session configuration."""

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_URL = "sqlite:///./financial.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)


# Enable WAL mode and foreign keys via SQLAlchemy event (not raw PRAGMA in query layer)
@event.listens_for(engine, "connect")
def set_sqlite_options(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
