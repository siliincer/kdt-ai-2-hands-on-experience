import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Make `financial_service` importable regardless of the cwd alembic was
# invoked from (mirrors the `sys.path.insert(0, "src")` trick used by
# scripts/seed_dev_db.py).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from financial_service import (
    models,  # noqa: E402,F401  (registers all tables on Base.metadata)
)
from financial_service.database import DATABASE_URL, Base  # noqa: E402

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Use the app's single source of truth for the DB URL (fixed absolute path,
# same one FastAPI connects to) — unless the caller already set one
# programmatically (migration_runtime.run_migrations(database_url=...) does
# this for scripts/seed_dev_db.py, which can target an alternate SQLite file).
if not config.get_main_option("sqlalchemy.url"):
    config.set_main_option("sqlalchemy.url", DATABASE_URL)

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# financial_service.models's classes register themselves on Base.metadata
# on import (above) — this is what `alembic revision --autogenerate` diffs
# against to detect model changes.
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # ── 수정된 부분: 오프라인 버전 테이블 이름 설정 ─────────────────────
        version_table="alembic_version_mock_financial_service",
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # ── 수정된 부분: 온라인 버전 테이블 이름 설정 ─────────────────────
            version_table="alembic_version_mock_financial_service",
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
