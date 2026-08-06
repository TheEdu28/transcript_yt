"""Contrato de persistencia para videos."""


class VideoRepository:
    """Encapsulate future SQLite queries for video metadata."""

    def get_by_youtube_id(self, youtube_id: str) -> None:
        """Retrieve a video by its YouTube identifier."""
        raise NotImplementedError

