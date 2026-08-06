"""Entidad futura para preferencias didácticas persistentes."""

from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DidacticSettings(Base):
    """Store configurable pedagogical parameters for a user or course."""

    __tablename__ = "didactic_settings"
    id: Mapped[int] = mapped_column(primary_key=True)
    audience_level: Mapped[str]

