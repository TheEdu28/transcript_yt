"""Pruebas de la máquina de estados de ingesta visible por HU-02."""

from pathlib import Path
from types import SimpleNamespace

from app.services.pipeline import PipelineService, TranscriptChunk, TranscriptSegment, VideoInfo


class FakeRepository:
    """Repository double for testing state transitions without SQLite."""

    def __init__(self, video: object | None = None) -> None:
        self.video = video
        self.updates: list[tuple[str, int, str]] = []

    def get_by_youtube_id(self, _session: object, _youtube_id: str) -> object | None:
        return self.video

    def create(self, _session: object, **values: object) -> object:
        self.video = SimpleNamespace(id=12, **values)
        return self.video

    def get(self, _session: object, _video_id: int) -> object | None:
        return self.video

    def update_progress(self, _session: object, video: object, stage: str, percent: int, status: str = "processing") -> None:
        video.status, video.progress_stage, video.progress_percent = status, stage, percent
        self.updates.append((stage, percent, status))


class FakeSession:
    """Minimal transaction double for pipeline unit tests."""

    def commit(self) -> None:
        """Pipeline commits state after every durable transition."""


def bare_pipeline(tmp_path: Path, repository: FakeRepository) -> PipelineService:
    """Construct the orchestrator without loading ChromaDB or Whisper."""
    service = PipelineService.__new__(PipelineService)
    service.settings = SimpleNamespace(raw_transcripts_directory=tmp_path)
    service.repository = repository
    return service


def test_queue_ingest_creates_a_pollable_queued_video(tmp_path: Path) -> None:
    """HU-02 makes an accepted job available before expensive processing starts."""
    repository = FakeRepository()
    service = bare_pipeline(tmp_path, repository)
    service.youtube = SimpleNamespace(inspect=lambda _url, _settings: VideoInfo("abc", "https://youtu.be/abc", "Clase", 60, "es"))
    job = service.queue_ingest("https://youtu.be/abc", FakeSession())
    assert job == {"video_id": 12, "status": "queued", "progress_stage": "queued", "progress_percent": 0, "queued": True}


def test_process_queued_ingest_publishes_completed_progress(tmp_path: Path) -> None:
    """HU-02 advances through local stages and ends at 100 percent."""
    transcript_path = tmp_path / "abc.json"
    video = SimpleNamespace(id=12, youtube_id="abc", source_url="https://youtu.be/abc", title="Clase", duration_seconds=60,
                            language="es", transcript_path=str(transcript_path), status="queued", processing_seconds=0.0)
    repository = FakeRepository(video)
    service = bare_pipeline(tmp_path, repository)
    service.youtube = SimpleNamespace(download_audio=lambda *_args: tmp_path / "audio.mp3")
    service.whisper = SimpleNamespace(transcribe=lambda *_args: [TranscriptSegment(0, 10, "Texto de prueba")])
    service.chunker = SimpleNamespace(build=lambda *_args: [TranscriptChunk(0, "Texto de prueba", 0, 10)])
    service.vectors = SimpleNamespace(index=lambda *_args: None)
    result = service.process_queued_ingest(12, FakeSession())
    assert result["chunks_indexed"] == 1
    assert (video.status, video.progress_stage, video.progress_percent) == ("indexed", "completed", 100)
    assert transcript_path.exists()


def test_ingest_result_preserves_the_synchronous_response_contract() -> None:
    """HU-02 adds async support without changing the original ingest result shape."""
    video = SimpleNamespace(id=12, title="Clase", language="es", duration_seconds=60, processing_seconds=2.5)
    assert PipelineService._ingest_result(video, 3)["chunks_indexed"] == 3
