"""Recursos didácticos persistidos para consulta, edición y exportación."""

from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class DidacticMaterial(Base):
    """Conserva el JSON validado de un resumen o cuestionario generado."""

    __tablename__ = "didactic_materials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    video_id: Mapped[int] = mapped_column(Integer, index=True)
    material_type: Mapped[str] = mapped_column(String(20))
    content_json: Mapped[str] = mapped_column(Text)
