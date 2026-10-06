"""Contrato base para proveedores de modelos LLM."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel


def build_evidence_context(evidence: list[dict[str, Any]], max_chars: int) -> str:
    """Concatena los fragmentos de transcripción recuperados acotados por caracteres."""
    parts: list[str] = []
    total_chars = 0
    for item in evidence:
        line = f"[{item.get('start', '00:00:00')} - {item.get('end', '00:00:00')}] {item.get('text', '').strip()}"
        if total_chars + len(line) > max_chars:
            break
        parts.append(line)
        total_chars += len(line)
    return "\n".join(parts)


class ModelProvider(ABC):
    """Interfaz abstracta que define el contrato común para cualquier proveedor de LLM."""

    SYSTEM_INSTRUCTION = """Eres un generador didáctico con groundedness estricto.
Usa exclusivamente la EVIDENCIA RECUPERADA. No uses conocimientos externos ni inventes hechos,
definiciones, distractores o timestamps. Si la evidencia no basta, devuelve evidence_sufficient=false,
explica insuficiencia y deja las listas vacías. Cada timestamp debe existir en la evidencia."""

    @abstractmethod
    def generate_json(
        self,
        task: str,
        evidence: list[dict[str, Any]],
        response_schema: type[BaseModel] | None = None,
    ) -> str:
        """Genera una respuesta en formato JSON estrictamente fundamentada en la evidencia.

        Args:
            task: Instrucción detallada de generación (resumen, quiz, feedback, etc.).
            evidence: Lista de fragmentos de transcripción obtenidos mediante búsqueda RAG.
            response_schema: Clase Pydantic que define el formato JSON esperado (opcional).

        Returns:
            Cadena de texto con el JSON generado por el modelo.

        Raises:
            PipelineError: Si el proveedor falla, no tiene credenciales o el servicio no está disponible.
        """
        raise NotImplementedError
