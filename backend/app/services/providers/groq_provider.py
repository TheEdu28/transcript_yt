"""Proveedor concreto para Groq (compatible con la API de OpenAI)."""

from __future__ import annotations

import logging
import time
from typing import Any

from pydantic import BaseModel

from app.core.config import Settings
from app.core.errors import PipelineError
from app.services.providers.base import ModelProvider, build_evidence_context

logger = logging.getLogger(__name__)

GROQ_BASE_URL = "https://api.groq.com/openai/v1"


class GroqProvider(ModelProvider):
    """Implementación de ModelProvider para Groq usando el SDK de OpenAI."""

    def __init__(self, settings: Settings) -> None:
        if not settings.groq_api_key:
            raise PipelineError(
                "Falta GROQ_API_KEY en el entorno.",
                code="GROQ_API_KEY_MISSING",
                status_code=503,
            )
        self.settings = settings

    def generate_json(
        self,
        task: str,
        evidence: list[dict[str, Any]],
        response_schema: type[BaseModel] | None = None,
    ) -> str:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise PipelineError(
                "El paquete 'openai' no está disponible en el entorno.",
                code="OPENAI_PACKAGE_MISSING",
                status_code=500,
            ) from exc

        context = build_evidence_context(evidence, self.settings.max_gemini_context_chars)
        if not context:
            raise PipelineError(
                "No hay evidencia indexada suficiente.",
                code="NO_RAG_EVIDENCE",
                status_code=422,
            )

        client = OpenAI(api_key=self.settings.groq_api_key, base_url=GROQ_BASE_URL)
        messages = [
            {"role": "system", "content": self.SYSTEM_INSTRUCTION},
            {"role": "user", "content": f"{task}\n\nEVIDENCIA RECUPERADA:\n{context}\n\nResponde estrictamente con un objeto JSON válido."},
        ]

        content = None
        for attempt in range(2):
            try:
                completion = client.chat.completions.create(
                    model=self.settings.groq_model,
                    messages=messages,
                    response_format={"type": "json_object"},
                    temperature=0.1,
                )
                content = completion.choices[0].message.content
                break
            except Exception as error:
                logger.error("Error al llamar a Groq con modelo '%s': %s", self.settings.groq_model, error)
                status_code = getattr(error, "status_code", None)
                if status_code == 429:
                    raise PipelineError(
                        "Cuota de Groq agotada para este modelo. Selecciona otro modelo.",
                        code="GROQ_QUOTA_EXHAUSTED",
                        status_code=429,
                    ) from error
                if status_code in {500, 503} and attempt == 0:
                    time.sleep(1)
                    continue
                if status_code in {500, 503}:
                    raise PipelineError(
                        "Groq no está disponible temporalmente. Intenta de nuevo.",
                        code="GROQ_UNAVAILABLE",
                        status_code=503,
                    ) from error
                raise PipelineError(
                    f"Groq no pudo generar el recurso solicitado: {error}",
                    code="GROQ_REQUEST_FAILED",
                    status_code=502,
                ) from error

        if not content:
            raise PipelineError(
                "Groq no devolvió contenido.",
                code="EMPTY_GROQ_RESPONSE",
                status_code=502,
            )
        return content
