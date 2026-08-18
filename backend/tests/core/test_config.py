"""Pruebas de rutas locales de configuración."""

from pathlib import Path

from app.core.config import DATA_DIR, PROJECT_ROOT, Settings


def test_cookie_file_defaults_to_canonical_data_directory() -> None:
    """Use the project data directory when no cookie file is configured."""
    assert Settings(_env_file=None).resolved_yt_dlp_cookie_file == DATA_DIR / "cookies.txt"


def test_cookie_file_resolves_relative_to_project_root() -> None:
    """Allow a local cookie file path without storing credentials in code."""
    settings = Settings(yt_dlp_cookie_file=Path("backend/data/cookies.txt"))
    assert settings.resolved_yt_dlp_cookie_file == PROJECT_ROOT / "backend/data/cookies.txt"


def test_cookie_file_accepts_documented_environment_alias() -> None:
    """Use the YTDLP_COOKIE_FILE variable documented for local deployments."""
    settings = Settings(YTDLP_COOKIE_FILE="backend/data/cookies.txt")
    assert settings.resolved_yt_dlp_cookie_file == PROJECT_ROOT / "backend/data/cookies.txt"
