"""Fábrica de sesiones SQLite; la inicialización se añadirá después."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings

engine = create_engine(get_settings().sqlite_database_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

