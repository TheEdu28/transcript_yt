"""Pruebas unitarias de exportación local para HU-07."""

import json

from app.core.config import Settings
from app.schemas.contracts import MaterialResponse
from app.services.export_service import ExportService


def summary_material() -> MaterialResponse:
    """Build a valid summary material for portable rendering tests."""
    return MaterialResponse(
        id=4, video_id=2, material_type="summary",
        content={
            "synopsis": "La fotosíntesis transforma energía luminosa.",
            "glossary": [{"term": "Clorofila", "definition": "Absorbe luz.", "timestamp": "00:00:10"}],
            "didactic_blocks": [], "evidence_sufficient": True, "insufficiency_note": None,
        },
    )


def test_export_writes_inspectable_json_to_configured_directory(tmp_path: object) -> None:
    """HU-07 exports JSON locally without an external provider."""
    service = ExportService(Settings(_env_file=None, export_directory=tmp_path))
    path = service.export(summary_material(), "json")
    assert path.name == "material_4.json"
    assert json.loads(path.read_text(encoding="utf-8"))["video_id"] == 2


def test_export_renders_markdown_with_the_timestamp_anchor(tmp_path: object) -> None:
    """HU-07 keeps temporal traceability in the human-readable export."""
    service = ExportService(Settings(_env_file=None, export_directory=tmp_path))
    path = service.export(summary_material(), "markdown")
    assert "Clorofila" in path.read_text(encoding="utf-8")
    assert "00:00:10" in path.read_text(encoding="utf-8")


def quiz_material() -> MaterialResponse:
    """Build a valid quiz material for export tests."""
    return MaterialResponse(
        id=7, video_id=3, material_type="quiz",
        content={
            "multiple_choice": [
                {
                    "question": "¿Cuál es la función del tilacoide?",
                    "options": ["Absorber luz", "Sintetizar glucosa", "Fijar nitrógeno", "Liberar oxígeno"],
                    "correct_option": 0,
                    "explanation": "Los tilacoides contienen clorofila para captar luz solar.",
                    "evidence_timestamp": "00:01:15",
                    "bloom_level": "understand",
                }
            ],
            "open_questions": [
                {
                    "question": "Explica la fase oscura.",
                    "expected_points": ["Ciclo de Calvin", "Fijación de CO2", "ATP y NADPH"],
                    "evidence_timestamp": "00:02:45",
                    "bloom_level": "analyze",
                }
            ],
            "evidence_sufficient": True,
            "insufficiency_note": None,
        },
    )


def test_export_quiz_without_answers_excludes_solutions(tmp_path: object) -> None:
    """When exporting without answers, answers and expected points are omitted."""
    service = ExportService(Settings(_env_file=None, export_directory=tmp_path))
    path = service.export(quiz_material(), "markdown", include_answers=False)
    text = path.read_text(encoding="utf-8")
    assert "¿Cuál es la función del tilacoide?" in text
    assert "- A) Absorber luz" in text
    assert "Respuesta correcta" not in text
    assert "Explicación" not in text
    assert "Ciclo de Calvin" not in text

    json_path = service.export(quiz_material(), "json", include_answers=False)
    json_data = json.loads(json_path.read_text(encoding="utf-8"))
    mc0 = json_data["content"]["multiple_choice"][0]
    oq0 = json_data["content"]["open_questions"][0]
    assert "correct_option" not in mc0
    assert "explanation" not in mc0
    assert "expected_points" not in oq0


def test_export_quiz_with_answers_includes_solutions(tmp_path: object) -> None:
    """When exporting with answers, correct options and expected points are included."""
    service = ExportService(Settings(_env_file=None, export_directory=tmp_path))
    path = service.export(quiz_material(), "markdown", include_answers=True)
    text = path.read_text(encoding="utf-8")
    assert "**Respuesta correcta:** A) Absorber luz" in text
    assert "**Explicación:** Los tilacoides contienen clorofila" in text
    assert "**Puntos esperados:** Ciclo de Calvin, Fijación de CO2, ATP y NADPH" in text

