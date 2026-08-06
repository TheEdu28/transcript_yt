"""Endpoints RF-06: parámetros didácticos."""

from fastapi import APIRouter, status

from app.schemas.settings import DidacticSettingsUpdate

router = APIRouter()


@router.put("/didactic", status_code=status.HTTP_501_NOT_IMPLEMENTED)
def update_didactic_settings(payload: DidacticSettingsUpdate) -> None:
    """Persist didactic generation preferences (RF-06)."""
    raise NotImplementedError

