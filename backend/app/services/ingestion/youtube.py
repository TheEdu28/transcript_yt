"""Extracción y validación de videos de YouTube usando yt-dlp."""

from __future__ import annotations

import json
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.core.config import Settings
from app.core.errors import PipelineError
from app.services.ingestion.whisper import TranscriptSegment

SUPPORTED_LANGUAGES = {"es", "en"}
YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}


@dataclass(frozen=True)
class VideoInfo:
    """Datos validados antes de descargar cualquier contenido."""

    youtube_id: str
    url: str
    title: str
    duration_seconds: int
    language: str


def is_supported_youtube_url(url: str) -> bool:
    """Acepta únicamente URLs HTTP(S) que identifiquen un video de YouTube, no playlists."""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme not in {"http", "https"} or host not in YOUTUBE_HOSTS:
        return False
    if host == "youtu.be":
        return bool(parsed.path.strip("/"))
    if parsed.path == "/watch":
        return "v=" in parsed.query
    return bool(parsed.path.strip("/")) and "/playlist" not in parsed.path


class YouTubeService:
    """Valida visibilidad, idioma declarado y duración con yt-dlp."""

    def inspect(self, url: str, settings: Settings) -> VideoInfo:
        if not is_supported_youtube_url(url):
            raise PipelineError("La URL debe pertenecer a YouTube.", code="INVALID_YOUTUBE_URL")
        try:
            from yt_dlp import YoutubeDL
            from yt_dlp.utils import DownloadError

            ydl_opts: dict[str, Any] = {
                "quiet": False,
                "no_warnings": False,
                "noplaylist": True,
                "js_runtimes": {"node": {"path": "C:/Program Files/nodejs/node.exe"}},
                "remote_components": ["ejs:github"],
            }
            cookies_path = settings.resolved_yt_dlp_cookie_file
            if cookies_path.exists():
                ydl_opts["cookiefile"] = str(cookies_path)
            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
        except DownloadError as error:
            error_msg = str(error).lower()
            if "private" in error_msg:
                raise PipelineError("El video debe ser público.", code="VIDEO_NOT_PUBLIC", status_code=403) from error
            raise PipelineError(
                f"No se pudo acceder al video: {error}",
                code="VIDEO_UNAVAILABLE",
                status_code=403,
            ) from error

        return self._validate_metadata(info, url, settings)

    def _validate_metadata(self, info: dict[str, Any], url: str, settings: Settings) -> VideoInfo:
        """Valida metadatos antes de descargar audio (HU-01, HU-10)."""
        availability = str(info.get("availability") or "").lower()
        if availability and availability != "public":
            raise PipelineError("El video debe ser público.", code="VIDEO_NOT_PUBLIC", status_code=403)
        if info.get("is_live"):
            raise PipelineError("Las transmisiones en vivo no son compatibles.", code="LIVE_VIDEO_UNSUPPORTED")
        duration = int(info.get("duration") or 0)
        if duration <= 0:
            raise PipelineError("No fue posible determinar la duración del video.", code="MISSING_DURATION")
        if duration > settings.max_video_duration_seconds:
            raise PipelineError("El video excede el límite de 60 minutos.", code="DURATION_EXCEEDED")

        language = self._declared_language(info)
        if language not in SUPPORTED_LANGUAGES:
            raise PipelineError(
                "El video debe declarar español o inglés para poder procesarse.",
                code="UNSUPPORTED_LANGUAGE",
                status_code=422,
            )
        youtube_id = str(info.get("id") or "")
        if not youtube_id:
            raise PipelineError("YouTube no devolvió un identificador de video.", code="MISSING_VIDEO_ID")
        return VideoInfo(
            youtube_id=youtube_id,
            url=url,
            title=str(info.get("title") or youtube_id),
            duration_seconds=duration,
            language=language,
        )

    @staticmethod
    def _declared_language(info: dict[str, Any]) -> str | None:
        candidates = [str(info.get("language") or "")]
        candidates.extend((info.get("subtitles") or {}).keys())
        candidates.extend((info.get("automatic_captions") or {}).keys())
        for candidate in candidates:
            prefix = candidate.lower().split("-")[0].split("_")[0]
            if prefix in SUPPORTED_LANGUAGES:
                return prefix
        return None

    def download_audio(self, video: VideoInfo, settings: Settings) -> Path:
        """Extrae audio MP3 localmente una vez aprobadas las validaciones."""
        from yt_dlp import YoutubeDL

        output_template = str(settings.audio_directory / f"{video.youtube_id}.%(ext)s")
        cookies_path = settings.resolved_yt_dlp_cookie_file
        options = {
            "format": "bestaudio/best",
            "outtmpl": output_template,
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "js_runtimes": {"node": {"path": "C:/Program Files/nodejs/node.exe"}},
            "remote_components": ["ejs:github"],
            "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "128"}],
        }
        if cookies_path.exists():
            options["cookiefile"] = str(cookies_path)
        try:
            with YoutubeDL(options) as ydl:
                ydl.download([video.url])
        except Exception as error:
            raise PipelineError("No se pudo extraer el audio del video.", code="AUDIO_EXTRACTION_FAILED") from error
        audio_path = settings.audio_directory / f"{video.youtube_id}.mp3"
        if not audio_path.exists():
            raise PipelineError("FFmpeg no produjo el audio esperado.", code="AUDIO_FILE_MISSING")
        return audio_path

    def extract_subtitles(self, video: VideoInfo, settings: Settings) -> list[TranscriptSegment] | None:
        """Extrae subtítulos oficiales o automáticos de YouTube vía yt-dlp en segundos (Fast-Path)."""
        from yt_dlp import YoutubeDL

        if video.language == "es":
            sub_langs = ["es", "es-419", "es-ES", "es-MX", "es-US"]
        elif video.language == "en":
            sub_langs = ["en", "en-US", "en-GB", "en-CA"]
        else:
            sub_langs = [video.language]

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            options: dict[str, Any] = {
                "skip_download": True,
                "writesubtitles": True,
                "writeautomaticsub": True,
                "subtitleslangs": sub_langs,
                "subtitlesformat": "json3/vtt/best",
                "outtmpl": str(tmp_path / "%(id)s.%(ext)s"),
                "quiet": True,
                "no_warnings": True,
                "noplaylist": True,
                "js_runtimes": {"node": {"path": "C:/Program Files/nodejs/node.exe"}},
                "remote_components": ["ejs:github"],
            }
            cookies_path = settings.resolved_yt_dlp_cookie_file
            if cookies_path.exists():
                options["cookiefile"] = str(cookies_path)

            try:
                with YoutubeDL(options) as ydl:
                    ydl.download([video.url])
            except Exception:
                return None

            downloaded_files = list(tmp_path.iterdir())
            if not downloaded_files:
                return None

            # Prioridad 1: Archivo json3 del idioma del video
            target_json3 = [
                f for f in downloaded_files
                if f.suffix == ".json3" and any(lang in f.name.lower() for lang in sub_langs)
            ]
            json3_files = target_json3 or [f for f in downloaded_files if f.suffix == ".json3"]

            # Prioridad 2: Archivo vtt del idioma del video
            target_vtt = [
                f for f in downloaded_files
                if f.suffix == ".vtt" and any(lang in f.name.lower() for lang in sub_langs)
            ]
            vtt_files = target_vtt or [f for f in downloaded_files if f.suffix == ".vtt"]

            segments: list[TranscriptSegment] = []
            if json3_files:
                segments = _parse_json3(json3_files[0])
            elif vtt_files:
                segments = _parse_vtt(vtt_files[0])

            # Deduplicar segmentos idénticos consecutivos
            deduped: list[TranscriptSegment] = []
            for seg in segments:
                if deduped and deduped[-1].text == seg.text and abs(deduped[-1].start - seg.start) < 1.0:
                    continue
                deduped.append(seg)

            if len(deduped) >= 2 and sum(len(s.text.split()) for s in deduped) >= 5:
                return deduped

            return None


def _parse_vtt_timestamp(ts: str) -> float:
    parts = ts.strip().split(":")
    try:
        if len(parts) == 3:
            h, m, s = parts
            return round(int(h) * 3600 + int(m) * 60 + float(s), 2)
        if len(parts) == 2:
            m, s = parts
            return round(int(m) * 60 + float(s), 2)
    except Exception:
        pass
    return 0.0


def _parse_json3(file_path: Path) -> list[TranscriptSegment]:
    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    events = data.get("events", [])
    segments: list[TranscriptSegment] = []
    for ev in events:
        raw_text = "".join(s.get("utf8", "") for s in ev.get("segs", []) if "utf8" in s)
        text = " ".join(raw_text.replace("\n", " ").split()).strip()
        if not text:
            continue
        start_ms = ev.get("tStartMs", 0)
        dur_ms = ev.get("dDurationMs", 0)
        start = round(start_ms / 1000.0, 2)
        end = round((start_ms + dur_ms) / 1000.0, 2)
        if end <= start:
            end = round(start + 2.0, 2)
        segments.append(TranscriptSegment(start=start, end=end, text=text))
    return segments


def _parse_vtt(file_path: Path) -> list[TranscriptSegment]:
    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception:
        return []
    blocks = content.replace("\r\n", "\n").split("\n\n")
    segments: list[TranscriptSegment] = []
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        time_idx = next((i for i, line in enumerate(lines) if "-->" in line), None)
        if time_idx is None or time_idx + 1 >= len(lines):
            continue
        parts = lines[time_idx].split("-->")
        start = _parse_vtt_timestamp(parts[0].split()[0])
        end = _parse_vtt_timestamp(parts[1].split()[0])
        raw_text = " ".join(lines[time_idx + 1:])
        text = " ".join(re.sub(r"<[^>]+>", "", raw_text).split()).strip()
        if not text:
            continue
        if end <= start:
            end = round(start + 2.0, 2)
        segments.append(TranscriptSegment(start=start, end=end, text=text))
    return segments

