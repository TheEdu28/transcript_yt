"""Entidad futura para materiales didácticos generados."""

from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DidacticMaterial(Base):
    """Store generation metadata and serialized resource references."""

    __tablename__ = "didactic_materials"
    id: Mapped[int] = mapped_column(primary_key=True)
    video_id: Mapped[int] = mapped_column(index=True)
    material_type: Mapped[str]

