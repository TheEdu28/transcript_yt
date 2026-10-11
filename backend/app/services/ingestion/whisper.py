"""Transcripción de audio local con faster-whisper."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.core.errors import PipelineError

SUPPORTED_LANGUAGES = {"es", "en"}


@dataclass(frozen=True)
class TranscriptSegment:
    """Texto puntuado de Whisper y su intervalo de respaldo temporal."""

    start: float
    end: float
    text: str


class WhisperService:
    """Transcripción local con timestamps de segmento y puntuación de Whisper."""

    _model: Any = None

    def transcribe(self, audio_path: Path, language: str, settings: Settings) -> list[TranscriptSegment]:
        import os
        from faster_whisper import WhisperModel

        if self._model is None:
            threads = min(4, os.cpu_count() or 4)
            self._model = WhisperModel(
                settings.whisper_model,
                device=settings.whisper_device,
                compute_type=settings.whisper_compute_type,
                cpu_threads=threads,
                num_workers=1,
            )
        segments, detected = self._model.transcribe(
            str(audio_path),
            language=language,
            task="transcribe",
            vad_filter=True,
            beam_size=1,
            word_timestamps=False,
        )
        if detected.language not in SUPPORTED_LANGUAGES:
            raise PipelineError("Whisper detectó un idioma no permitido.", code="UNSUPPORTED_LANGUAGE")
        result = [
            TranscriptSegment(round(s.start, 2), round(s.end, 2), s.text.strip())
            for s in segments
            if s.text.strip()
        ]
        if not result:
            raise PipelineError("No se detectó voz transcribible en el video.", code="EMPTY_TRANSCRIPT")
        return result
