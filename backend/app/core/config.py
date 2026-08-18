"""Configuración centralizada. Ninguna clave se codifica en el repositorio."""

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data"


class Settings(BaseSettings):
    """Carga parámetros del entorno y conserva los datos fuera de /backend."""

    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / ".env", extra="ignore")
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"
    whisper_model: str = "base"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    max_video_duration_seconds: int = 3600
    chunk_words: int = 220
    chunk_overlap_segments: int = 2
    rag_retrieval_limit: int = 6
    max_gemini_context_chars: int = 12000
    # 4096 permite completar el JSON del resumen sin enviar transcripciones largas.
    max_gemini_output_tokens: int = 4096
    # Archivo Netscape exportado desde el navegador autenticado; no se versiona.
    yt_dlp_cookie_file: Path | None = Field(
        default=None,
        validation_alias=AliasChoices("YTDLP_COOKIE_FILE", "yt_dlp_cookie_file"),
    )
    sqlite_database_url: str = f"sqlite:///{(DATA_DIR / 'metadata' / 'app.db').as_posix()}"
    chroma_persist_directory: Path = DATA_DIR / "chroma_db"
    chroma_collection_name: str = "transcript_chunks"
    raw_transcripts_directory: Path = DATA_DIR / "transcripts" / "raw"
    processed_transcripts_directory: Path = DATA_DIR / "transcripts" / "processed"
    audio_directory: Path = DATA_DIR / "audio"

    @property
    def resolved_yt_dlp_cookie_file(self) -> Path:
        """Return the configured cookie path relative to the repository when needed."""
        if self.yt_dlp_cookie_file is None:
            return DATA_DIR / "cookies.txt"
        return (
            self.yt_dlp_cookie_file
            if self.yt_dlp_cookie_file.is_absolute()
            else PROJECT_ROOT / self.yt_dlp_cookie_file
        )

    def ensure_data_directories(self) -> None:
        """Create only the local directories used by the pipeline at startup."""
        for directory in (self.chroma_persist_directory, self.raw_transcripts_directory,
                          self.processed_transcripts_directory, self.audio_directory,
                          DATA_DIR / "metadata"):
            directory.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    """Return the single application settings instance."""
    return Settings()
