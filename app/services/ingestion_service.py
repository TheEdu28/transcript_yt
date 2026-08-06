"""Caso de uso RF-01: orquestación de ingesta y procesamiento."""


class IngestionService:
    """Coordinate metadata, audio acquisition, transcription and indexing."""

    def ingest(self, video_url: str, language: str) -> int:
        """Start the future video ingestion pipeline and return its video id."""
        raise NotImplementedError

