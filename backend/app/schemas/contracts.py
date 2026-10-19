"""Contratos de API y formatos estrictos que Gemini debe producir."""

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, model_validator

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


class VideoDetailResponse(BaseModel):
    """Detalle de un video registrado incluyendo su youtube_id."""

    id: int
    youtube_id: str
    source_url: str
    title: str
    language: str
    duration_seconds: int
    status: str



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
    synopsis: str = Field(max_length=4000)
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
    answer: str = Field(default="", max_length=3000)


class FeedbackRequest(BaseModel):
    """Intento parcial o completo enviado para recibir retroalimentación de HU-09."""

    multiple_choice_answers: list[MultipleChoiceAnswer] = Field(default_factory=list)
    open_answers: list[OpenAnswer] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def populate_answers(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "answers" in data and "multiple_choice_answers" not in data:
                data["multiple_choice_answers"] = data["answers"]
        return data


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
    """Contrato JSON que Gemini debe devolver para las respuestas abiertas de HU-09."""

    feedback: list[OpenAnswerFeedback]
    evidence_sufficient: bool
    insufficiency_note: str | None = None


class OpenQuestionEvaluation(BaseModel):
    """Evaluación individual de una pregunta abierta con calificación normalizada y groundedness."""

    question_index: int = Field(..., ge=0, description="Índice de la pregunta abierta en el cuestionario.")
    score: float = Field(..., ge=0.0, le=1.0, description="Calificación continua entre 0.0 y 1.0 basada en la evidencia.")
    is_correct: bool = Field(..., description="True si la respuesta alcanza suficiencia pedagógica (score >= 0.7).")
    feedback_text: str = Field(..., description="Explicación pedagógica breve fundamentada exclusivamente en la evidencia.")
    missing_points: list[str] = Field(description="Ideas clave que faltaron según la evidencia.")


class OpenQuestionsEvaluationBatch(BaseModel):
    """Contrato JSON que Gemini debe devolver para la evaluación estructurada de preguntas abiertas."""

    evaluations: list[OpenQuestionEvaluation]
    evidence_sufficient: bool = Field(description="False si la evidencia no basta para evaluar.")
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


class GroupJoinRequest(BaseModel):
    """Código de 6 caracteres alfanuméricos para unirse a un grupo."""

    code: str = Field(min_length=6, max_length=6, pattern=r"^[A-Za-z0-9]{6}$")


class GroupUpdate(BaseModel):
    """Datos para modificar las propiedades del grupo."""

    name: str = Field(min_length=2, max_length=150)


class GroupResponse(BaseModel):
    """Representación pública del grupo con su admin_id y código."""

    id: int
    name: str
    admin_id: int
    code: str
    created_at: datetime


class MyGroupsResponse(BaseModel):
    """Listas separadas de grupos administrados y grupos en los que es miembro."""

    admin_groups: list[GroupResponse]
    member_groups: list[GroupResponse]


class GroupMemberAdd(BaseModel):
    """Identificador del usuario a incorporar al grupo."""

    user_id: int


class GroupMemberResponse(BaseModel):
    """Detalle de membresía en un grupo."""

    id: int
    group_id: int
    user_id: int
    joined_at: datetime


class GroupMemberDetail(BaseModel):
    """Información legible del miembro para la interfaz del grupo."""

    id: int
    user_id: int
    nombre: str
    email: str
    is_admin: bool
    joined_at: datetime


class TopicCreate(BaseModel):
    """Datos para registrar un nuevo tema o actividad en el grupo."""

    title: str = Field(min_length=2, max_length=200)
    video_id: int | None = None
    material_id: int | None = None
    description: str | None = None
    is_active: bool = True


class TopicUpdate(BaseModel):
    """Datos para modificar un tema o actividad."""

    title: str | None = Field(default=None, min_length=2, max_length=200)
    description: str | None = None
    video_id: int | None = None
    material_id: int | None = None
    is_active: bool | None = None


class TopicResponse(BaseModel):
    """Respuesta con la información del tema."""

    id: int
    group_id: int
    video_id: int | None = None
    material_id: int | None = None
    quiz_id: int | None = None
    summary_id: int | None = None
    title: str
    description: str = ""
    created_by: int | None = None
    is_active: bool = True
    created_at: datetime


class TopicMaterialsResponse(BaseModel):
    """Materiales compartidos del tema y materiales personales del estudiante."""

    topic_id: int
    video_id: int | None = None
    title: str | None = None
    is_admin: bool = False
    shared_quiz: MaterialResponse | None = None
    shared_summary: MaterialResponse | None = None
    personal_quiz: MaterialResponse | None = None
    personal_summary: MaterialResponse | None = None
    personal_quizzes: list[MaterialResponse] = Field(default_factory=list)


class AttemptGradeUpdate(BaseModel):
    """Actualización o revisión manual de la calificación de un intento."""

    final_score: float = Field(ge=0.0, le=100.0)
    review_notes: str | None = None


class AttemptSubmitRequest(BaseModel):
    """Envío de respuestas de un cuestionario por parte de un miembro."""

    multiple_choice_answers: list[MultipleChoiceAnswer] = Field(default_factory=list)
    open_answers: list[OpenAnswer] = Field(default_factory=list)
    material_id: int | None = None

    @model_validator(mode="before")
    @classmethod
    def populate_answers(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "answers" in data and "multiple_choice_answers" not in data:
                data["multiple_choice_answers"] = data["answers"]
        return data


class AttemptResponse(BaseModel):
    """Detalle de un intento realizado por un miembro."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    topic_id: int
    user_id: int
    attempt_number: int
    raw_score: float
    final_score: float
    submitted_at: datetime


class AdminAttemptResponse(AttemptResponse):
    """Detalle del intento para el administrador incluyendo las respuestas dadas."""

    answers_json: str


class MemberTopicSummary(BaseModel):
    """Resumen de desempeño de un miembro en una actividad."""

    user_id: int
    user_name: str
    user_email: str
    total_attempts: int
    best_attempt: AttemptResponse | None
    latest_attempt: AttemptResponse | None
    average_final_score: float | None
    average_raw_score: float | None


class TopicSummaryResponse(BaseModel):
    """Resumen consolidado de todos los miembros del grupo para un tema."""

    topic_id: int
    group_id: int
    title: str
    members_summary: list[MemberTopicSummary]


class MemberTopicGrade(BaseModel):
    """Estado y calificación de un miembro en un tema concreto."""

    topic_id: int
    topic_title: str
    status: Literal["evaluated", "pending"]
    total_attempts: int = 0
    attempts_count: int = 0
    best_final_score: float | None = None
    best_raw_score: float | None = None
    latest_final_score: float | None = None
    latest_attempt_id: int | None = None
    latest_submitted_at: datetime | None = None
    review_notes: str | None = None


class MemberGradeSummary(BaseModel):
    """Resumen académico de un miembro en el grupo."""

    user_id: int
    user_name: str
    user_email: str
    nombre: str | None = None
    email: str | None = None
    completed_topics: int
    total_topics: int
    average_score: float | None = None
    topics: list[MemberTopicGrade] = Field(default_factory=list)
    topic_grades: dict[str | int, Any] = Field(default_factory=dict)


class GroupGradesResponse(BaseModel):
    """Libro de calificaciones consolidado del grupo."""

    group_id: int
    group_name: str
    is_admin: bool
    total_topics: int
    topics: list[TopicResponse] = Field(default_factory=list)
    members: list[MemberGradeSummary]



