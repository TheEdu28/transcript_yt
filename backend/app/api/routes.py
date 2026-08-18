"""Rutas FastAPI que exponen los tres casos de uso del núcleo."""

from collections.abc import Generator

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.errors import PipelineError
from app.db.database import SessionLocal
from app.schemas.contracts import IngestRequest, IngestResponse, QuizRequest, QuizResponse, SummaryRequest, SummaryResponse
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


@router.post("/materials/quiz", response_model=QuizResponse)
def generate_quiz(payload: QuizRequest, session: Session = Depends(get_session)) -> QuizResponse:
    """RF-03: crea preguntas respaldadas por timestamps de la transcripción."""
    try:
        return PipelineService().quiz(payload.video_id, payload.multiple_choice_count, payload.open_question_count, session)
    except PipelineError as error:
        raise_http(error)
