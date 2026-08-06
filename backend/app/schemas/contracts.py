"""Contratos de API y formatos estrictos que Gemini debe producir."""

from typing import Annotated

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
    synopsis: str = Field(max_length=1400)
    glossary: list[GlossaryItem]
    didactic_blocks: list[DidacticBlock]
    evidence_sufficient: bool
    insufficiency_note: str | None = None


class QuizRequest(BaseModel):
    """Solicitud de RF-03 con cantidad limitada para la capa gratuita."""

    video_id: int
    multiple_choice_count: int = Field(default=5, ge=1, le=10)
    open_question_count: int = Field(default=3, ge=1, le=8)


class MultipleChoiceQuestion(BaseModel):
    question: str
    options: list[str] = Field(min_length=4, max_length=4)
    correct_option: int = Field(ge=0, le=3)
    explanation: str
    evidence_timestamp: str


class OpenQuestion(BaseModel):
    question: str
    expected_points: list[str]
    evidence_timestamp: str


class QuizResponse(BaseModel):
    multiple_choice: list[MultipleChoiceQuestion]
    open_questions: list[OpenQuestion]
    evidence_sufficient: bool
    insufficiency_note: str | None = None
