"""Pruebas unitarias para el Fast-Path de subtítulos y su integración en el pipeline."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.ingestion.whisper import TranscriptSegment
from app.services.ingestion.youtube import (
    VideoInfo,
    _parse_json3,
    _parse_vtt,
    _parse_vtt_timestamp,
)
from app.services.pipeline import PipelineService, TranscriptChunk
from tests.services.test_ingestion_progress import FakeRepository, FakeSession, bare_pipeline


def test_parse_vtt_timestamp() -> None:
    assert _parse_vtt_timestamp("00:01:23.450") == 83.45
    assert _parse_vtt_timestamp("02:15.500") == 135.50
    assert _parse_vtt_timestamp("invalid") == 0.0


def test_parse_json3_converts_events_to_transcript_segments(tmp_path: Path) -> None:
    sample = {
        "events": [
            {
                "tStartMs": 1000,
                "dDurationMs": 2500,
                "segs": [{"utf8": "Hola mundo"}, {"utf8": " desde YouTube"}],
            },
            {
                "tStartMs": 4000,
                "dDurationMs": 3000,
                "segs": [{"utf8": "Segunda oración explicativa"}],
            },
            {
                "tStartMs": 7000,
                "dDurationMs": 1000,
                "segs": [{"utf8": "\n"}],
            },
        ]
    }
    json3_file = tmp_path / "video.es.json3"
    json3_file.write_text(json.dumps(sample), encoding="utf-8")

    segments = _parse_json3(json3_file)
    assert len(segments) == 2
    assert segments[0].start == 1.0
    assert segments[0].end == 3.5
    assert segments[0].text == "Hola mundo desde YouTube"
    assert segments[1].start == 4.0
    assert segments[1].end == 7.0
    assert segments[1].text == "Segunda oración explicativa"


def test_parse_vtt_converts_cues_to_transcript_segments(tmp_path: Path) -> None:
    sample_vtt = """WEBVTT
Kind: captions
Language: es

00:00:01.500 --> 00:00:04.200
Bienvenido a la <b>clase</b> de hoy.

00:00:05.000 --> 00:00:08.500
Aprenderemos sobre algoritmos y estructuras.
"""
    vtt_file = tmp_path / "video.es.vtt"
    vtt_file.write_text(sample_vtt, encoding="utf-8")

    segments = _parse_vtt(vtt_file)
    assert len(segments) == 2
    assert segments[0].start == 1.5
    assert segments[0].end == 4.2
    assert segments[0].text == "Bienvenido a la clase de hoy."
    assert segments[1].start == 5.0
    assert segments[1].end == 8.5
    assert segments[1].text == "Aprenderemos sobre algoritmos y estructuras."


def test_fast_path_bypasses_whisper_and_audio_download(tmp_path: Path) -> None:
    transcript_path = tmp_path / "fast.json"
    video = SimpleNamespace(
        id=99,
        youtube_id="fast123",
        source_url="https://youtu.be/fast123",
        title="Video Rápido",
        duration_seconds=120,
        language="es",
        transcript_path=str(transcript_path),
        status="queued",
        processing_seconds=0.0,
    )
    repository = FakeRepository(video)
    service = bare_pipeline(tmp_path, repository)

    download_audio_called = False
    whisper_called = False

    def mock_download_audio(*_args: object) -> Path:
        nonlocal download_audio_called
        download_audio_called = True
        return tmp_path / "audio.mp3"

    def mock_whisper(*_args: object) -> list[TranscriptSegment]:
        nonlocal whisper_called
        whisper_called = True
        return []

    service.youtube = SimpleNamespace(
        extract_subtitles=lambda *_args: [
            TranscriptSegment(0.0, 5.0, "Introducción al tema"),
            TranscriptSegment(5.0, 10.0, "Detalles importantes"),
        ],
        download_audio=mock_download_audio,
    )
    service.whisper = SimpleNamespace(transcribe=mock_whisper)
    service.chunker = SimpleNamespace(
        build=lambda segments, _s: [TranscriptChunk(0, "chunk 1", 0.0, 10.0)]
    )
    service.vectors = SimpleNamespace(index=lambda *_args: None)

    result = service.process_queued_ingest(99, FakeSession())

    assert not download_audio_called, "download_audio no debe llamarse cuando hay subtítulos disponibles"
    assert not whisper_called, "Whisper no debe ejecutarse cuando hay subtítulos disponibles"
    assert result["chunks_indexed"] == 1
    assert video.status == "indexed"
    assert video.progress_percent == 100
    assert transcript_path.exists()

    saved_data = json.loads(transcript_path.read_text(encoding="utf-8"))
    assert len(saved_data) == 2
    assert saved_data[0]["text"] == "Introducción al tema"


def test_fast_path_falls_back_to_whisper_when_no_subtitles(tmp_path: Path) -> None:
    transcript_path = tmp_path / "fallback.json"
    video = SimpleNamespace(
        id=100,
        youtube_id="fallback123",
        source_url="https://youtu.be/fallback123",
        title="Video Sin Subtítulos",
        duration_seconds=120,
        language="es",
        transcript_path=str(transcript_path),
        status="queued",
        processing_seconds=0.0,
    )
    repository = FakeRepository(video)
    service = bare_pipeline(tmp_path, repository)

    download_audio_called = False
    whisper_called = False

    def mock_download_audio(*_args: object) -> Path:
        nonlocal download_audio_called
        download_audio_called = True
        return tmp_path / "audio.mp3"

    def mock_whisper(*_args: object) -> list[TranscriptSegment]:
        nonlocal whisper_called
        whisper_called = True
        return [
            TranscriptSegment(0.0, 5.0, "Transcripción de Whisper"),
            TranscriptSegment(5.0, 10.0, "Segunda parte de Whisper"),
        ]

    service.youtube = SimpleNamespace(
        extract_subtitles=lambda *_args: None,
        download_audio=mock_download_audio,
    )
    service.whisper = SimpleNamespace(transcribe=mock_whisper)
    service.chunker = SimpleNamespace(
        build=lambda segments, _s: [TranscriptChunk(0, "chunk 1", 0.0, 10.0)]
    )
    service.vectors = SimpleNamespace(index=lambda *_args: None)

    result = service.process_queued_ingest(100, FakeSession())

    assert download_audio_called, "download_audio debe llamarse como fallback"
    assert whisper_called, "Whisper debe llamarse como fallback"
    assert result["chunks_indexed"] == 1
    assert video.status == "indexed"
    assert video.progress_percent == 100
