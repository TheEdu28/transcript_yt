"""Pruebas unitarias sin modelos ni llamadas de red."""

from app.core.config import Settings
from app.services.pipeline import ChunkingService, TranscriptSegment, YouTubeService


def test_chunks_preserve_timestamp_and_overlap() -> None:
    settings = Settings(chunk_words=4, chunk_overlap_segments=1)
    segments = [
        TranscriptSegment(0, 5, "uno dos"), TranscriptSegment(5, 10, "tres cuatro"),
        TranscriptSegment(10, 15, "cinco seis"),
    ]
    chunks = ChunkingService().build(segments, settings)
    assert len(chunks) == 2
    assert chunks[0].end == 10
    assert chunks[1].start == 5


def test_language_uses_declared_or_caption_languages() -> None:
    assert YouTubeService._declared_language({"automatic_captions": {"es-419": []}}) == "es"

