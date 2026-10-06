"""Contratos de API y formatos estrictos que Gemini debe producir."""

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import AnyHttpUrl, BaseModel, Field

Timestamp = Annotated[str, Field(pattern=r"^\d{2}:\d{2}:\d{2}$")]

# Proveedores de LLM soportados por el sistema.
ModelProviderName = Literal["gemini", "openai", "groq"]


class ModelInfo(BaseModel):
    """Un modelo concreto dentro de un proveedor, con su estado de cuota."""

    model_id: str        # Identificador único: "gemini/gemini-2.0-flash-lite"
    provider: ModelProviderName
    label: str           # Nombre legible para la UI.
    available: bool      # False si la API key no está configurada.
    quota_exhausted: bool = False  # True si el último intento devolvió 429.
    is_default: bool = False


class ModelsResponse(BaseModel):
    """Listado de modelos disponibles y cuál es el activo por defecto."""

    models: list[ModelInfo]
    default_model_id: str


# Mantener ProviderInfo y el ModelsResponse antiguo para no romper tests existentes.
class ProviderInfo(BaseModel):
    name: ModelProviderName
    label: str
    available: bool
    model: str



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
    model_provider: ModelProviderName | None = Field(
        default=None,
        description="Proveedor de LLM a usar en esta petición. Si no se indica, se usa el activo en la configuración.",
    )
    model_id: str | None = Field(
        default=None,
        description="ID concreto del modelo (ej: 'gemini/gemini-2.0-flash'). Sobreescribe model_provider.",
    )


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
    model_provider: ModelProviderName | None = Field(
        default=None,
        description="Proveedor de LLM a usar en esta petición. Si no se indica, se usa el activo en la configuración.",
    )
    model_id: str | None = Field(
        default=None,
        description="ID concreto del modelo (ej: 'gemini/gemini-2.0-flash'). Sobreescribe model_provider.",
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
    last_edited_by: int | None = None
    last_edited_by_name: str | None = None
    last_edited_at: str | None = None


class MaterialUpdateRequest(BaseModel):
    """Contenido completo editado por el usuario para un recurso existente."""

    content: dict[str, Any]


class MaterialVersionItem(BaseModel):
    id: int
    edited_by: int | None
    edited_by_name: str | None = None
    edited_at: str


class MaterialVersionsResponse(BaseModel):
    material_id: int
    versions: list[MaterialVersionItem]


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


ExportFormat = Literal["json", "markdown", "pdf", "docx"]


class VideoHistoryItem(BaseModel):
    """Entrada del historial de videos del usuario autenticado."""

    id: int
    youtube_id: str
    title: str
    language: str
    duration_seconds: int
    status: str
    created_at: str | None
    has_summary: bool
    has_quiz: bool
    published_in_groups: list[int]


class VideoHistoryResponse(BaseModel):
    items: list[VideoHistoryItem]
    total: int
    page: int
    page_size: int


class UserCreate(BaseModel):
    """Datos mínimos para registrar una identidad autenticable."""

    nombre: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=5, max_length=320)
    password: str = Field(min_length=8, max_length=128)


class UserLogin(BaseModel):
    """Credenciales JSON enviadas para obtener un token de acceso."""

    email: str = Field(min_length=5, max_length=320)
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    """Bearer token emitido después de autenticar credenciales válidas."""

    access_token: str
    token_type: Literal["bearer"] = "bearer"


class GroupCreate(BaseModel):
    """Datos para crear un nuevo grupo de estudio."""

    name: str = Field(min_length=2, max_length=150)


class GroupUpdate(BaseModel):
    """Datos para modificar las propiedades del grupo."""

    name: str = Field(min_length=2, max_length=150)


class GroupResponse(BaseModel):
    """Representación pública del grupo con su admin_id."""

    id: int
    name: str
    admin_id: int
    created_at: datetime


class GroupMemberAdd(BaseModel):
    """Identificador del usuario a incorporar al grupo."""

    user_id: int


class GroupMemberResponse(BaseModel):
    """Detalle de membresía en un grupo."""

    id: int
    group_id: int
    user_id: int
    joined_at: datetime


class TopicCreate(BaseModel):
    """Datos para registrar un nuevo tema o actividad en el grupo."""

    title: str = Field(min_length=2, max_length=200)
    description: str = Field(default="", max_length=5000)
    is_published: bool = True
    video_id: int | None = None


class TopicUpdate(BaseModel):
    """Datos para modificar un tema o actividad."""

    title: str | None = Field(default=None, min_length=2, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    is_published: bool | None = None
    video_id: int | None = None


class TopicResponse(BaseModel):
    """Respuesta con la información del tema."""

    id: int
    group_id: int
    title: str
    description: str
    is_published: bool
    video_id: int | None = None
    created_at: datetime


class AttemptCreate(BaseModel):
    """Envío de resultado o intento de un alumno."""

    score: int | None = Field(default=None, ge=0, le=100)
    details: str = Field(default="", max_length=2000)


class AttemptResponse(BaseModel):
    """Detalle del intento realizado."""

    id: int
    topic_id: int
    user_id: int
    score: int | None
    details: str
    created_at: datetime
