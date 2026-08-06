"""Pruebas de HU-01 y HU-10 sin red ni proveedores externos."""

import pytest

from app.core.config import Settings
from app.core.errors import PipelineError
from app.services.pipeline import YouTubeService, is_supported_youtube_url


def video_metadata(**overrides: object) -> dict[str, object]:
    """Build a public, Spanish video metadata fixture."""
    metadata: dict[str, object] = {
        "id": "abc123", "title": "Clase de prueba", "duration": 600,
        "availability": "public", "language": "es",
    }
    metadata.update(overrides)
    return metadata


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://www.youtube.com/watch?v=abc123", True),
        ("https://youtu.be/abc123", True),
        ("https://www.youtube.com/playlist?list=abc", False),
        ("https://example.com/watch?v=abc123", False),
    ],
)
def test_is_supported_youtube_url_accepts_only_video_urls(url: str, expected: bool) -> None:
    """HU-01 rejects non-YouTube and playlist-only addresses before network access."""
    assert is_supported_youtube_url(url) is expected


def test_validate_metadata_accepts_public_spanish_video() -> None:
    """HU-01 accepts a public video with an allowed declared language."""
    result = YouTubeService()._validate_metadata(
        video_metadata(), "https://www.youtube.com/watch?v=abc123", Settings(),
    )
    assert result.language == "es"
    assert result.duration_seconds == 600


def test_validate_metadata_rejects_private_video() -> None:
    """HU-01 reports a stable public-visibility error."""
    with pytest.raises(PipelineError, match="público") as error:
        YouTubeService()._validate_metadata(
            video_metadata(availability="private"), "https://www.youtube.com/watch?v=abc123", Settings(),
        )
    assert error.value.code == "VIDEO_NOT_PUBLIC"


def test_validate_metadata_rejects_duration_over_60_minutes() -> None:
    """HU-10 enforces the configured duration boundary before download."""
    with pytest.raises(PipelineError) as error:
        YouTubeService()._validate_metadata(
            video_metadata(duration=3601), "https://www.youtube.com/watch?v=abc123", Settings(),
        )
    assert error.value.code == "DURATION_EXCEEDED"


def test_validate_metadata_rejects_unsupported_language() -> None:
    """HU-10 permits only Spanish and English metadata or captions."""
    with pytest.raises(PipelineError) as error:
        YouTubeService()._validate_metadata(
            video_metadata(language="fr"), "https://www.youtube.com/watch?v=abc123", Settings(),
        )
    assert error.value.code == "UNSUPPORTED_LANGUAGE"
