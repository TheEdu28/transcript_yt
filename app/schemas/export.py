"""Contrato para exportación de resultados."""

from enum import StrEnum

from pydantic import BaseModel


class ExportFormat(StrEnum):
    """Initial export formats reserved for RF-04."""

    JSON = "json"
    MARKDOWN = "markdown"
    PDF = "pdf"


class ExportRequest(BaseModel):
    """Resource and target format selected for export."""

    material_id: int
    format: ExportFormat = ExportFormat.MARKDOWN

