"""SQLite sólo para metadatos; ChromaDB conserva los vectores."""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    """Base de las entidades ORM."""


settings = get_settings()
settings.ensure_data_directories()
engine = create_engine(settings.sqlite_database_url, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_session() -> Generator[Session, None, None]:
    """Provide one SQLite session per HTTP request."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
