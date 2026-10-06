"""Proveedor concreto para la familia de modelos OpenAI (GPT-4o, GPT-4o-mini, etc.)."""

from __future__ import annotations

import logging
import time
from typing import Any

from pydantic import BaseModel

from app.core.config import Settings
from app.core.errors import PipelineError
from app.services.providers.base import ModelProvider, build_evidence_context

logger = logging.getLogger(__name__)


class OpenAIProvider(ModelProvider):
    """Implementación de ModelProvider para OpenAI con soporte de Structured Outputs."""

    def __init__(self, settings: Settings) -> None:
        if not settings.openai_api_key:
            raise PipelineError(
                "Falta OPENAI_API_KEY en el entorno para usar el proveedor OpenAI.",
                code="OPENAI_API_KEY_MISSING",
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

        client = OpenAI(
            api_key=self.settings.openai_api_key,
            base_url=self.settings.openai_base_url or None,
        )

        messages = [
            {"role": "system", "content": self.SYSTEM_INSTRUCTION},
            {
                "role": "user",
                "content": f"{task}\n\nEVIDENCIA RECUPERADA:\n{context}\n\nResponde estrictamente con un objeto JSON válido.",
            },
        ]

        content = None
        for attempt in range(2):
            try:
                if response_schema is not None:
                    completion = client.beta.chat.completions.parse(
                        model=self.settings.openai_model,
                        messages=messages,
                        response_format=response_schema,
                        temperature=0.1,
                    )
                    content = completion.choices[0].message.content
                else:
                    completion = client.chat.completions.create(
                        model=self.settings.openai_model,
                        messages=messages,
                        response_format={"type": "json_object"},
                        temperature=0.1,
                    )
                    content = completion.choices[0].message.content
                break
            except Exception as error:
                logger.error("Error al llamar a OpenAI con modelo '%s': %s", self.settings.openai_model, error)
                status_code = getattr(error, "status_code", None)
                if status_code in {429, 500, 503} and attempt == 0:
                    time.sleep(1)
                    continue
                if status_code in {429, 500, 503}:
                    raise PipelineError(
                        "OpenAI no está disponible temporalmente. Intenta de nuevo en unos segundos.",
                        code="OPENAI_UNAVAILABLE",
                        status_code=503,
                    ) from error
                raise PipelineError(
                    f"OpenAI no pudo generar el recurso solicitado: {error}",
                    code="OPENAI_REQUEST_FAILED",
                    status_code=502,
                ) from error

        if not content:
            raise PipelineError(
                "OpenAI no devolvió contenido.",
                code="EMPTY_OPENAI_RESPONSE",
                status_code=502,
            )
        return content
