from __future__ import annotations

"""
Production veritabanı bağlantı yardımcıları.

Render'da DATABASE_URL tanımlandığında PostgreSQL kullanılır. DATABASE_URL
yoksa local geliştirme için SQLite fallback devreye girer.
"""

import os

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine


def normalize_database_url(url: str) -> str:
    """Render/Heroku tarzı postgres:// adresini SQLAlchemy uyumlu hale getirir."""
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url.removeprefix("postgres://")
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url.removeprefix("postgresql://")
    return url


def create_pooled_engine() -> Engine | None:
    """DATABASE_URL varsa connection pool kullanan PostgreSQL engine'i oluşturur."""
    database_url = (os.environ.get("DATABASE_URL") or "").strip()
    if not database_url:
        return None
    return create_engine(
        normalize_database_url(database_url),
        pool_size=int(os.environ.get("DB_POOL_SIZE", "5")),
        max_overflow=int(os.environ.get("DB_MAX_OVERFLOW", "10")),
        pool_pre_ping=True,
        pool_recycle=1800,
        future=True,
    )
