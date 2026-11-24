"""Tiny startup migrations for SQLite — adds missing columns to existing tables.

This is intentionally simple. For a real product over time, switch to Alembic.
"""
from sqlalchemy import inspect, text
from app.core.db.session import engine


def _existing_columns(table: str) -> set[str]:
    insp = inspect(engine)
    if not insp.has_table(table):
        return set()
    return {c["name"] for c in insp.get_columns(table)}


def _add_column_if_missing(table: str, column: str, ddl: str) -> None:
    if column not in _existing_columns(table):
        with engine.begin() as conn:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
        print(f"[migrate] added {table}.{column}")


def ensure_schema() -> None:
    """Add user_id to existing tenant tables if running on an old DB."""
    insp = inspect(engine)

    # Tables exist only after create_all; if not yet, skip — create_all will set the new schema.
    if insp.has_table("documents"):
        _add_column_if_missing("documents", "user_id", "INTEGER")
        _add_column_if_missing("documents", "stored_size", "INTEGER DEFAULT 0")
        _add_column_if_missing("documents", "sha256", "VARCHAR(64) DEFAULT ''")
        _add_column_if_missing("documents", "compression", "VARCHAR(20) DEFAULT 'identity'")
    if insp.has_table("company_profile"):
        _add_column_if_missing("company_profile", "user_id", "INTEGER")
        # Move legacy single-company data into the new multi-company table once.
        # Keeping the old table makes this migration reversible and idempotent.
        if inspect(engine).has_table("companies"):
            legacy_cols = _existing_columns("company_profile")
            new_cols = _existing_columns("companies")
            copy_cols = sorted((legacy_cols & new_cols) - {"id"})
            if copy_cols:
                cols = ", ".join(copy_cols)
                select_values = []
                for col in copy_cols:
                    if col == "updated_at":
                        select_values.append("COALESCE(old.updated_at, CURRENT_TIMESTAMP)")
                    elif col in {"key_personnel", "past_projects"}:
                        select_values.append(f"COALESCE(old.{col}, '[]')")
                    elif col == "user_id":
                        select_values.append("old.user_id")
                    else:
                        select_values.append(f"COALESCE(old.{col}, '')")
                values = ", ".join(select_values)
                with engine.begin() as conn:
                    conn.execute(text(
                        f"INSERT INTO companies ({cols}) SELECT {values} FROM company_profile old "
                        "WHERE old.user_id IS NOT NULL AND NOT EXISTS "
                        "(SELECT 1 FROM companies new WHERE new.user_id = old.user_id)"
                    ))
    if insp.has_table("bids"):
        _add_column_if_missing("bids", "user_id", "INTEGER")
    if insp.has_table("past_bids"):
        _add_column_if_missing("past_bids", "user_id", "INTEGER")

    # Email verification columns on users (existing users default to verified=1 so they aren't blocked)
    if insp.has_table("users"):
        if "email_verified" not in _existing_columns("users"):
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE users ADD COLUMN email_verified BOOLEAN DEFAULT 1"))
                conn.execute(text("UPDATE users SET email_verified = 1 WHERE email_verified IS NULL"))
            print("[migrate] added users.email_verified (existing users marked verified)")
        _add_column_if_missing("users", "verification_code",         "VARCHAR")
        _add_column_if_missing("users", "verification_code_sent_at", "DATETIME")
