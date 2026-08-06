"""Endpoints RF-01 y RF-05: búsqueda e ingesta de videos."""

from fastapi import APIRouter, status

from app.schemas.video import VideoIngestRequest, VideoSearchRequest

router = APIRouter()


@router.post("/search", status_code=status.HTTP_501_NOT_IMPLEMENTED)
def search_videos(payload: VideoSearchRequest) -> None:
    """Search YouTube videos by keywords (RF-05)."""
    raise NotImplementedError


@router.post("/ingest", status_code=status.HTTP_501_NOT_IMPLEMENTED)
def ingest_video(payload: VideoIngestRequest) -> None:
    """Queue the ingestion and transcription of a YouTube video (RF-01)."""
    raise NotImplementedError

