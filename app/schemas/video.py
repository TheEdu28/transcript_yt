"""Contratos para búsqueda e ingesta de videos."""

from pydantic import BaseModel, Field, HttpUrl


class VideoSearchRequest(BaseModel):
    """Search criteria for RF-05."""

    keywords: str = Field(min_length=2)
    max_results: int = Field(default=10, ge=1, le=50)


class VideoIngestRequest(BaseModel):
    """Input required to start RF-01."""

    url: HttpUrl
    language: str = "es"

