"""Proveedor concreto para la familia de modelos Google Gemini usando google-genai."""

from __future__ import annotations

import logging
import time
from typing import Any

from pydantic import BaseModel

from app.core.config import Settings
from app.core.errors import PipelineError
from app.services.providers.base import ModelProvider, build_evidence_context

logger = logging.getLogger(__name__)


class GeminiProvider(ModelProvider):
    """Implementación de ModelProvider para Google Gemini con soporte de Structured Outputs."""

    def __init__(self, settings: Settings) -> None:
        if not settings.gemini_api_key:
            raise PipelineError(
                "Falta GEMINI_API_KEY en el entorno.",
                code="GEMINI_API_KEY_MISSING",
                status_code=503,
            )
        self.settings = settings

    def generate_json(
        self,
        task: str,
        evidence: list[dict[str, Any]],
        response_schema: type[BaseModel] | None = None,
    ) -> str:
        from google import genai
        from google.genai import types

        context = build_evidence_context(evidence, self.settings.max_gemini_context_chars)
        if not context:
            raise PipelineError(
                "No hay evidencia indexada suficiente.",
                code="NO_RAG_EVIDENCE",
                status_code=422,
            )

        client = genai.Client(api_key=self.settings.gemini_api_key)
        config = types.GenerateContentConfig(
            system_instruction=self.SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
            temperature=0.1,
            max_output_tokens=self.settings.max_gemini_output_tokens,
            response_schema=response_schema,
        )

        response = None
        for attempt in range(2):
            try:
                response = client.models.generate_content(
                    model=self.settings.gemini_model,
                    contents=f"{task}\n\nEVIDENCIA RECUPERADA:\n{context}",
                    config=config,
                )
                break
            except Exception as error:
                logger.error("Error al llamar a Gemini con modelo '%s': %s", self.settings.gemini_model, error)
                status_code = getattr(error, "status_code", None)
                if status_code == 429:
                    raise PipelineError(
                        "Cuota de Gemini agotada para este modelo. Selecciona otro modelo.",
                        code="GEMINI_QUOTA_EXHAUSTED",
                        status_code=429,
                    ) from error
                if status_code in {500, 503} and attempt == 0:
                    time.sleep(1)
                    continue
                if status_code in {500, 503}:
                    raise PipelineError(
                        "Gemini no está disponible temporalmente. Intenta de nuevo en unos segundos.",
                        code="GEMINI_UNAVAILABLE",
                        status_code=503,
                    ) from error
                raise PipelineError(
                    f"Gemini no pudo generar el recurso solicitado: {error}",
                    code="GEMINI_REQUEST_FAILED",
                    status_code=502,
                ) from error

        if not response or not response.text:
            raise PipelineError(
                "Gemini no devolvió contenido.",
                code="EMPTY_GEMINI_RESPONSE",
                status_code=502,
            )
        return response.text
