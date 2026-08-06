"""Endpoints RF-02 y RF-03: recursos didácticos generados."""

from fastapi import APIRouter, status

from app.schemas.material import MaterialGenerationRequest, QuizGenerationRequest

router = APIRouter()


@router.post("/generate", status_code=status.HTTP_501_NOT_IMPLEMENTED)
def generate_material(payload: MaterialGenerationRequest) -> None:
    """Generate synopsis, glossary and didactic blocks (RF-02)."""
    raise NotImplementedError


@router.post("/quiz", status_code=status.HTTP_501_NOT_IMPLEMENTED)
def generate_quiz(payload: QuizGenerationRequest) -> None:
    """Generate a Bloom-aligned quiz (RF-03)."""
    raise NotImplementedError

