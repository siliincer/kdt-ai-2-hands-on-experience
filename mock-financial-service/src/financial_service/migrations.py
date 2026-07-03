"""
DB-level audit log immutability triggers.

SQLite:  CREATE TRIGGER ... RAISE(ABORT, ...)
Postgres: BEFORE UPDATE/DELETE trigger function (DDL executed when dialect is postgresql)

Called once at startup after Base.metadata.create_all().
"""
from sqlalchemy import text
from sqlalchemy.engine import Engine


def apply_audit_triggers(engine: Engine) -> None:
    dialect = engine.dialect.name

    if dialect == "sqlite":
        _apply_sqlite_triggers(engine)
    elif dialect == "postgresql":
        _apply_postgres_triggers(engine)
    # other dialects: no-op (add as needed)


def _apply_sqlite_triggers(engine: Engine) -> None:
    triggers = [
        """
        CREATE TRIGGER IF NOT EXISTS audit_logs_no_update
        BEFORE UPDATE ON audit_logs
        BEGIN
            SELECT RAISE(ABORT, 'audit_logs is append-only: UPDATE forbidden');
        END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS audit_logs_no_delete
        BEFORE DELETE ON audit_logs
        BEGIN
            SELECT RAISE(ABORT, 'audit_logs is append-only: DELETE forbidden');
        END
        """,
    ]
    with engine.connect() as conn:
        for ddl in triggers:
            conn.execute(text(ddl))
        conn.commit()


def _apply_postgres_triggers(engine: Engine) -> None:
    """
    Postgres equivalent using a PL/pgSQL trigger function.
    Requires SERIALIZABLE isolation for full transfer integrity.
    """
    ddl = """
    CREATE OR REPLACE FUNCTION audit_logs_immutable()
    RETURNS TRIGGER LANGUAGE plpgsql AS $$
    BEGIN
        RAISE EXCEPTION 'audit_logs is append-only: % forbidden', TG_OP;
    END;
    $$;

    DROP TRIGGER IF EXISTS audit_logs_no_update ON audit_logs;
    CREATE TRIGGER audit_logs_no_update
    BEFORE UPDATE ON audit_logs
    FOR EACH ROW EXECUTE FUNCTION audit_logs_immutable();

    DROP TRIGGER IF EXISTS audit_logs_no_delete ON audit_logs;
    CREATE TRIGGER audit_logs_no_delete
    BEFORE DELETE ON audit_logs
    FOR EACH ROW EXECUTE FUNCTION audit_logs_immutable();
    """
    with engine.connect() as conn:
        conn.execute(text(ddl))
        conn.commit()
