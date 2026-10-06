"""Casos de uso para consultar y editar recursos didácticos ya generados."""

import json
from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.errors import PipelineError
from app.repositories.material_repository import MaterialRepository
from app.schemas.contracts import MaterialResponse, QuizResponse, SummaryResponse


class MaterialService:
    """Valida el contenido antes de persistir cualquier edición del estudiante."""

    def __init__(self, repository: MaterialRepository | None = None) -> None:
        self.repository = repository or MaterialRepository()

    def save_generated(self, session: Session, video_id: int, material_type: str, content: SummaryResponse | QuizResponse, owner_id: int | None = None) -> SummaryResponse | QuizResponse:
        """Persist a provider-validated response and attach its generated identifier."""
        serialized = json.dumps(content.model_dump(mode="json", exclude={"material_id"}), ensure_ascii=False)
        if owner_id is None:
            material = self.repository.create(session, video_id, material_type, serialized)
        else:
            material = self.repository.create(session, video_id, material_type, serialized, owner_id=owner_id)
        return content.model_copy(update={"material_id": material.id})

    def get(self, session: Session, material_id: int) -> MaterialResponse:
        """Load a material and return its stored content with a canonical material identifier."""
        material = self.repository.get(session, material_id)
        if not material:
            raise PipelineError("El material no existe.", code="MATERIAL_NOT_FOUND", status_code=404)
        return self._as_response(session, material.id, material.video_id, material.material_type, material.content_json)

    def update(self, session: Session, material_id: int, content: dict[str, Any], edited_by: int | None = None) -> MaterialResponse:
        """Validate and persist a complete user edit, saving a version snapshot."""
        material = self.repository.get(session, material_id)
        if not material:
            raise PipelineError("El material no existe.", code="MATERIAL_NOT_FOUND", status_code=404)
        validated = self._validate_content(material.material_type, content)
        serialized = json.dumps(validated.model_dump(mode="json", exclude={"material_id"}), ensure_ascii=False)
        if edited_by is None:
            self.repository.update_content(session, material, serialized)
        else:
            self.repository.update_content(session, material, serialized, edited_by=edited_by)
        return MaterialResponse(
            id=material.id, video_id=material.video_id, material_type=material.material_type,
            content=validated.model_dump(mode="json", exclude={"material_id"}),
            **self._last_editor_fields(session, material.id),
        )

    def list_versions(self, session: Session, material_id: int) -> list[dict]:
        """Return version history metadata (no content) for display in the UI."""
        material = self.repository.get(session, material_id)
        if not material:
            raise PipelineError("El material no existe.", code="MATERIAL_NOT_FOUND", status_code=404)
        return [
            {
                "id": v.id,
                "edited_by": v.edited_by,
                "edited_by_name": self.repository.user_name(session, v.edited_by),
                "edited_at": v.edited_at.isoformat(),
            }
            for v in self.repository.list_versions(session, material_id)
        ]

    def restore(self, session: Session, material_id: int, version_id: int, edited_by: int) -> MaterialResponse:
        """Restore a previous snapshot while preserving the current state in history."""
        material = self.repository.get(session, material_id)
        if not material:
            raise PipelineError("El material no existe.", code="MATERIAL_NOT_FOUND", status_code=404)
        version = self.repository.get_version(session, material_id, version_id)
        if not version:
            raise PipelineError("La versión no existe para este material.", code="VERSION_NOT_FOUND", status_code=404)
        try:
            content = json.loads(version.content_json)
        except json.JSONDecodeError as error:
            raise PipelineError("La versión almacenada es inválida.", code="INVALID_STORED_VERSION", status_code=500) from error
        validated = self._validate_content(material.material_type, content, allow_legacy_quiz=True)
        serialized = json.dumps(validated.model_dump(mode="json", exclude={"material_id"}), ensure_ascii=False)
        self.repository.update_content(session, material, serialized, edited_by=edited_by)
        return MaterialResponse(
            id=material.id, video_id=material.video_id, material_type=material.material_type,
            content=validated.model_dump(mode="json", exclude={"material_id"}),
            **self._last_editor_fields(session, material.id),
        )

    def can_edit(self, session: Session, material_id: int, user_id: int) -> bool:
        """Return whether a user owns the source video or administers its published group topic."""
        material = self.repository.get(session, material_id)
        return material is not None and self.repository.is_video_owner_or_published_group_admin(session, material, user_id)

    def _as_response(self, session: Session, material_id: int, video_id: int, material_type: str, content_json: str) -> MaterialResponse:
        """Deserialize persisted JSON through its original Pydantic contract."""
        try:
            content = json.loads(content_json)
        except json.JSONDecodeError as error:
            raise PipelineError("El material almacenado es inválido.", code="INVALID_STORED_MATERIAL", status_code=500) from error
        validated = self._validate_content(material_type, content, allow_legacy_quiz=True)
        return MaterialResponse(
            id=material_id, video_id=video_id, material_type=material_type,
            content=validated.model_dump(mode="json", exclude={"material_id"}),
            **self._last_editor_fields(session, material_id),
        )

    def _last_editor_fields(self, session: Session, material_id: int) -> dict[str, Any]:
        """Build optional metadata for the latest version, including generated materials."""
        latest_version = getattr(self.repository, "latest_version", None)
        if latest_version is None:
            return {"last_edited_by": None, "last_edited_by_name": None, "last_edited_at": None}
        latest = latest_version(session, material_id)
        if not latest:
            return {"last_edited_by": None, "last_edited_by_name": None, "last_edited_at": None}
        user_name = getattr(self.repository, "user_name", None)
        return {
            "last_edited_by": latest.edited_by,
            "last_edited_by_name": user_name(session, latest.edited_by) if user_name else None,
            "last_edited_at": latest.edited_at.isoformat(),
        }

    @staticmethod
    def _validate_content(
        material_type: str, content: dict[str, Any], allow_legacy_quiz: bool = False
    ) -> SummaryResponse | QuizResponse:
        """Reuse generation contracts so edited materials cannot lose their schema."""
        try:
            if material_type == "summary":
                return SummaryResponse.model_validate(content)
            if material_type == "quiz":
                normalized = dict(content)
                if allow_legacy_quiz:
                    for key in ("multiple_choice", "open_questions"):
                        normalized[key] = [
                            {**item, "bloom_level": item.get("bloom_level", "understand")}
                            for item in content.get(key, [])
                        ]
                return QuizResponse.model_validate(normalized)
        except ValidationError as error:
            raise PipelineError(
                "El contenido no cumple el esquema del material.",
                code="INVALID_MATERIAL_CONTENT",
                status_code=422,
            ) from error
        raise PipelineError("El tipo de material almacenado no es compatible.", code="INVALID_MATERIAL_TYPE", status_code=500)
