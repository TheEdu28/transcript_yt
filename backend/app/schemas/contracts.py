"""Contratos de API y formatos estrictos que Gemini debe producir."""

from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import AnyHttpUrl, BaseModel, Field

Timestamp = Annotated[str, Field(pattern=r"^\d{2}:\d{2}:\d{2}$")]


class IngestRequest(BaseModel):
    """URL que inicia el pipeline completo de RF-01."""

    url: AnyHttpUrl


class IngestResponse(BaseModel):
    """Resultado de una ingesta sincronizada e indexada."""

    video_id: int
    title: str
    language: str
    duration_seconds: int
    chunks_indexed: int
    processing_seconds: float


class IngestAcceptedResponse(BaseModel):
    """Trabajo de ingesta que puede consultarse mientras se ejecuta en segundo plano."""

    video_id: int
    status: str
    progress_stage: str
    progress_percent: int = Field(ge=0, le=100)


class ProgressResponse(IngestAcceptedResponse):
    """Estado actual de HU-02 para sondeo desde la interfaz."""

    processing_seconds: float


class SummaryRequest(BaseModel):
    """Solicitud de RF-02; la consulta cambia la recuperación RAG."""

    video_id: int
    focus: str = Field(default="ideas principales, conceptos, definiciones y procesos", max_length=300)


class GlossaryItem(BaseModel):
    term: str
    definition: str
    timestamp: Timestamp


class DidacticBlock(BaseModel):
    title: str
    explanation: str
    timestamps: list[Timestamp] = Field(min_length=1)


class SummaryResponse(BaseModel):
    material_id: int | None = None
    synopsis: str = Field(max_length=1400)
    glossary: list[GlossaryItem]
    didactic_blocks: list[DidacticBlock]
    evidence_sufficient: bool
    insufficiency_note: str | None = None


class BloomLevel(StrEnum):
    """Niveles cognitivos configurables de la taxonomía de Bloom."""

    REMEMBER = "remember"
    UNDERSTAND = "understand"
    APPLY = "apply"
    ANALYZE = "analyze"
    EVALUATE = "evaluate"
    CREATE = "create"


class QuizRequest(BaseModel):
    """Solicitud de RF-03 con cantidad limitada para la capa gratuita."""

    video_id: int
    multiple_choice_count: int = Field(default=5, ge=1, le=10)
    open_question_count: int = Field(default=3, ge=1, le=8)
    bloom_levels: list[BloomLevel] = Field(
        default_factory=lambda: [BloomLevel.REMEMBER, BloomLevel.UNDERSTAND, BloomLevel.APPLY],
        min_length=1,
    )


class MultipleChoiceQuestion(BaseModel):
    """Pregunta cerrada y su evidencia temporal dentro del video."""

    question: str
    options: list[str] = Field(min_length=4, max_length=4)
    correct_option: int = Field(ge=0, le=3)
    explanation: str
    evidence_timestamp: Timestamp
    bloom_level: BloomLevel


class OpenQuestion(BaseModel):
    """Pregunta de desarrollo con los puntos que deben aparecer en la respuesta."""

    question: str
    expected_points: list[str] = Field(min_length=1)
    evidence_timestamp: Timestamp
    bloom_level: BloomLevel


class QuizResponse(BaseModel):
    material_id: int | None = None
    multiple_choice: list[MultipleChoiceQuestion]
    open_questions: list[OpenQuestion]
    evidence_sufficient: bool
    insufficiency_note: str | None = None


class MaterialResponse(BaseModel):
    """Recurso persistido, con un contenido que conserva su estructura validada."""

    id: int
    video_id: int
    material_type: Literal["summary", "quiz"]
    content: dict[str, Any]


class MaterialUpdateRequest(BaseModel):
    """Contenido completo editado por el usuario para un recurso existente."""

    content: dict[str, Any]


class MultipleChoiceAnswer(BaseModel):
    """Respuesta del estudiante a una pregunta cerrada, identificada por su posición."""

    question_index: int = Field(ge=0)
    selected_option: int = Field(ge=0, le=3)


class OpenAnswer(BaseModel):
    """Respuesta libre del estudiante con un límite seguro para la capa gratuita."""

    question_index: int = Field(ge=0)
    answer: str = Field(min_length=1, max_length=3000)


class FeedbackRequest(BaseModel):
    """Intento parcial o completo enviado para recibir retroalimentación de HU-09."""

    multiple_choice_answers: list[MultipleChoiceAnswer] = Field(default_factory=list)
    open_answers: list[OpenAnswer] = Field(default_factory=list)


class MultipleChoiceFeedback(BaseModel):
    question_index: int
    is_correct: bool
    explanation: str
    evidence_timestamp: Timestamp


class OpenAnswerFeedback(BaseModel):
    question_index: int
    feedback: str
    achieved_points: list[str]
    missing_points: list[str]
    evidence_timestamp: Timestamp


class OpenFeedbackBatch(BaseModel):
    """Contrato JSON que Gemini debe devolver para las respuestas abiertas."""

    feedback: list[OpenAnswerFeedback]
    evidence_sufficient: bool
    insufficiency_note: str | None = None


class FeedbackResponse(BaseModel):
    material_id: int
    multiple_choice: list[MultipleChoiceFeedback]
    open_questions: list[OpenAnswerFeedback]
    evidence_sufficient: bool
    insufficiency_note: str | None = None


ExportFormat = Literal["json", "markdown"]
