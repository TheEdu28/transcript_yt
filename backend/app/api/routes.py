"""Rutas FastAPI que exponen los tres casos de uso del núcleo."""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import PipelineError
from app.db.database import SessionLocal, get_session
from app.repositories.video_repository import VideoRepository
from app.schemas.contracts import (
    ExportFormat, FeedbackRequest, FeedbackResponse, IngestAcceptedResponse, IngestRequest, IngestResponse,
    MaterialResponse, MaterialUpdateRequest, MaterialVersionsResponse, ModelsResponse, ProgressResponse,
    QuizRequest, QuizResponse, SummaryRequest, SummaryResponse, VideoHistoryResponse,
)
from app.services.auth_service import get_current_user
from app.models.user import User
from app.models.group import GroupMember, Topic
from app.services.export_service import ExportService
from app.services.feedback_service import FeedbackService
from app.services.material_service import MaterialService
from app.services.pipeline import PipelineService
from app.services.providers import list_available_models, list_available_providers

router = APIRouter(prefix="/api/v1", tags=["pipeline"])

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


@router.get("/models", response_model=ModelsResponse)
def list_models() -> ModelsResponse:
    """Lista los modelos disponibles consultando las APIs de Gemini y Groq dinámicamente."""
    return ModelsResponse(**list_available_models(get_settings()))


@router.get("/videos", response_model=VideoHistoryResponse)
def list_my_videos(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> VideoHistoryResponse:
    """Historial paginado de videos ingestados por el usuario autenticado."""
    items, total = VideoRepository().list_by_owner(session, current_user.id, page=page, page_size=page_size, status=status)
    return VideoHistoryResponse(items=items, total=total, page=page, page_size=page_size)


@router.delete("/videos/{video_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_video(
    video_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> None:
    """Elimina un video propio de SQLite y sus vectores de ChromaDB."""
    repo = VideoRepository()
    video = repo.get(session, video_id)
    if not video:
        raise_http(PipelineError("El video no existe.", code="VIDEO_NOT_FOUND", status_code=404))
    if video.owner_id != current_user.id:
        raise_http(PipelineError("No tienes permiso para eliminar este video.", code="FORBIDDEN", status_code=403))
    PipelineService().vectors.delete_by_video(video_id)
    repo.delete(session, video)


@router.post("/videos/ingest", response_model=IngestResponse, status_code=status.HTTP_201_CREATED)
def ingest_video(
    payload: IngestRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> IngestResponse:
    """RF-01: valida, extrae, transcribe e indexa un video público de hasta 60 min."""
    try:
        return IngestResponse(**PipelineService().ingest(str(payload.url), session, owner_id=current_user.id))
    except PipelineError as error:
        raise_http(error)


@router.post("/videos/ingest/async", response_model=IngestAcceptedResponse, status_code=status.HTTP_202_ACCEPTED)
def ingest_video_async(
    payload: IngestRequest, background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> IngestAcceptedResponse:
    """HU-02: queue local work and immediately return a resource to poll for progress."""
    try:
        job = PipelineService().queue_ingest(str(payload.url), session, owner_id=current_user.id)
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
        return PipelineService().summary(payload.video_id, payload.focus, session, model_provider=payload.model_provider, model_id=payload.model_id)
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
            payload.bloom_levels, session, model_provider=payload.model_provider, model_id=payload.model_id,
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
    material_id: int,
    payload: MaterialUpdateRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> MaterialResponse:
    """HU-06: edita un material validando esquema y guardando snapshot de versión.

    Permitido si el usuario es dueño del video O admin de algún grupo donde el
    material está publicado como tema.
    """
    svc = MaterialService()
    material = svc.repository.get(session, material_id)
    if not material:
        raise_http(PipelineError("El material no existe.", code="MATERIAL_NOT_FOUND", status_code=404))

    if not svc.can_edit(session, material_id, current_user.id):
        raise_http(PipelineError(
            "Solo el dueño del video o el admin de un grupo donde está publicado puede editar este material.",
            code="FORBIDDEN", status_code=403,
        ))
    try:
        return svc.update(session, material_id, payload.content, edited_by=current_user.id)
    except PipelineError as error:
        raise_http(error)


@router.get("/materials/{material_id}/versions", response_model=MaterialVersionsResponse)
def list_material_versions(
    material_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> MaterialVersionsResponse:
    """Devuelve el historial de versiones de un material (sin contenido completo)."""
    try:
        versions = MaterialService().list_versions(session, material_id)
        return MaterialVersionsResponse(material_id=material_id, versions=versions)
    except PipelineError as error:
        raise_http(error)


@router.post("/materials/{material_id}/versions/{version_id}/restore", response_model=MaterialResponse)
def restore_material_version(
    material_id: int,
    version_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> MaterialResponse:
    """Restaura una versión previa y guarda el contenido actual como otra versión."""
    svc = MaterialService()
    material = svc.repository.get(session, material_id)
    if not material:
        raise_http(PipelineError("El material no existe.", code="MATERIAL_NOT_FOUND", status_code=404))
    if not svc.can_edit(session, material_id, current_user.id):
        raise_http(PipelineError(
            "Solo el dueño del video o el admin de un grupo donde está publicado puede restaurar este material.",
            code="FORBIDDEN", status_code=403,
        ))
    try:
        return svc.restore(session, material_id, version_id, edited_by=current_user.id)
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
    """HU-07: create and download a local JSON, Markdown, PDF or DOCX version."""
    try:
        material = MaterialService().get(session, material_id)
        path = ExportService(get_settings()).export(material, format)
    except PipelineError as error:
        raise_http(error)
    media_types = {
        "json": "application/json",
        "markdown": "text/markdown",
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
    media_type = media_types[format]
    return FileResponse(path, media_type=media_type, filename=path.name)
