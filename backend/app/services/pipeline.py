"""Pipeline local: YouTube -> audio -> Whisper -> chunks -> ChromaDB -> Gemini RAG.

Las importaciones pesadas se realizan dentro de los métodos para que arrancar la API
no descargue modelos ni requiera GPU. Whisper y ChromaDB siempre se ejecutan localmente.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import PipelineError
from app.repositories.video_repository import VideoRepository
from app.schemas.contracts import BloomLevel, QuizResponse, SummaryResponse
from app.services.ingestion import (
    ChunkingService,
    SUPPORTED_LANGUAGES,
    TranscriptChunk,
    TranscriptSegment,
    VectorStoreService,
    VideoInfo,
    WhisperService,
    YouTubeService,
    is_supported_youtube_url,
    timestamp,
)
from app.services.material_service import MaterialService
from app.services.providers import (
    GeminiProvider,
    ModelProvider,
    OpenAIProvider,
    get_model_provider,
)

logger = logging.getLogger(__name__)


def build_evidence_context(evidence: list[dict[str, Any]], max_chars: int) -> str:
    """Format retrieved chunks within a hard prompt budget for Gemini's free tier."""
    if max_chars <= 0:
        return ""
    records: list[str] = []
    used = 0
    for item in evidence:
        start, end = str(item["start"]), str(item["end"])
        header = f"[{start} - {end}] "
        remaining = max_chars - used
        if remaining <= len(header):
            break
        text = str(item.get("text") or "").strip()
        record = header + text[: remaining - len(header)]
        if not record.strip():
            continue
        records.append(record)
        used += len(record) + 2
        if used >= max_chars:
            break
    return "\n\n".join(records)[:max_chars]


def normalize_json_response(raw_response: str) -> str:
    """Remove optional Markdown fences before validating a provider JSON response."""
    response = raw_response.strip()
    if not response.startswith("```"):
        return response
    lines = response.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def parse_grounded_summary(raw_response: str, evidence: list[dict[str, Any]]) -> SummaryResponse:
    """Parse Gemini JSON and reject summaries that cite timestamps not retrieved by RAG."""
    try:
        result = SummaryResponse.model_validate_json(normalize_json_response(raw_response))
    except ValidationError as error:
        invalid_fields = ", ".join(
            ".".join(str(part) for part in issue["loc"])
            for issue in error.errors(include_url=False)[:4]
        )
        raise PipelineError(
            f"Gemini devolvió un resumen con estructura inválida en: {invalid_fields or 'JSON'}.",
            code="INVALID_SUMMARY_RESPONSE",
            status_code=502,
        ) from error

    if len(result.synopsis.split()) > 200:
        raise PipelineError(
            "Gemini excedió el límite de 200 palabras.",
            code="SUMMARY_LENGTH_EXCEEDED",
            status_code=502,
        )

    available_timestamps = {
        str(value)
        for item in evidence
        for value in (item.get("start"), item.get("end"))
        if value is not None
    }
    cited_timestamps = [item.timestamp for item in result.glossary]
    cited_timestamps.extend(value for block in result.didactic_blocks for value in block.timestamps)
    unknown = sorted(set(cited_timestamps) - available_timestamps)
    if unknown:
        raise PipelineError(
            "El resumen cita timestamps que no pertenecen a la evidencia recuperada.",
            code="UNGROUNDED_TIMESTAMP",
            status_code=502,
        )
    if not result.evidence_sufficient and (result.glossary or result.didactic_blocks):
        raise PipelineError(
            "La respuesta insuficiente de Gemini contiene material no respaldado.",
            code="INCONSISTENT_EVIDENCE_RESPONSE",
            status_code=502,
        )
    return result


def parse_grounded_quiz(
    raw_response: str,
    evidence: list[dict[str, Any]],
    multiple_choice_count: int,
    open_question_count: int,
    bloom_levels: list[BloomLevel] | None = None,
) -> QuizResponse:
    """Parse and verify a quiz before exposing Gemini output through the API."""
    try:
        result = QuizResponse.model_validate_json(normalize_json_response(raw_response))
    except ValidationError as error:
        invalid_fields = ", ".join(
            ".".join(str(part) for part in issue["loc"])
            for issue in error.errors(include_url=False)[:4]
        )
        raise PipelineError(
            f"Gemini devolvió un cuestionario con estructura inválida en: {invalid_fields or 'JSON'}.",
            code="INVALID_QUIZ_RESPONSE",
            status_code=502,
        ) from error

    available_timestamps = {
        str(value)
        for item in evidence
        for value in (item.get("start"), item.get("end"))
        if value is not None
    }
    cited_timestamps = [item.evidence_timestamp for item in result.multiple_choice]
    cited_timestamps.extend(item.evidence_timestamp for item in result.open_questions)
    unknown = sorted(set(cited_timestamps) - available_timestamps)
    if unknown:
        raise PipelineError(
            "El cuestionario cita timestamps que no pertenecen a la evidencia recuperada.",
            code="UNGROUNDED_TIMESTAMP",
            status_code=502,
        )
    if not result.evidence_sufficient:
        if result.multiple_choice or result.open_questions:
            raise PipelineError(
                "La respuesta insuficiente de Gemini contiene preguntas no respaldadas.",
                code="INCONSISTENT_EVIDENCE_RESPONSE",
                status_code=502,
            )
        return result
    if len(result.multiple_choice) != multiple_choice_count or len(result.open_questions) != open_question_count:
        raise PipelineError(
            "Gemini no devolvió la cantidad de preguntas solicitada.",
            code="QUIZ_COUNT_MISMATCH",
            status_code=502,
        )
    allowed_levels = set(bloom_levels or list(BloomLevel))
    generated_levels = [item.bloom_level for item in result.multiple_choice]
    generated_levels.extend(item.bloom_level for item in result.open_questions)
    if set(generated_levels) - allowed_levels:
        raise PipelineError(
            "Gemini generó preguntas fuera de los niveles de Bloom solicitados.",
            code="UNREQUESTED_BLOOM_LEVEL",
            status_code=502,
        )
    for question in result.multiple_choice:
        normalized_options = [option.strip().casefold() for option in question.options]
        if len(set(normalized_options)) != len(normalized_options):
            raise PipelineError(
                "Gemini devolvió opciones repetidas en una pregunta de selección múltiple.",
                code="DUPLICATE_QUIZ_OPTIONS",
                status_code=502,
            )
    return result


class GeminiService(ModelProvider):
    """Fachada compatible con código existente que delega en el ModelProvider configurado."""

    SYSTEM_INSTRUCTION = ModelProvider.SYSTEM_INSTRUCTION

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        provider_name: str | None = None,
        model_id: str | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.provider = get_model_provider(self.settings, provider_name=provider_name, model_id=model_id)

    def generate_json(
        self,
        task: str,
        evidence: list[dict[str, Any]],
        response_schema: type[BaseModel] | None = None,
    ) -> str:
        return self.provider.generate_json(task, evidence, response_schema)


class PipelineService:
    """Orquesta RF-01 de punta a punta y conserva la trazabilidad en disco/SQLite."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.youtube = YouTubeService()
        self.whisper = WhisperService()
        self.chunker = ChunkingService()
        self.vectors = VectorStoreService(self.settings)
        self.repository = VideoRepository()

    def queue_ingest(self, url: str, session: Session, *, owner_id: int | None = None) -> dict[str, Any]:
        """Validate metadata and create a pollable job before expensive local work begins."""
        video_info = self.youtube.inspect(url, self.settings)
        existing = self.repository.get_by_youtube_id(session, video_info.youtube_id)
        if existing and existing.status == "indexed":
            return {
                "video_id": existing.id,
                "status": existing.status,
                "progress_stage": existing.progress_stage,
                "progress_percent": existing.progress_percent,
                "queued": False,
            }
        if existing and existing.status in {"queued", "processing"}:
            return {
                "video_id": existing.id,
                "status": existing.status,
                "progress_stage": existing.progress_stage,
                "progress_percent": existing.progress_percent,
                "queued": False,
            }
        transcript_path = self.settings.raw_transcripts_directory / f"{video_info.youtube_id}.json"
        video = existing or self.repository.create(
            session,
            youtube_id=video_info.youtube_id,
            source_url=video_info.url,
            title=video_info.title,
            language=video_info.language,
            duration_seconds=video_info.duration_seconds,
            transcript_path=str(transcript_path),
            status="queued",
            progress_stage="queued",
            progress_percent=0,
            processing_seconds=0.0,
            owner_id=owner_id,
        )
        if existing:
            self.repository.update_progress(session, video, "queued", 0, status="queued")
        return {
            "video_id": video.id,
            "status": video.status,
            "progress_stage": video.progress_stage,
            "progress_percent": video.progress_percent,
            "queued": True,
        }

    def ingest(self, url: str, session: Session, *, owner_id: int | None = None) -> dict[str, Any]:
        """Preserve the original synchronous endpoint while using the same job state machine."""
        job = self.queue_ingest(url, session, owner_id=owner_id)
        if job["status"] == "indexed":
            video = self.repository.get(session, job["video_id"])
            assert video is not None
            return self._ingest_result(video, chunks_indexed=0)
        if not job["queued"]:
            raise PipelineError("El video ya se está procesando.", code="VIDEO_ALREADY_PROCESSING", status_code=409)
        return self.process_queued_ingest(job["video_id"], session)

    def process_queued_ingest(self, video_id: int, session: Session) -> dict[str, Any]:
        """Run the local ingestion stages and publish their state for HU-02 polling."""
        video = self.repository.get(session, video_id)
        if not video:
            raise PipelineError("El video no existe.", code="VIDEO_NOT_FOUND", status_code=404)
        started = time.perf_counter()
        video_info = VideoInfo(
            video.youtube_id, video.source_url, video.title, video.duration_seconds, video.language
        )
        transcript_path = Path(video.transcript_path)
        try:
            segments: list[TranscriptSegment] | None = None
            if hasattr(self.youtube, "extract_subtitles"):
                try:
                    self.repository.update_progress(session, video, "fetching_subtitles", 10)
                    segments = self.youtube.extract_subtitles(video_info, self.settings)
                except Exception:
                    segments = None

            if not segments:
                self.repository.update_progress(session, video, "downloading_audio", 15)
                audio_path = self.youtube.download_audio(video_info, self.settings)
                self.repository.update_progress(session, video, "transcribing", 35)
                segments = self.whisper.transcribe(audio_path, video_info.language, self.settings)
            transcript_path.write_text(
                json.dumps([asdict(s) for s in segments], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            self.repository.update_progress(session, video, "chunking", 65)
            chunks = self.chunker.build(segments, self.settings)
            self.repository.update_progress(session, video, "indexing", 75)
            self.vectors.index(video.id, chunks)
            elapsed = round(time.perf_counter() - started, 2)
            video.status, video.progress_stage, video.progress_percent = "indexed", "completed", 100
            video.processing_seconds = elapsed
            session.commit()
            return self._ingest_result(video, chunks_indexed=len(chunks))
        except PipelineError:
            video.status, video.progress_stage = "failed", "failed"
            session.commit()
            raise
        except Exception as error:
            video.status, video.progress_stage = "failed", "failed"
            session.commit()
            raise PipelineError("Falló el pipeline de ingesta.", code="INGESTION_FAILED", status_code=500) from error

    def summary(
        self,
        video_id: int,
        focus: str,
        session: Session,
        *,
        model_provider: str | None = None,
        model_id: str | None = None,
        owner_id: int | None = None,
    ) -> SummaryResponse:
        self._assert_indexed(video_id, session)
        evidence = self.vectors.retrieve(video_id, focus)
        prompt = """Genera el resumen didáctico solicitado a partir de la evidencia. La sinopsis debe
tener menos de 200 palabras. Los timestamps deben tener el formato HH:MM:SS y coincidir exactamente
con los límites de tiempo presentes en la evidencia recuperada."""
        raw_response = GeminiService(self.settings, provider_name=model_provider, model_id=model_id).generate_json(
            prompt, evidence, response_schema=SummaryResponse,
        )
        video = self.repository.get(session, video_id)
        effective_owner = owner_id if owner_id is not None else (video.owner_id if video else None)
        return MaterialService().save_generated(
            session,
            video_id,
            "summary",
            parse_grounded_summary(raw_response, evidence),
            owner_id=effective_owner,
        )

    def quiz(
        self,
        video_id: int,
        multiple_choice_count: int,
        open_question_count: int,
        bloom_levels: list[BloomLevel],
        session: Session,
        *,
        model_provider: str | None = None,
        model_id: str | None = None,
        owner_id: int | None = None,
    ) -> QuizResponse:
        self._assert_indexed(video_id, session)
        evidence = self.vectors.retrieve(video_id, "hechos, definiciones, procesos y ejemplos para evaluación")
        prompt = f"""Genera JSON válido con multiple_choice, open_questions, evidence_sufficient,
insufficiency_note. Genera exactamente {multiple_choice_count} preguntas de opción múltiple y
{open_question_count} abiertas. Cada múltiple debe contener question, options (exactamente 4),
correct_option (índice 0-3), explanation y evidence_timestamp. Los tres distractores deben provenir
de conceptos mencionados en la evidencia, pero ser incorrectos para la pregunta. Cada abierta contiene
question, expected_points y evidence_timestamp. Toda pregunta debe contener bloom_level y usar sólo
uno de estos niveles solicitados: {', '.join(level.value for level in bloom_levels)}. Si la evidencia no basta, establece
evidence_sufficient=false, explica la insuficiencia y devuelve ambas listas vacías. No inventes
contenido ni timestamps."""
        raw_response = GeminiService(self.settings, provider_name=model_provider, model_id=model_id).generate_json(
            prompt, evidence, response_schema=QuizResponse,
        )
        video = self.repository.get(session, video_id)
        effective_owner = owner_id if owner_id is not None else (video.owner_id if video else None)
        return MaterialService().save_generated(
            session,
            video_id,
            "quiz",
            parse_grounded_quiz(raw_response, evidence, multiple_choice_count, open_question_count, bloom_levels),
            owner_id=effective_owner,
        )

    @staticmethod
    def _ingest_result(video: Any, chunks_indexed: int) -> dict[str, Any]:
        """Return the established synchronous-ingestion response contract."""
        return {
            "video_id": video.id,
            "title": video.title,
            "language": video.language,
            "duration_seconds": video.duration_seconds,
            "chunks_indexed": chunks_indexed,
            "processing_seconds": video.processing_seconds,
        }

    def _assert_indexed(self, video_id: int, session: Session) -> None:
        video = self.repository.get(session, video_id)
        if not video:
            raise PipelineError("El video no existe.", code="VIDEO_NOT_FOUND", status_code=404)
        if video.status != "indexed":
            raise PipelineError("El video aún no está indexado.", code="VIDEO_NOT_INDEXED", status_code=409)


# Re-exportaciones públicas para compatibilidad 100% retroactiva
__all__ = [
    "ChunkingService",
    "GeminiProvider",
    "GeminiService",
    "ModelProvider",
    "OpenAIProvider",
    "PipelineService",
    "SUPPORTED_LANGUAGES",
    "TranscriptChunk",
    "TranscriptSegment",
    "VectorStoreService",
    "VideoInfo",
    "WhisperService",
    "YouTubeService",
    "YOUTUBE_HOSTS",
    "build_evidence_context",
    "is_supported_youtube_url",
    "normalize_json_response",
    "parse_grounded_quiz",
    "parse_grounded_summary",
    "timestamp",
]
