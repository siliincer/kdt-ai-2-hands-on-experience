"""
DB-level migrations: audit log immutability triggers and analytics views.

SQLite:  CREATE TRIGGER ... RAISE(ABORT, ...)
Postgres: BEFORE UPDATE/DELETE trigger function
(DDL executed when dialect is postgresql)

Analytics views (정보계 read-only access):
  v_infobank_account_balances  — canonical balance per account
  v_infobank_ledger_entries    — denormalized ledger entry rows

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


def apply_snapshot_schema(engine: Engine) -> None:
    """Create read-only view joining accounts with balance_snapshots for 정보계 access.

    View: v_account_snapshots
    Shows cached balance, watermark, and refresh timestamp per account.
    LEFT JOIN — accounts without a snapshot appear with NULL cached fields.
    Idempotent: CREATE VIEW IF NOT EXISTS / CREATE OR REPLACE VIEW.
    """
    dialect = engine.dialect.name
    if dialect == "sqlite":
        ddl = """
        CREATE VIEW IF NOT EXISTS v_account_snapshots AS
        SELECT
            a.account_id,
            a.owner,
            a.currency,
            a.created_at,
            COALESCE(bs.cached_balance, 0)  AS cached_balance,
            COALESCE(bs.sum_credit, 0)       AS sum_credit,
            COALESCE(bs.sum_debit, 0)        AS sum_debit,
            bs.last_entry_rowid,
            bs.refreshed_at
        FROM accounts a
        LEFT JOIN balance_snapshots bs ON a.account_id = bs.account_id
        """
    elif dialect == "postgresql":
        ddl = """
        CREATE OR REPLACE VIEW v_account_snapshots AS
        SELECT
            a.account_id,
            a.owner,
            a.currency,
            a.created_at,
            COALESCE(bs.cached_balance, 0)  AS cached_balance,
            COALESCE(bs.sum_credit, 0)       AS sum_credit,
            COALESCE(bs.sum_debit, 0)        AS sum_debit,
            bs.last_entry_rowid,
            bs.refreshed_at
        FROM accounts a
        LEFT JOIN balance_snapshots bs ON a.account_id = bs.account_id
        """
    else:
        return  # no-op for other dialects

    with engine.connect() as conn:
        conn.execute(text(ddl))
        conn.commit()


def apply_analytics_views(engine: Engine) -> None:
    """Create read-only views for 정보계 (downstream analytics) access.

    Views:
      v_infobank_account_balances  — canonical balance (SUM CREDIT − SUM DEBIT),
                                     sum_credit, sum_debit, entry_count per account.
      v_infobank_ledger_entries    — denormalized ledger entries with account metadata.

    Both views are CREATE ... IF NOT EXISTS → idempotent on repeated startup.
    """
    dialect = engine.dialect.name
    if dialect == "sqlite":
        _apply_sqlite_views(engine)
    elif dialect == "postgresql":
        _apply_postgres_views(engine)
    # other dialects: no-op


def _apply_sqlite_views(engine: Engine) -> None:
    views = [
        """
        CREATE VIEW IF NOT EXISTS v_infobank_account_balances AS
        SELECT
            a.account_id,
            a.owner,
            a.currency,
            a.created_at,
            COALESCE(SUM(CASE WHEN le.entry_type = 'CREDIT' THEN le.amount ELSE 0 END), 0)
                - COALESCE(SUM(CASE WHEN le.entry_type = 'DEBIT'  THEN le.amount ELSE 0 END), 0)
                AS balance,
            COALESCE(SUM(CASE WHEN le.entry_type = 'CREDIT' THEN le.amount ELSE 0 END), 0)
                AS sum_credit,
            COALESCE(SUM(CASE WHEN le.entry_type = 'DEBIT'  THEN le.amount ELSE 0 END), 0)
                AS sum_debit,
            COUNT(le.entry_id) AS entry_count
        FROM accounts a
        LEFT JOIN ledger_entries le ON le.account_id = a.account_id
        GROUP BY a.account_id, a.owner, a.currency, a.created_at
        """,
        """
        CREATE VIEW IF NOT EXISTS v_infobank_ledger_entries AS
        SELECT
            le.entry_id,
            le.account_id,
            a.owner,
            a.currency,
            le.transaction_id,
            le.entry_type,
            le.amount,
            le.running_balance,
            le.created_at
        FROM ledger_entries le
        JOIN accounts a ON a.account_id = le.account_id
        """,
    ]
    with engine.connect() as conn:
        for ddl in views:
            conn.execute(text(ddl))
        conn.commit()


def _apply_postgres_views(engine: Engine) -> None:
    """Postgres equivalents using CREATE OR REPLACE VIEW."""
    views = [
        """
        CREATE OR REPLACE VIEW v_infobank_account_balances AS
        SELECT
            a.account_id,
            a.owner,
            a.currency,
            a.created_at,
            COALESCE(SUM(CASE WHEN le.entry_type = 'CREDIT' THEN le.amount ELSE 0 END), 0)
                - COALESCE(SUM(CASE WHEN le.entry_type = 'DEBIT'  THEN le.amount ELSE 0 END), 0)
                AS balance,
            COALESCE(SUM(CASE WHEN le.entry_type = 'CREDIT' THEN le.amount ELSE 0 END), 0)
                AS sum_credit,
            COALESCE(SUM(CASE WHEN le.entry_type = 'DEBIT'  THEN le.amount ELSE 0 END), 0)
                AS sum_debit,
            COUNT(le.entry_id) AS entry_count
        FROM accounts a
        LEFT JOIN ledger_entries le ON le.account_id = a.account_id
        GROUP BY a.account_id, a.owner, a.currency, a.created_at
        """,
        """
        CREATE OR REPLACE VIEW v_infobank_ledger_entries AS
        SELECT
            le.entry_id,
            le.account_id,
            a.owner,
            a.currency,
            le.transaction_id,
            le.entry_type,
            le.amount,
            le.running_balance,
            le.created_at
        FROM ledger_entries le
        JOIN accounts a ON a.account_id = le.account_id
        """,
    ]
    with engine.connect() as conn:
        for ddl in views:
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
