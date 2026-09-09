"""Rutas FastAPI que exponen los tres casos de uso del núcleo."""

from collections.abc import Generator

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import PipelineError
from app.db.database import SessionLocal
from app.repositories.video_repository import VideoRepository
from app.schemas.contracts import (
    ExportFormat, FeedbackRequest, FeedbackResponse, IngestAcceptedResponse, IngestRequest, IngestResponse,
    MaterialResponse, MaterialUpdateRequest, ProgressResponse, QuizRequest, QuizResponse, SummaryRequest, SummaryResponse,
)
from app.services.export_service import ExportService
from app.services.feedback_service import FeedbackService
from app.services.material_service import MaterialService
from app.services.pipeline import PipelineService

router = APIRouter(prefix="/api/v1", tags=["pipeline"])


def get_session() -> Generator[Session, None, None]:
    """Provide one SQLite session per request."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def raise_http(error: PipelineError) -> None:
    """Do not leak provider details; expose a stable functional error code."""
    raise HTTPException(status_code=error.status_code, detail={"code": error.code, "message": str(error)})


def process_ingest_job(video_id: int) -> None:
    """Run a queued job with its own SQLite session after the HTTP response is sent."""
    session = SessionLocal()
    try:
        PipelineService().process_queued_ingest(video_id, session)
    except PipelineError:
        # The pipeline has already persisted a stable failed status for polling clients.
        pass
    finally:
        session.close()


@router.get("/health")
def health() -> dict[str, str]:
    """Confirma que el proceso API está disponible sin cargar los modelos."""
    return {"status": "ok"}


@router.post("/videos/ingest", response_model=IngestResponse, status_code=status.HTTP_201_CREATED)
def ingest_video(payload: IngestRequest, session: Session = Depends(get_session)) -> IngestResponse:
    """RF-01: valida, extrae, transcribe e indexa un video público de hasta 60 min."""
    try:
        return IngestResponse(**PipelineService().ingest(str(payload.url), session))
    except PipelineError as error:
        raise_http(error)


@router.post("/videos/ingest/async", response_model=IngestAcceptedResponse, status_code=status.HTTP_202_ACCEPTED)
def ingest_video_async(
    payload: IngestRequest, background_tasks: BackgroundTasks, session: Session = Depends(get_session),
) -> IngestAcceptedResponse:
    """HU-02: queue local work and immediately return a resource to poll for progress."""
    try:
        job = PipelineService().queue_ingest(str(payload.url), session)
        if job["queued"]:
            background_tasks.add_task(process_ingest_job, job["video_id"])
        return IngestAcceptedResponse(**job)
    except PipelineError as error:
        raise_http(error)


@router.get("/videos/{video_id}/progress", response_model=ProgressResponse)
def get_ingestion_progress(video_id: int, session: Session = Depends(get_session)) -> ProgressResponse:
    """HU-02: retrieve the latest durable stage and percentage of an ingestion job."""
    video = VideoRepository().get(session, video_id)
    if not video:
        raise_http(PipelineError("El video no existe.", code="VIDEO_NOT_FOUND", status_code=404))
    return ProgressResponse(
        video_id=video.id, status=video.status, progress_stage=video.progress_stage,
        progress_percent=video.progress_percent, processing_seconds=video.processing_seconds,
    )


@router.post(
    "/materials/summary", response_model=SummaryResponse,
    responses={409: {"description": "Video sin indexar"}, 422: {"description": "Sin evidencia RAG"},
               503: {"description": "Gemini no disponible temporalmente"},
               502: {"description": "Respuesta Gemini inválida o no fundamentada"}},
)
def generate_summary(payload: SummaryRequest, session: Session = Depends(get_session)) -> SummaryResponse:
    """RF-02: recupera contexto local y solicita la salida didáctica grounded a Gemini."""
    try:
        return PipelineService().summary(payload.video_id, payload.focus, session)
    except PipelineError as error:
        raise_http(error)


@router.post(
    "/materials/quiz", response_model=QuizResponse,
    responses={409: {"description": "Video sin indexar"}, 422: {"description": "Sin evidencia RAG"},
               503: {"description": "Gemini no disponible temporalmente"},
               502: {"description": "Respuesta Gemini inválida o no fundamentada"}},
)
def generate_quiz(payload: QuizRequest, session: Session = Depends(get_session)) -> QuizResponse:
    """RF-03: crea preguntas respaldadas por timestamps de la transcripción."""
    try:
        return PipelineService().quiz(
            payload.video_id, payload.multiple_choice_count, payload.open_question_count,
            payload.bloom_levels, session,
        )
    except PipelineError as error:
        raise_http(error)


@router.get("/materials/{material_id}", response_model=MaterialResponse)
def get_material(material_id: int, session: Session = Depends(get_session)) -> MaterialResponse:
    """HU-06: consult a generated material before deciding whether to edit it."""
    try:
        return MaterialService().get(session, material_id)
    except PipelineError as error:
        raise_http(error)


@router.put("/materials/{material_id}", response_model=MaterialResponse)
def update_material(
    material_id: int, payload: MaterialUpdateRequest, session: Session = Depends(get_session),
) -> MaterialResponse:
    """HU-06: persist a validated full-content edit without regenerating it."""
    try:
        return MaterialService().update(session, material_id, payload.content)
    except PipelineError as error:
        raise_http(error)


@router.post("/materials/{material_id}/feedback", response_model=FeedbackResponse)
def evaluate_quiz_attempt(
    material_id: int, payload: FeedbackRequest, session: Session = Depends(get_session),
) -> FeedbackResponse:
    """HU-09: provide immediate quiz feedback, grounded for open answers."""
    try:
        return FeedbackService().evaluate(session, material_id, payload)
    except PipelineError as error:
        raise_http(error)


@router.get("/materials/{material_id}/export")
def export_material(
    material_id: int, format: ExportFormat = "markdown", session: Session = Depends(get_session),
) -> FileResponse:
    """HU-07: create and download a local JSON or Markdown version of a material."""
    try:
        material = MaterialService().get(session, material_id)
        path = ExportService(get_settings()).export(material, format)
    except PipelineError as error:
        raise_http(error)
    media_type = "application/json" if format == "json" else "text/markdown"
    return FileResponse(path, media_type=media_type, filename=path.name)
