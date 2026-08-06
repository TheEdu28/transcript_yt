"""Entidad futura que representa un video y su estado de procesamiento."""

from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Video(Base):
    """Store video metadata without storing the audiovisual file in SQLite."""

    __tablename__ = "videos"
    id: Mapped[int] = mapped_column(primary_key=True)
    youtube_id: Mapped[str] = mapped_column(unique=True, index=True)
    title: Mapped[str]

