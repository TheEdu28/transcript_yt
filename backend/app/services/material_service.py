"""Casos de uso para consultar y editar recursos didácticos ya generados."""

import json
from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import PipelineError
from app.repositories.material_repository import MaterialRepository
from app.schemas.contracts import MaterialResponse, QuizResponse, SummaryResponse


class MaterialService:
    """Valida el contenido antes de persistir cualquier edición del estudiante."""

    def __init__(self, repository: MaterialRepository | None = None) -> None:
        self.repository = repository or MaterialRepository()

    def save_generated(self, session: Session, video_id: int, material_type: str, content: SummaryResponse | QuizResponse) -> SummaryResponse | QuizResponse:
        """Persist a provider-validated response and attach its generated identifier."""
        material = self.repository.create(
            session, video_id, material_type,
            json.dumps(content.model_dump(mode="json", exclude={"material_id"}), ensure_ascii=False),
        )
        return content.model_copy(update={"material_id": material.id})

    def get(self, session: Session, material_id: int) -> MaterialResponse:
        """Load a material and return its stored content with a canonical material identifier."""
        material = self.repository.get(session, material_id)
        if not material:
            raise PipelineError("El material no existe.", code="MATERIAL_NOT_FOUND", status_code=404)
        return self._as_response(material.id, material.video_id, material.material_type, material.content_json)

    def update(self, session: Session, material_id: int, content: dict[str, Any]) -> MaterialResponse:
        """Validate and persist a complete user edit without contacting Gemini again."""
        material = self.repository.get(session, material_id)
        if not material:
            raise PipelineError("El material no existe.", code="MATERIAL_NOT_FOUND", status_code=404)
        validated = self._validate_content(material.material_type, content)
        self.repository.update_content(
            session, material,
            json.dumps(validated.model_dump(mode="json", exclude={"material_id"}), ensure_ascii=False),
        )
        return MaterialResponse(
            id=material.id, video_id=material.video_id, material_type=material.material_type,
            content=validated.model_dump(mode="json", exclude={"material_id"}),
        )

    def _as_response(self, material_id: int, video_id: int, material_type: str, content_json: str) -> MaterialResponse:
        """Deserialize persisted JSON through its original Pydantic contract."""
        try:
            content = json.loads(content_json)
        except json.JSONDecodeError as error:
            raise PipelineError("El material almacenado es inválido.", code="INVALID_STORED_MATERIAL", status_code=500) from error
        validated = self._validate_content(material_type, content)
        return MaterialResponse(
            id=material_id, video_id=video_id, material_type=material_type,
            content=validated.model_dump(mode="json", exclude={"material_id"}),
        )

    @staticmethod
    def _validate_content(material_type: str, content: dict[str, Any]) -> SummaryResponse | QuizResponse:
        """Reuse generation contracts so edited materials cannot lose their schema."""
        if material_type == "summary":
            return SummaryResponse.model_validate(content)
        if material_type == "quiz":
            # Los cuestionarios de Sprint 3 no tenían Bloom; al leerlos se les asigna
            # el nivel intermedio para conservar compatibilidad, mientras las salidas nuevas lo exigen.
            normalized = dict(content)
            for key in ("multiple_choice", "open_questions"):
                normalized[key] = [{**item, "bloom_level": item.get("bloom_level", "understand")} for item in content.get(key, [])]
            return QuizResponse.model_validate(normalized)
        raise PipelineError("El tipo de material almacenado no es compatible.", code="INVALID_MATERIAL_TYPE", status_code=500)
