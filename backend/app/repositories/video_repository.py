"""Persistencia aislada de los metadatos de videos."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.material import DidacticMaterial
from app.models.group import Topic
from app.models.video import Video


class VideoRepository:
    """Encapsula las consultas SQLite utilizadas por los casos de uso."""

    def create(self, session: Session, **values: object) -> Video:
        video = Video(**values)
        session.add(video)
        session.commit()
        session.refresh(video)
        return video

    def get(self, session: Session, video_id: int) -> Video | None:
        return session.get(Video, video_id)

    def delete(self, session: Session, video: Video) -> None:
        """Elimina el registro del video de SQLite."""
        session.delete(video)
        session.commit()

    def get_by_youtube_id(self, session: Session, youtube_id: str) -> Video | None:
        return session.scalar(select(Video).where(Video.youtube_id == youtube_id))

    def set_status(self, session: Session, video: Video, status: str) -> None:
        video.status = status
        session.commit()

    def update_progress(self, session: Session, video: Video, stage: str, percent: int, status: str = "processing") -> None:
        """Persist a monotonic, API-visible ingestion stage for polling clients."""
        video.status = status
        video.progress_stage = stage
        video.progress_percent = max(0, min(100, percent))
        session.commit()

    def list_by_owner(
        self, session: Session, owner_id: int, *, page: int = 1, page_size: int = 20, status: str | None = None
    ) -> tuple[list[dict], int]:
        """Devuelve (items, total) para el historial paginado del usuario.

        Cada item incluye:
          - todos los campos del video
          - has_summary: bool
          - has_quiz: bool
          - published_in_groups: list[int]  — IDs de grupos donde es tema
        """
        from sqlalchemy import func
        where = [Video.owner_id == owner_id]
        if status:
            where.append(Video.status == status)
        base_q = select(Video).where(*where).order_by(Video.created_at.desc())
        total = session.scalar(select(func.count()).select_from(Video).where(*where)) or 0

        videos = session.scalars(
            base_q.offset((page - 1) * page_size).limit(page_size)
        ).all()
        if not videos:
            return [], total

        video_ids = [v.id for v in videos]

        # Materiales generados agrupados por video_id y tipo
        materials = session.execute(
            select(DidacticMaterial.video_id, DidacticMaterial.material_type)
            .where(DidacticMaterial.video_id.in_(video_ids))
        ).all()
        summaries = {row.video_id for row in materials if row.material_type == "summary"}
        quizzes   = {row.video_id for row in materials if row.material_type == "quiz"}

        # Temas de grupo que apuntan a estos videos
        topics = session.execute(
            select(Topic.video_id, Topic.group_id)
            .where(Topic.video_id.in_(video_ids))
        ).all()
        published: dict[int, list[int]] = {}
        for row in topics:
            published.setdefault(row.video_id, []).append(row.group_id)

        items = [
            {
                "id": v.id,
                "youtube_id": v.youtube_id,
                "title": v.title,
                "language": v.language,
                "duration_seconds": v.duration_seconds,
                "status": v.status,
                "created_at": v.created_at.isoformat() if v.created_at else None,
                "has_summary": v.id in summaries,
                "has_quiz": v.id in quizzes,
                "published_in_groups": published.get(v.id, []),
            }
            for v in videos
        ]
        return items, total
