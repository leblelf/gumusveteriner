from __future__ import annotations

"""
Local SQLite verilerini Render PostgreSQL veritabanına bir kez taşır.

Kullanım:
    $env:DATABASE_URL="postgresql://..."
    python scripts/migrate_sqlite_to_postgres.py
"""

import os
import sqlite3
import sys
from pathlib import Path

import psycopg2
from psycopg2 import sql

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.postgres_adapter import POSTGRES_SCHEMA, _postgres_url  # noqa: E402


SQLITE_PATH = Path(os.environ.get("SQLITE_SOURCE_PATH") or ROOT / "data" / "gumus_veteriner.db")
DATABASE_URL = (os.environ.get("DATABASE_URL") or "").strip()

# Foreign key bağımlılıkları nedeniyle tablolar bu sırayla aktarılır.
TABLES = [
    "users",
    "admins",
    "products",
    "pets",
    "appointments",
    "sessions",
    "password_resets",
    "user_addresses",
    "pet_health_records",
    "appointment_reminders",
    "appointment_slots",
    "orders",
    "order_items",
    "contacts",
    "admin_login_attempts",
    "admin_audit_logs",
    "services",
    "site_texts",
    "site_reviews",
    "notifications",
]


def sqlite_columns(connection: sqlite3.Connection, table: str) -> list[str]:
    return [row["name"] for row in connection.execute(f"PRAGMA table_info({table})")]


def postgres_columns(cursor, table: str) -> set[str]:
    cursor.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
        """,
        (table,),
    )
    return {row[0] for row in cursor.fetchall()}


def migrate_table(sqlite_db: sqlite3.Connection, postgres_db, table: str) -> int:
    source_columns = sqlite_columns(sqlite_db, table)
    if not source_columns:
        return 0
    with postgres_db.cursor() as cursor:
        target_columns = postgres_columns(cursor, table)
        columns = [column for column in source_columns if column in target_columns]
        rows = sqlite_db.execute(f"SELECT {', '.join(columns)} FROM {table}").fetchall()
        if not rows:
            return 0
        query = sql.SQL("INSERT INTO {} ({}) VALUES ({}) ON CONFLICT DO NOTHING").format(
            sql.Identifier(table),
            sql.SQL(", ").join(map(sql.Identifier, columns)),
            sql.SQL(", ").join(sql.Placeholder() for _ in columns),
        )
        cursor.executemany(query, [tuple(row[column] for column in columns) for row in rows])
        if "id" in columns:
            cursor.execute(
                sql.SQL(
                    "SELECT setval(pg_get_serial_sequence(%s, 'id'), "
                    "COALESCE((SELECT MAX(id) FROM {}), 1), true)"
                ).format(sql.Identifier(table)),
                (table,),
            )
    postgres_db.commit()
    return len(rows)


def main() -> None:
    if not DATABASE_URL:
        raise SystemExit("DATABASE_URL tanımlı değil.")
    if not SQLITE_PATH.exists():
        raise SystemExit(f"SQLite dosyası bulunamadı: {SQLITE_PATH}")

    sqlite_db = sqlite3.connect(SQLITE_PATH)
    sqlite_db.row_factory = sqlite3.Row
    postgres_db = psycopg2.connect(_postgres_url(DATABASE_URL))
    try:
        with postgres_db.cursor() as cursor:
            cursor.execute(POSTGRES_SCHEMA)
        postgres_db.commit()
        for table in TABLES:
            count = migrate_table(sqlite_db, postgres_db, table)
            print(f"{table}: {count} kayıt işlendi")
    finally:
        sqlite_db.close()
        postgres_db.close()


if __name__ == "__main__":
    main()

