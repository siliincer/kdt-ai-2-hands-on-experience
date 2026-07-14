"""Programmatic `alembic upgrade head` — run automatically on server startup.

Replaces the old `Base.metadata.create_all()` startup hook. create_all() only
creates tables that don't exist yet; it never alters existing ones, so a
schema change (new column, etc.) silently had no effect on an already-seeded
`financial.db` until someone manually deleted the file and reseeded. Running
the real migration chain on every startup keeps the on-disk schema in sync
with models.py automatically, without dropping existing data (unlike a
drop_all()+create_all() reset).
"""

from pathlib import Path

from alembic import command
from alembic.config import Config

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_ALEMBIC_INI = _PROJECT_ROOT / "alembic.ini"
# Named "alembic_migrations", not "alembic" — a directory literally named
# `alembic` sitting on sys.path (e.g. cwd == mock-financial-service/) shadows
# the installed `alembic` pip package and breaks `from alembic import command`.
_ALEMBIC_SCRIPT_LOCATION = _PROJECT_ROOT / "alembic_migrations"


def run_migrations(database_url: str | None = None) -> None:
    """Upgrade a DB to the latest revision (defaults to database.DATABASE_URL).

    database_url lets callers (e.g. scripts/seed_dev_db.py) target an
    alternate SQLite file — the migration chain still applies, so that DB
    also ends up with the `alembic_version` table stamped, and won't collide
    with a real `alembic upgrade head` run against it later.
    """
    cfg = Config(str(_ALEMBIC_INI))
    cfg.set_main_option("script_location", str(_ALEMBIC_SCRIPT_LOCATION))
    if database_url is not None:
        cfg.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(cfg, "head")
