"""Registro, autenticación JWT y resolución del usuario actual."""

from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import PipelineError
from app.db.database import get_session
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.contracts import TokenResponse, UserCreate, UserLogin

password_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


class AuthService:
    """Casos de uso de registro e inicio de sesión."""

    def __init__(self, repository: UserRepository | None = None) -> None:
        self.repository = repository or UserRepository()
        self.settings = get_settings()

    def register(self, payload: UserCreate, session: Session) -> User:
        email = payload.email.strip().lower()
        if self.repository.get_by_email(session, email):
            raise PipelineError(
                "El correo ya está registrado.", code="EMAIL_ALREADY_REGISTERED", status_code=status.HTTP_409_CONFLICT,
            )

        try:
            user = self.repository.create(
                session,
                nombre=payload.nombre.strip(),
                email=email,
                password_hash=password_context.hash(payload.password),
            )
            session.commit()
            session.refresh(user)
            return user
        except IntegrityError as error:
            session.rollback()
            raise PipelineError(
                "El correo ya está registrado.", code="EMAIL_ALREADY_REGISTERED", status_code=status.HTTP_409_CONFLICT,
            ) from error

    def login(self, payload: UserLogin, session: Session) -> TokenResponse:
        user = self.repository.get_by_email(session, payload.email.strip().lower())
        password_matches = user is not None and password_context.verify(payload.password, user.password_hash)
        if not password_matches:
            raise PipelineError(
                "Correo o contraseña inválidos.", code="INVALID_CREDENTIALS", status_code=status.HTTP_401_UNAUTHORIZED,
            )

        if not self.settings.jwt_secret_key:
            raise PipelineError(
                "Falta JWT_SECRET_KEY en el entorno.", code="JWT_SECRET_KEY_MISSING", status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        expires_at = datetime.now(timezone.utc) + timedelta(minutes=self.settings.jwt_access_token_expire_minutes)
        access_token = jwt.encode(
            {"sub": str(user.id), "exp": expires_at},
            self.settings.jwt_secret_key,
            algorithm=self.settings.jwt_algorithm,
        )
        return TokenResponse(access_token=access_token)


def get_current_user(
    token: str = Depends(oauth2_scheme), session: Session = Depends(get_session),
) -> User:
    """Validate a Bearer JWT and load the current user from SQLite."""
    settings = get_settings()
    if not settings.jwt_secret_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "JWT_SECRET_KEY_MISSING", "message": "Falta JWT_SECRET_KEY en el entorno."},
        )

    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": "INVALID_TOKEN", "message": "El token de acceso no es válido o expiró."},
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        subject = payload.get("sub")
        if not subject:
            raise credentials_error
        user_id = int(subject)
    except (JWTError, ValueError):
        raise credentials_error

    user = UserRepository().get(session, user_id)
    if not user:
        raise credentials_error
    return user
