"""Contrato para parámetros didácticos."""

from pydantic import BaseModel, Field


class DidacticSettingsUpdate(BaseModel):
    """Editable pedagogical preferences for RF-06."""

    audience_level: str = "undergraduate"
    preferred_language: str = "es"
    default_question_count: int = Field(default=10, ge=1, le=30)

