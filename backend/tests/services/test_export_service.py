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
