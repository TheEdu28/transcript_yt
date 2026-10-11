"""Particionamiento semántico y solapamiento de transcripciones."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings
from app.services.ingestion.whisper import TranscriptSegment


@dataclass(frozen=True)
class TranscriptChunk:
    """Fragmento semántico que se vectoriza junto con su evidencia temporal."""

    index: int
    text: str
    start: float
    end: float


class ChunkingService:
    """Agrupa segmentos completos conservando continuidad semántica mediante solapamiento."""

    def build(self, segments: list[TranscriptSegment], settings: Settings) -> list[TranscriptChunk]:
        chunks: list[TranscriptChunk] = []
        start_index = 0
        while start_index < len(segments):
            end_index, word_count = start_index, 0
            while end_index < len(segments) and word_count < settings.chunk_words:
                word_count += len(segments[end_index].text.split())
                end_index += 1
            current = segments[start_index:end_index]
            chunks.append(
                TranscriptChunk(
                    index=len(chunks),
                    text=" ".join(segment.text for segment in current),
                    start=current[0].start,
                    end=current[-1].end,
                )
            )
            if end_index >= len(segments):
                break
            start_index = max(start_index + 1, end_index - settings.chunk_overlap_segments)
        return chunks
