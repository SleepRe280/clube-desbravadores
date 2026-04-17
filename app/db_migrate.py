"""Adiciona colunas em bancos SQLite já existentes (create_all não altera tabelas)."""

from sqlalchemy import inspect, text

from app.extensions import db


def _sqlite_columns(engine, table: str) -> set:
    insp = inspect(engine)
    try:
        return {c["name"] for c in insp.get_columns(table)}
    except Exception:
        return set()


def migrate_sqlite_schema(app):
    uri = app.config.get("SQLALCHEMY_DATABASE_URI") or ""
    if "sqlite" not in uri:
        return

    engine = db.engine
    with app.app_context():
        member_cols = _sqlite_columns(engine, "members")
        for col, ddl in [
            ("cpf", "VARCHAR(14)"),
            ("blood_type", "VARCHAR(8)"),
            ("father_name", "VARCHAR(120)"),
            ("mother_name", "VARCHAR(120)"),
            ("emergency_contact_name", "VARCHAR(120)"),
            ("emergency_contact_phone", "VARCHAR(40)"),
            ("notebook_current", "VARCHAR(200)"),
            ("overall_performance", "INTEGER DEFAULT 0"),
            ("photo_filename", "VARCHAR(200)"),
            ("activities_30_json", "TEXT"),
            ("notebook_checklist_30_json", "TEXT"),
        ]:
            if col not in member_cols:
                with engine.connect() as conn:
                    conn.execute(text(f"ALTER TABLE members ADD COLUMN {col} {ddl}"))
                    conn.commit()
                member_cols.add(col)

        act_cols = _sqlite_columns(engine, "activity_records")
        if "completed" not in act_cols:
            with engine.connect() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE activity_records ADD COLUMN completed INTEGER DEFAULT 0"
                    )
                )
                conn.commit()


def ensure_users_email_verified_column(app):
    """Adiciona users.email_verified em bancos já existentes (SQLite ou PostgreSQL)."""
    uri = (app.config.get("SQLALCHEMY_DATABASE_URI") or "").lower()
    engine = db.engine
    insp = inspect(engine)
    try:
        cols = {c["name"] for c in insp.get_columns("users")}
    except Exception:
        return
    if "email_verified" in cols:
        return
    if "sqlite" in uri:
        ddl = "ALTER TABLE users ADD COLUMN email_verified INTEGER NOT NULL DEFAULT 1"
    else:
        ddl = "ALTER TABLE users ADD COLUMN email_verified BOOLEAN NOT NULL DEFAULT TRUE"
    with engine.connect() as conn:
        conn.execute(text(ddl))
        conn.commit()
