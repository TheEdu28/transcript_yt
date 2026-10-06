"""Persistencia de usuarios autenticables."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User


class UserRepository:
    """Encapsula consultas de identidad en SQLite."""

    def get(self, session: Session, user_id: int) -> User | None:
        return session.get(User, user_id)

    def get_by_email(self, session: Session, email: str) -> User | None:
        return session.scalar(select(User).where(User.email == email))

    def create(self, session: Session, *, nombre: str, email: str, password_hash: str) -> User:
        user = User(nombre=nombre, email=email, password_hash=password_hash)
        session.add(user)
        session.flush()
        return user
