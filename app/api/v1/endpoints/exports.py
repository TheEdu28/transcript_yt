"""Endpoints RF-04: consulta y exportación."""

from fastapi import APIRouter, status

from app.schemas.export import ExportRequest

router = APIRouter()


@router.post("/", status_code=status.HTTP_501_NOT_IMPLEMENTED)
def export_material(payload: ExportRequest) -> None:
    """Export a generated didactic resource (RF-04)."""
    raise NotImplementedError

