"""Persistencia SQLite de resúmenes y cuestionarios editables."""

from sqlalchemy.orm import Session

from app.models.material import DidacticMaterial


class MaterialRepository:
    """Aísla el acceso a recursos didácticos serializados como JSON."""

    def create(self, session: Session, video_id: int, material_type: str, content_json: str) -> DidacticMaterial:
        """Store a newly generated, already validated resource."""
        material = DidacticMaterial(video_id=video_id, material_type=material_type, content_json=content_json)
        session.add(material)
        session.commit()
        session.refresh(material)
        return material

    def get(self, session: Session, material_id: int) -> DidacticMaterial | None:
        """Retrieve a resource by its stable identifier."""
        return session.get(DidacticMaterial, material_id)

    def update_content(self, session: Session, material: DidacticMaterial, content_json: str) -> DidacticMaterial:
        """Replace the serialized content after domain validation."""
        material.content_json = content_json
        session.commit()
        session.refresh(material)
        return material
