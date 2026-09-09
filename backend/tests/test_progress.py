"""Pruebas unitarias del estado de progreso visible durante la ingesta (HU-02)."""

from types import SimpleNamespace

from app.repositories.video_repository import VideoRepository


class FakeSession:
    """Minimal session double that proves the progress update is committed."""

    def __init__(self) -> None:
        self.commits = 0

    def commit(self) -> None:
        """Record the durability boundary requested by the repository."""
        self.commits += 1


def test_update_progress_clamps_percentage_and_persists_stage() -> None:
    """HU-02 prevents invalid percentages from reaching polling clients."""
    session = FakeSession()
    video = SimpleNamespace(status="queued", progress_stage="queued", progress_percent=0)
    VideoRepository().update_progress(session, video, "transcribing", 125)
    assert (video.status, video.progress_stage, video.progress_percent, session.commits) == ("processing", "transcribing", 100, 1)
