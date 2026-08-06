"""Endpoint de disponibilidad del servicio."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health_check() -> dict[str, str]:
    """Report the minimal liveness state of the API."""
    return {"status": "ok"}

