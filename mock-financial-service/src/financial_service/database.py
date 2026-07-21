"""Database engine and session configuration."""

from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# Fixed absolute path — independent of the current working directory the
# server happens to be launched from (root vs mock-financial-service/), so
# `financial.db` always lands in the same place instead of splitting into
# two different files depending on where `uvicorn`/pytest was invoked.
# Override with the DATABASE_URL env var for Postgres etc.
_DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent.parent / "financial.db"
DATABASE_URL = f"sqlite:///{_DEFAULT_DB_PATH}"
# 수정사항: database_url은 backend에서 쓰는 환경변수라서
# sqlite 경로는 하드코딩으로 대체했습니다.

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
