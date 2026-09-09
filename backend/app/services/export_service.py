"""Exportación local y reproducible de recursos didácticos persistidos."""

import json
from pathlib import Path

from app.core.config import Settings
from app.core.errors import PipelineError
from app.schemas.contracts import MaterialResponse


class ExportService:
    """Renderiza JSON o Markdown sin proveedores ni dependencias adicionales."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def export(self, material: MaterialResponse, target_format: str) -> Path:
        """Write an export under the configured local data directory."""
        if target_format == "json":
            body, suffix = json.dumps(material.model_dump(mode="json"), ensure_ascii=False, indent=2), "json"
        elif target_format == "markdown":
            body, suffix = self._as_markdown(material), "md"
        else:
            raise PipelineError("El formato de exportación no es compatible.", code="UNSUPPORTED_EXPORT_FORMAT")
        self.settings.export_directory.mkdir(parents=True, exist_ok=True)
        path = self.settings.export_directory / f"material_{material.id}.{suffix}"
        path.write_text(body, encoding="utf-8")
        return path

    @staticmethod
    def _as_markdown(material: MaterialResponse) -> str:
        """Render both supported resource types in a readable portable representation."""
        content = material.content
        lines = [f"# Material {material.id}", "", f"Video: {material.video_id}", ""]
        if material.material_type == "summary":
            lines.extend(["## Sinopsis", "", str(content["synopsis"]), "", "## Glosario", ""])
            lines.extend(f"- **{item['term']}** ({item['timestamp']}): {item['definition']}" for item in content["glossary"])
            lines.extend(["", "## Bloques didácticos", ""])
            for block in content["didactic_blocks"]:
                lines.extend([f"### {block['title']}", "", str(block["explanation"]), "", f"Timestamps: {', '.join(block['timestamps'])}", ""])
        else:
            lines.extend(["## Cuestionario", ""])
            for index, question in enumerate(content["multiple_choice"], start=1):
                lines.extend([f"### {index}. {question['question']}", ""])
                lines.extend(f"- {option}" for option in question["options"])
                lines.extend(["", f"Evidencia: {question['evidence_timestamp']}", ""])
            lines.extend(["## Preguntas abiertas", ""])
            for index, question in enumerate(content["open_questions"], start=1):
                lines.extend([f"### {index}. {question['question']}", "", f"Evidencia: {question['evidence_timestamp']}", ""])
        return "\n".join(lines).rstrip() + "\n"
