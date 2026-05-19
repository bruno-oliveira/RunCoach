"""Database engine, session factory, and FastAPI session dependency.

Centralizes SQLAlchemy setup so the rest of the app does not import
SQLAlchemy directly outside of the infrastructure layer.
"""

from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.infrastructure.config import settings
from app.models.base import Base

_is_sqlite = "sqlite" in settings.database_url

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if _is_sqlite else {},
    poolclass=NullPool if _is_sqlite else None,
)

if _is_sqlite:
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_conn, _):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA cache_size=-32000")
        cursor.execute("PRAGMA temp_store=MEMORY")
        cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """Yield a database session; closed after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


__all__ = ["Base", "engine", "SessionLocal", "get_db"]
