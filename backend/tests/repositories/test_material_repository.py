"""Pruebas SQLite de persistencia de materiales para HU-06 y HU-07."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.repositories.material_repository import MaterialRepository


def test_material_repository_creates_reads_and_updates_content() -> None:
    """SQLite retains the same material identifier across an edit."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    repository = MaterialRepository()
    material = repository.create(session, 2, "summary", '{"synopsis":"antes"}')
    assert repository.get(session, material.id) is material
    updated = repository.update_content(session, material, '{"synopsis":"después"}')
    assert updated.content_json == '{"synopsis":"después"}'
