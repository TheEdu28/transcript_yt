"""Metadatos mínimos de cada video procesado."""

from sqlalchemy import Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class Video(Base):
    """No guarda el audiovisual, sólo referencias y estado de su procesamiento."""

    __tablename__ = "videos"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    youtube_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    source_url: Mapped[str] = mapped_column(String(2048))
    title: Mapped[str] = mapped_column(String(500))
    language: Mapped[str] = mapped_column(String(8))
    duration_seconds: Mapped[int] = mapped_column(Integer)
    transcript_path: Mapped[str] = mapped_column(String(2048))
    status: Mapped[str] = mapped_column(String(30), default="indexed")
    processing_seconds: Mapped[float] = mapped_column(Float, default=0.0)

