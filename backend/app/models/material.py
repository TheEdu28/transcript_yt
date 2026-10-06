"""Recursos didácticos persistidos para consulta, edición y exportación."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class DidacticMaterial(Base):
    """Conserva el JSON validado de un resumen o cuestionario generado."""

    __tablename__ = "didactic_materials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    video_id: Mapped[int] = mapped_column(Integer, index=True)
    material_type: Mapped[str] = mapped_column(String(20))
    content_json: Mapped[str] = mapped_column(Text)
    owner_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True, index=True)

    versions: Mapped[list["MaterialVersion"]] = relationship(
        "MaterialVersion", back_populates="material", cascade="all, delete-orphan", order_by="MaterialVersion.edited_at.desc()"
    )


class MaterialVersion(Base):
    """Snapshot inmutable de cada edición de un material didáctico."""

    __tablename__ = "material_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    material_id: Mapped[int] = mapped_column(Integer, ForeignKey("didactic_materials.id"), nullable=False, index=True)
    content_json: Mapped[str] = mapped_column(Text, nullable=False)
    edited_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    edited_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    material: Mapped["DidacticMaterial"] = relationship("DidacticMaterial", back_populates="versions")
