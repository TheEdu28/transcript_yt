"""Contratos para generación de recursos didácticos."""

from enum import StrEnum

from pydantic import BaseModel, Field


class BloomLevel(StrEnum):
    """Cognitive levels accepted for questionnaire generation."""

    REMEMBER = "remember"
    UNDERSTAND = "understand"
    APPLY = "apply"
    ANALYZE = "analyze"
    EVALUATE = "evaluate"
    CREATE = "create"


class MaterialGenerationRequest(BaseModel):
    """Parameters for synopsis, glossary and didactic blocks."""

    video_id: int
    target_level: str = "undergraduate"
    retrieval_chunk_count: int = Field(default=8, ge=1, le=20)


class QuizGenerationRequest(BaseModel):
    """Parameters for a Bloom-aligned quiz."""

    video_id: int
    question_count: int = Field(default=10, ge=1, le=30)
    bloom_levels: list[BloomLevel] = Field(default_factory=lambda: list(BloomLevel))

