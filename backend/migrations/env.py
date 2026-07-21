from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

import backend.models  # noqa: F401
from backend.core.load_environment_var import settings

# 🌟 이 한 줄로 __init__.py 안의 모든 모델 클래스가 메모리에 등록됩니다.
# Import the model modules so their tables and metadata are registered.
from backend.db.postgres import Base

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# 🌟 pydantic-settings에서 읽어온 실제 DB URL을 Alembic 설정에 강제로 주입합니다.
# Alembic env.py는 동기 커넥션(connectable.connect())을 쓰므로, 앱이 쓰는 비동기
# asyncpg 드라이버 그대로 넘기면 greenlet 컨텍스트 없이 await_only()가 호출되어
# MissingGreenlet 에러가 난다. 마이그레이션 전용으로 동기 드라이버(psycopg2)로 치환.
sync_url = settings.DATABASE_URL.replace("postgresql+asyncpg", "postgresql+psycopg2")
config.set_main_option("sqlalchemy.url", sync_url)

# Interpret the config file for Python logging.
# this is basically a fileConfig object.
# disable_existing_loggers=False: run_migrations() 는 앱 lifespan(startup)에서도
# 호출되는데, 기본값(True)이면 이미 설정된 uvicorn.access 로거까지 꺼뜨려 접근 로그
# (200 라인)가 사라진다. 마이그레이션 로깅만 설정하고 기존 로거는 보존한다.
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

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
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
