"""Configuración tipada obtenida del entorno."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Represent environment variables required by the prototype."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_name: str = "Material Didactico YouTube API"
    app_env: str = "development"
    debug: bool = True
    api_v1_prefix: str = "/api/v1"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"
    youtube_api_key: str = ""
    youtube_max_results: int = 10
    sqlite_database_url: str = "sqlite:///./data/metadata/app.db"
    chroma_persist_directory: Path = Path("./data/chroma")
    chroma_collection_name: str = "video_transcript_chunks"
    whisper_model: str = "base"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    raw_transcripts_directory: Path = Path("./data/transcripts/raw")
    processed_transcripts_directory: Path = Path("./data/transcripts/processed")
    exports_directory: Path = Path("./data/exports")


@lru_cache
def get_settings() -> Settings:
    """Return cached application configuration."""
    return Settings()

