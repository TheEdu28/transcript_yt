"""Pruebas unitarias de consulta y edición de materiales persistidos (HU-06)."""

import json
from types import SimpleNamespace

import pytest

from app.core.errors import PipelineError
from app.services.material_service import MaterialService
from app.schemas.contracts import SummaryResponse


def summary() -> SummaryResponse:
    """Return a small valid summary used as persisted material content."""
    return SummaryResponse(
        synopsis="La fotosíntesis transforma energía luminosa.", glossary=[], didactic_blocks=[],
        evidence_sufficient=True,
    )


class FakeMaterialRepository:
    """In-memory repository that records service interactions without SQLite."""

    def __init__(self, material: object | None = None) -> None:
        self.material = material
        self.created_content = ""

    def create(self, _session: object, video_id: int, material_type: str, content_json: str) -> object:
        self.created_content = content_json
        self.material = SimpleNamespace(id=7, video_id=video_id, material_type=material_type, content_json=content_json)
        return self.material

    def get(self, _session: object, _material_id: int) -> object | None:
        return self.material

    def update_content(self, _session: object, material: object, content_json: str) -> object:
        material.content_json = content_json
        return material


def test_save_generated_persists_validated_content_without_provider_identifier() -> None:
    """HU-06 gives generated material a local identifier and avoids storing a spoofable one."""
    repository = FakeMaterialRepository()
    result = MaterialService(repository).save_generated(object(), 3, "summary", summary())
    assert result.material_id == 7
    assert "material_id" not in json.loads(repository.created_content)


def test_get_rejects_missing_material() -> None:
    """HU-06 returns a stable not-found error for an unknown resource."""
    with pytest.raises(PipelineError) as error:
        MaterialService(FakeMaterialRepository()).get(object(), 99)
    assert error.value.code == "MATERIAL_NOT_FOUND"


def test_get_deserializes_stored_content_using_its_original_contract() -> None:
    """HU-06 preserves an editable material's schema after it is loaded again."""
    stored = SimpleNamespace(id=7, video_id=3, material_type="summary", content_json=summary().model_dump_json())
    result = MaterialService(FakeMaterialRepository(stored)).get(object(), 7)
    assert result.content["synopsis"] == "La fotosíntesis transforma energía luminosa."


def test_update_revalidates_content_and_ignores_client_material_id() -> None:
    """HU-06 retains the database identity while allowing a valid content edit."""
    stored = SimpleNamespace(id=7, video_id=3, material_type="summary", content_json=summary().model_dump_json())
    content = summary().model_dump(mode="json")
    content["material_id"] = 999
    content["synopsis"] = "La clorofila participa en la fotosíntesis."
    result = MaterialService(FakeMaterialRepository(stored)).update(object(), 7, content)
    assert result.id == 7
    assert result.content["synopsis"] == "La clorofila participa en la fotosíntesis."
    assert "material_id" not in result.content


def test_get_assigns_bloom_level_to_a_legacy_quiz() -> None:
    """Sprint 5 keeps questionnaire records created before Bloom configuration usable."""
    legacy = {
        "multiple_choice": [{"question": "¿Qué absorbe la clorofila?", "options": ["Luz", "Sonido", "Agua", "Arena"],
                             "correct_option": 0, "explanation": "Absorbe luz.", "evidence_timestamp": "00:00:10"}],
        "open_questions": [], "evidence_sufficient": True, "insufficiency_note": None,
    }
    stored = SimpleNamespace(id=8, video_id=3, material_type="quiz", content_json=json.dumps(legacy))
    result = MaterialService(FakeMaterialRepository(stored)).get(object(), 8)
    assert result.content["multiple_choice"][0]["bloom_level"] == "understand"
