"""Rutas públicas para registro e inicio de sesión."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.errors import PipelineError
from app.db.database import get_session
from app.models.user import User
from app.schemas.contracts import TokenResponse, UserCreate, UserLogin
from app.services.auth_service import AuthService, get_current_user

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def raise_http(error: PipelineError) -> None:
    """Translate known domain errors to the API envelope used by other routes."""
    raise HTTPException(status_code=error.status_code, detail={"code": error.code, "message": str(error)})


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(payload: UserCreate, session: Session = Depends(get_session)) -> dict[str, int | str]:
    """Create a user identity without assigning any global role."""
    try:
        user = AuthService().register(payload, session)
        return {"id": user.id, "nombre": user.nombre, "email": user.email}
    except PipelineError as error:
        raise_http(error)


@router.post("/login", response_model=TokenResponse)
def login(payload: UserLogin, session: Session = Depends(get_session)) -> TokenResponse:
    """Return a signed Bearer JWT when the supplied credentials are valid."""
    try:
        return AuthService().login(payload, session)
    except PipelineError as error:
        raise_http(error)


@router.get("/me")
def get_me(current_user: User = Depends(get_current_user)) -> dict[str, int | str]:
    """Retorna la identidad del usuario actualmente autenticado."""
    return {"id": current_user.id, "nombre": current_user.nombre, "email": current_user.email}
