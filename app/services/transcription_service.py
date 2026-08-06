"""Puerto para transcripción local con faster-whisper."""

from pathlib import Path


class TranscriptionService:
    """Transcribe audio locally and retain timestamped segments."""

    def transcribe(self, audio_path: Path, language: str) -> list[dict]:
        """Return timestamped transcript segments from Whisper."""
        raise NotImplementedError

