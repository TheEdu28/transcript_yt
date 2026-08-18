"""Pipeline local: YouTube -> audio -> Whisper -> chunks -> ChromaDB -> Gemini RAG.

Las importaciones pesadas se realizan dentro de los métodos para que arrancar la API
no descargue modelos ni requiera GPU. Whisper y ChromaDB siempre se ejecutan localmente.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import PipelineError
from app.repositories.video_repository import VideoRepository
from app.schemas.contracts import QuizResponse, SummaryResponse

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


@dataclass(frozen=True)
class TranscriptSegment:
    """Texto puntuado de Whisper y su intervalo de respaldo."""

    start: float
    end: float
    text: str


@dataclass(frozen=True)
class TranscriptChunk:
    """Fragmento semántico que se vectoriza junto con su evidencia temporal."""

    index: int
    text: str
    start: float
    end: float


def timestamp(seconds: float) -> str:
    """Format seconds as HH:MM:SS for outputs and Chroma metadata."""
    total = max(0, round(seconds))
    return f"{total // 3600:02d}:{(total % 3600) // 60:02d}:{total % 60:02d}"


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
        used += len(record) + 2  # Separador entre evidencia sin exceder el límite.
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
            code="INVALID_SUMMARY_RESPONSE", status_code=502,
        ) from error

    if len(result.synopsis.split()) > 200:
        raise PipelineError(
            "Gemini excedió el límite de 200 palabras.", code="SUMMARY_LENGTH_EXCEEDED", status_code=502,
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
            code="UNGROUNDED_TIMESTAMP", status_code=502,
        )
    if not result.evidence_sufficient and (result.glossary or result.didactic_blocks):
        raise PipelineError(
            "La respuesta insuficiente de Gemini contiene material no respaldado.",
            code="INCONSISTENT_EVIDENCE_RESPONSE", status_code=502,
        )
    return result


def is_supported_youtube_url(url: str) -> bool:
    """Accept only HTTP(S) URLs that identify a YouTube video, not a playlist."""
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
                "quiet": False, "no_warnings": False, "noplaylist": True,
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
                code="VIDEO_UNAVAILABLE", status_code=403,
            ) from error

        return self._validate_metadata(info, url, settings)

    def _validate_metadata(self, info: dict[str, Any], url: str, settings: Settings) -> VideoInfo:
        """Validate extractor metadata before any audio download (HU-01, HU-10)."""
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

        # yt-dlp expone el idioma declarado; cuando falta, se consultan subtítulos.
        language = self._declared_language(info)
        if language not in SUPPORTED_LANGUAGES:
            raise PipelineError(
                "El video debe declarar español o inglés para poder procesarse.",
                code="UNSUPPORTED_LANGUAGE", status_code=422,
            )
        youtube_id = str(info.get("id") or "")
        if not youtube_id:
            raise PipelineError("YouTube no devolvió un identificador de video.", code="MISSING_VIDEO_ID")
        return VideoInfo(
            youtube_id=youtube_id, url=url, title=str(info.get("title") or youtube_id),
            duration_seconds=duration, language=language,
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
        """Extrae audio MP3 localmente, sólo después de aprobar RF-01."""
        from yt_dlp import YoutubeDL

        output_template = str(settings.audio_directory / f"{video.youtube_id}.%(ext)s")
        cookies_path = settings.resolved_yt_dlp_cookie_file
        options = {
            "format": "bestaudio/best", "outtmpl": output_template, "noplaylist": True,
            "quiet": True, "no_warnings": True,
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


class WhisperService:
    """Transcripción local con timestamps de segmento y puntuación de Whisper."""

    _model: Any = None

    def transcribe(self, audio_path: Path, language: str, settings: Settings) -> list[TranscriptSegment]:
        from faster_whisper import WhisperModel

        if self._model is None:
            self._model = WhisperModel(settings.whisper_model, device=settings.whisper_device,
                                       compute_type=settings.whisper_compute_type)
        segments, detected = self._model.transcribe(
            str(audio_path), language=language, task="transcribe", vad_filter=True,
            beam_size=3, word_timestamps=False,
        )
        if detected.language not in SUPPORTED_LANGUAGES:
            raise PipelineError("Whisper detectó un idioma no permitido.", code="UNSUPPORTED_LANGUAGE")
        result = [TranscriptSegment(round(s.start, 2), round(s.end, 2), s.text.strip()) for s in segments if s.text.strip()]
        if not result:
            raise PipelineError("No se detectó voz transcribible en el video.", code="EMPTY_TRANSCRIPT")
        return result


class ChunkingService:
    """Agrupa segmentos completos; el solapamiento conserva continuidad semántica."""

    def build(self, segments: list[TranscriptSegment], settings: Settings) -> list[TranscriptChunk]:
        chunks: list[TranscriptChunk] = []
        start_index = 0
        while start_index < len(segments):
            end_index, word_count = start_index, 0
            while end_index < len(segments) and word_count < settings.chunk_words:
                word_count += len(segments[end_index].text.split())
                end_index += 1
            current = segments[start_index:end_index]
            chunks.append(TranscriptChunk(
                index=len(chunks), text=" ".join(segment.text for segment in current),
                start=current[0].start, end=current[-1].end,
            ))
            if end_index >= len(segments):
                break
            # Avanzar al menos un segmento evita ciclos para segmentos largos.
            start_index = max(start_index + 1, end_index - settings.chunk_overlap_segments)
        return chunks


class VectorStoreService:
    """Embeddings locales con all-MiniLM-L6-v2 y colección Chroma persistente."""

    _embedder: Any = None

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        import chromadb
        self.client = chromadb.PersistentClient(path=str(settings.chroma_persist_directory))
        self.collection = self.client.get_or_create_collection(
            name=settings.chroma_collection_name, metadata={"hnsw:space": "cosine"},
        )

    def _encoder(self) -> Any:
        if self._embedder is None:
            from sentence_transformers import SentenceTransformer
            self._embedder = SentenceTransformer(self.settings.embedding_model)
        return self._embedder

    def index(self, video_id: int, chunks: list[TranscriptChunk]) -> None:
        """Genera vectores localmente y reemplaza índices repetidos de forma idempotente."""
        documents = [chunk.text for chunk in chunks]
        embeddings = self._encoder().encode(documents, normalize_embeddings=True).tolist()
        self.collection.upsert(
            ids=[f"{video_id}:{chunk.index}" for chunk in chunks], documents=documents, embeddings=embeddings,
            metadatas=[{"video_id": video_id, "chunk_index": chunk.index,
                        "start": timestamp(chunk.start), "end": timestamp(chunk.end)} for chunk in chunks],
        )

    def retrieve(self, video_id: int, query: str) -> list[dict[str, Any]]:
        """Recupera pocos chunks, limitando después el contexto por caracteres."""
        # Chroma rechaza un n_results mayor que los registros filtrados; calcularlo
        # también evita enviar solicitudes inútiles a Gemini para un video vacío.
        available = len(self.collection.get(where={"video_id": video_id}, include=[]).get("ids", []))
        if not available:
            return []
        vector = self._encoder().encode([query], normalize_embeddings=True).tolist()
        result = self.collection.query(
            query_embeddings=vector, n_results=min(self.settings.rag_retrieval_limit, available),
            where={"video_id": video_id}, include=["documents", "metadatas", "distances"],
        )
        documents = result.get("documents", [[]])[0]
        metadata = result.get("metadatas", [[]])[0]
        return [{"text": text, **meta} for text, meta in zip(documents, metadata)]


class GeminiService:
    """Cliente Gemini que limita el contexto y fuerza JSON basado en evidencia RAG."""

    SYSTEM_INSTRUCTION = """Eres un generador didáctico con groundedness estricto.
Usa exclusivamente la EVIDENCIA RECUPERADA. No uses conocimientos externos ni inventes hechos,
definiciones, distractores o timestamps. Si la evidencia no basta, devuelve evidence_sufficient=false,
explica insuficiencia y deja las listas vacías. Cada timestamp debe existir en la evidencia."""

    def __init__(self, settings: Settings) -> None:
        if not settings.gemini_api_key:
            raise PipelineError("Falta GEMINI_API_KEY en el entorno.", code="GEMINI_API_KEY_MISSING", status_code=503)
        self.settings = settings

    def generate_json(
        self,
        task: str,
        evidence: list[dict[str, Any]],
        response_schema: type[BaseModel] | None = None,
    ) -> str:
        from google import genai
        from google.genai import types

        # Tope por caracteres: aprox. 3k tokens de entrada para no agotar la capa gratuita.
        context = build_evidence_context(evidence, self.settings.max_gemini_context_chars)
        if not context:
            raise PipelineError("No hay evidencia indexada suficiente.", code="NO_RAG_EVIDENCE", status_code=422)
        client = genai.Client(api_key=self.settings.gemini_api_key)
        config = types.GenerateContentConfig(
            system_instruction=self.SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
            temperature=0.1,
            max_output_tokens=self.settings.max_gemini_output_tokens,
            response_schema=response_schema,
        )
        for attempt in range(2):
            try:
                response = client.models.generate_content(
                    model=self.settings.gemini_model,
                    contents=f"{task}\n\nEVIDENCIA RECUPERADA:\n{context}",
                    config=config,
                )
                break
            except Exception as error:
                status_code = getattr(error, "status_code", None)
                if status_code in {429, 500, 503} and attempt == 0:
                    time.sleep(1)
                    continue
                if status_code in {429, 500, 503}:
                    raise PipelineError(
                        "Gemini no está disponible temporalmente. Intenta de nuevo en unos segundos.",
                        code="GEMINI_UNAVAILABLE", status_code=503,
                    ) from error
                raise PipelineError(
                    "Gemini no pudo generar el recurso solicitado.",
                    code="GEMINI_REQUEST_FAILED", status_code=502,
                ) from error
        if not response.text:
            raise PipelineError("Gemini no devolvió contenido.", code="EMPTY_GEMINI_RESPONSE", status_code=502)
        return response.text


class PipelineService:
    """Orquesta RF-01 de punta a punta y conserva la trazabilidad en disco/SQLite."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.youtube = YouTubeService()
        self.whisper = WhisperService()
        self.chunker = ChunkingService()
        self.vectors = VectorStoreService(self.settings)
        self.repository = VideoRepository()

    def ingest(self, url: str, session: Session) -> dict[str, Any]:
        started = time.perf_counter()
        video_info = self.youtube.inspect(url, self.settings)  # 1. validar antes de descargar
        existing = self.repository.get_by_youtube_id(session, video_info.youtube_id)
        if existing and existing.status == "indexed":
            return {"video_id": existing.id, "title": existing.title, "language": existing.language,
                    "duration_seconds": existing.duration_seconds, "chunks_indexed": 0,
                    "processing_seconds": existing.processing_seconds}
        transcript_path = self.settings.raw_transcripts_directory / f"{video_info.youtube_id}.json"
        video = existing or self.repository.create(
            session, youtube_id=video_info.youtube_id, source_url=video_info.url, title=video_info.title,
            language=video_info.language, duration_seconds=video_info.duration_seconds,
            transcript_path=str(transcript_path), status="processing", processing_seconds=0.0,
        )
        try:
            audio_path = self.youtube.download_audio(video_info, self.settings)  # 2. audio
            segments = self.whisper.transcribe(audio_path, video_info.language, self.settings)  # 3. Whisper
            transcript_path.write_text(json.dumps([asdict(s) for s in segments], ensure_ascii=False, indent=2), encoding="utf-8")
            chunks = self.chunker.build(segments, self.settings)  # 4. chunks con solapamiento
            self.vectors.index(video.id, chunks)  # 5-6. embeddings + Chroma persistente
            elapsed = round(time.perf_counter() - started, 2)
            video.status, video.processing_seconds = "indexed", elapsed
            session.commit()
            return {"video_id": video.id, "title": video.title, "language": video.language,
                    "duration_seconds": video.duration_seconds, "chunks_indexed": len(chunks),
                    "processing_seconds": elapsed}
        except PipelineError:
            video.status = "failed"
            session.commit()
            raise
        except Exception as error:
            video.status = "failed"
            session.commit()
            raise PipelineError("Falló el pipeline de ingesta.", code="INGESTION_FAILED", status_code=500) from error

    def summary(self, video_id: int, focus: str, session: Session) -> SummaryResponse:
        self._assert_indexed(video_id, session)
        evidence = self.vectors.retrieve(video_id, focus)
        prompt = """Genera el resumen didáctico solicitado a partir de la evidencia. La sinopsis debe
tener menos de 200 palabras. Los timestamps deben tener el formato HH:MM:SS y coincidir exactamente
con los límites de tiempo presentes en la evidencia recuperada."""
        raw_response = GeminiService(self.settings).generate_json(
            prompt, evidence, response_schema=SummaryResponse,
        )
        return parse_grounded_summary(raw_response, evidence)

    def quiz(self, video_id: int, multiple_choice_count: int, open_question_count: int, session: Session) -> QuizResponse:
        self._assert_indexed(video_id, session)
        evidence = self.vectors.retrieve(video_id, "hechos, definiciones, procesos y ejemplos para evaluación")
        prompt = f"""Genera JSON válido con multiple_choice, open_questions, evidence_sufficient,
insufficiency_note. Genera exactamente {multiple_choice_count} preguntas de opción múltiple y
{open_question_count} abiertas. Cada múltiple debe contener question, options (exactamente 4),
correct_option (índice 0-3), explanation y evidence_timestamp. Los tres distractores deben provenir
de conceptos mencionados en la evidencia, pero ser incorrectos para la pregunta. Cada abierta contiene
question, expected_points y evidence_timestamp. No inventes contenido ni timestamps."""
        return QuizResponse.model_validate_json(GeminiService(self.settings).generate_json(prompt, evidence))

    def _assert_indexed(self, video_id: int, session: Session) -> None:
        video = self.repository.get(session, video_id)
        if not video:
            raise PipelineError("El video no existe.", code="VIDEO_NOT_FOUND", status_code=404)
        if video.status != "indexed":
            raise PipelineError("El video aún no está indexado.", code="VIDEO_NOT_INDEXED", status_code=409)
