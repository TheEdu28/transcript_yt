"""Persistencia SQLite de resúmenes y cuestionarios editables."""

from sqlalchemy.orm import Session

from app.models.group import Group, Topic
from app.models.material import DidacticMaterial, MaterialVersion
from app.models.user import User
from app.models.video import Video


class MaterialRepository:
    """Aísla el acceso a recursos didácticos serializados como JSON."""

    def create(self, session: Session, video_id: int, material_type: str, content_json: str, owner_id: int | None = None) -> DidacticMaterial:
        """Store a newly generated, already validated resource."""
        material = DidacticMaterial(video_id=video_id, material_type=material_type, content_json=content_json, owner_id=owner_id)
        session.add(material)
        session.commit()
        session.refresh(material)
        return material

    def get(self, session: Session, material_id: int) -> DidacticMaterial | None:
        """Retrieve a resource by its stable identifier."""
        return session.get(DidacticMaterial, material_id)

    def update_content(self, session: Session, material: DidacticMaterial, content_json: str, edited_by: int | None = None) -> DidacticMaterial:
        """Snapshot current content, then replace with the validated edit."""
        snapshot = MaterialVersion(material_id=material.id, content_json=material.content_json, edited_by=edited_by)
        session.add(snapshot)
        material.content_json = content_json
        session.commit()
        session.refresh(material)
        return material

    def list_versions(self, session: Session, material_id: int) -> list[MaterialVersion]:
        """Return all historical snapshots for a material, newest first."""
        return (
            session.query(MaterialVersion)
            .filter(MaterialVersion.material_id == material_id)
            .order_by(MaterialVersion.edited_at.desc())
            .all()
        )

    def latest_version(self, session: Session, material_id: int) -> MaterialVersion | None:
        """Return the most recent edit snapshot for a material."""
        return (
            session.query(MaterialVersion)
            .filter(MaterialVersion.material_id == material_id)
            .order_by(MaterialVersion.edited_at.desc(), MaterialVersion.id.desc())
            .first()
        )

    def get_version(self, session: Session, material_id: int, version_id: int) -> MaterialVersion | None:
        """Retrieve a version only when it belongs to the requested material."""
        return (
            session.query(MaterialVersion)
            .filter(MaterialVersion.id == version_id, MaterialVersion.material_id == material_id)
            .first()
        )

    @staticmethod
    def user_name(session: Session, user_id: int | None) -> str | None:
        """Resolve a version editor's display name without exposing credentials."""
        if user_id is None:
            return None
        user = session.get(User, user_id)
        return user.nombre if user else None

    def is_video_owner_or_published_group_admin(
        self, session: Session, material: DidacticMaterial, user_id: int
    ) -> bool:
        """Check ownership or administration of any active group topic for the video."""
        if session.query(Video.id).filter(Video.id == material.video_id, Video.owner_id == user_id).first():
            return True
        return (
            session.query(Topic.id)
            .join(Group, Group.id == Topic.group_id)
            .filter(
                Topic.video_id == material.video_id,
                Topic.is_published.is_(True),
                Group.admin_id == user_id,
            )
            .first()
            is not None
        )
