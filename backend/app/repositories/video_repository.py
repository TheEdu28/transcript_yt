"""Persistencia aislada de los metadatos de videos."""

from sqlalchemy import select
from sqlalchemy.orm import Session

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

    def set_status(self, session: Session, video: Video, status: str) -> None:
        video.status = status
        session.commit()

    def update_progress(self, session: Session, video: Video, stage: str, percent: int, status: str = "processing") -> None:
        """Persist a monotonic, API-visible ingestion stage for polling clients."""
        video.status = status
        video.progress_stage = stage
        video.progress_percent = max(0, min(100, percent))
        session.commit()

    def get_by_youtube_id(self, session: Session, youtube_id: str) -> Video | None:
        return session.scalar(select(Video).where(Video.youtube_id == youtube_id))
