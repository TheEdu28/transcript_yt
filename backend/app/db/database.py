"""SQLite sólo para metadatos; ChromaDB conserva los vectores."""

from collections.abc import Generator
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    """Base de las entidades ORM."""


settings = get_settings()
settings.ensure_data_directories()
engine = create_engine(settings.sqlite_database_url, connect_args={"check_same_thread": False})


@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection: Any, _connection_record: Any) -> None:
    """Habilita WAL mode y timeout para evitar bloqueos por concurrencia en SQLite."""
    if settings.sqlite_database_url.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA busy_timeout=5000")
        finally:
            cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_session() -> Generator[Session, None, None]:
    """Provide one SQLite session per HTTP request."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
