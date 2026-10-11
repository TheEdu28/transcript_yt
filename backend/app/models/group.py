"""Modelos de datos para grupos, membresías, temas y actividades."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class Group(Base):
    """Grupo o aula administrada por un usuario (admin_id)."""

    __tablename__ = "groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    admin_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(6), unique=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    memberships: Mapped[list["GroupMembership"]] = relationship(
        "GroupMembership", back_populates="group", cascade="all, delete-orphan"
    )
    topics: Mapped[list["Topic"]] = relationship(
        "Topic", back_populates="group", cascade="all, delete-orphan"
    )


class GroupMembership(Base):
    """Membresía que asocia a un usuario con un grupo."""

    __tablename__ = "group_memberships"
    __table_args__ = (UniqueConstraint("group_id", "user_id", name="uq_group_membership_user"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_id: Mapped[int] = mapped_column(Integer, ForeignKey("groups.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    group: Mapped["Group"] = relationship("Group", back_populates="memberships")


# Compatibilidad hacia atrás
GroupMember = GroupMembership


class Topic(Base):
    """Tema o actividad evaluativa vinculada a un material de tipo quiz."""

    __tablename__ = "topics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_id: Mapped[int] = mapped_column(Integer, ForeignKey("groups.id"), nullable=False, index=True)
    video_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("videos.id"), nullable=True, index=True)
    material_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("didactic_materials.id"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    is_published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    group: Mapped["Group"] = relationship("Group", back_populates="topics")
    attempts: Mapped[list["Attempt"]] = relationship(
        "Attempt", back_populates="topic", cascade="all, delete-orphan"
    )


class Attempt(Base):
    """Registro de intento de un miembro al resolver un tema/cuestionario."""

    __tablename__ = "attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    topic_id: Mapped[int] = mapped_column(Integer, ForeignKey("topics.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_score: Mapped[float] = mapped_column(Float, nullable=False)
    final_score: Mapped[float] = mapped_column(Float, nullable=False)
    answers_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    submitted_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    topic: Mapped["Topic"] = relationship("Topic", back_populates="attempts")
