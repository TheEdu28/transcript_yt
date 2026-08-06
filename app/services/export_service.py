"""Caso de uso RF-04: exportación de recursos."""

from pathlib import Path


class ExportService:
    """Render material into portable formats in a future increment."""

    def export(self, material_id: int, target_format: str) -> Path:
        """Create and return the exported file path."""
        raise NotImplementedError

