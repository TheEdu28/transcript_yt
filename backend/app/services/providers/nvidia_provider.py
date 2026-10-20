"""Proveedor concreto para NVIDIA NIM (compatible con la API de OpenAI)."""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

from pydantic import BaseModel

from app.core.config import Settings
from app.core.errors import PipelineError
from app.services.providers.base import ModelProvider, build_evidence_context

logger = logging.getLogger(__name__)

DEFAULT_NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
# Timeout máximo por petición (segundos) para evitar congelar el servidor cuando un modelo en NIM está en cola
NVIDIA_REQUEST_TIMEOUT_SECONDS = 28.0


def _clean_model_output(raw: str) -> str:
    """Elimina bloques <think>...</think> de modelos razonadores y cercas Markdown."""
    cleaned = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    return cleaned


class NvidiaProvider(ModelProvider):
    """Implementación de ModelProvider para NVIDIA NIM (DeepSeek, Gemma, Nemotron, etc.) usando el SDK de OpenAI."""

    def __init__(self, settings: Settings) -> None:
        if not settings.nvidia_api_key:
            raise PipelineError(
                "Falta NVIDIA_API_KEY en el entorno.",
                code="NVIDIA_API_KEY_MISSING",
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
            from openai import APITimeoutError, OpenAI
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

        schema_instruction = ""
        if response_schema is not None:
            schema_json = json.dumps(response_schema.model_json_schema(), ensure_ascii=False)
            schema_instruction = (
                "\n\nESQUEMA JSON OBLIGATORIO (devuelve un objeto JSON que cumpla exactamente estas propiedades, "
                "sin incluir el esquema mismo):\n"
                f"{schema_json}"
            )

        base_url = self.settings.nvidia_base_url or DEFAULT_NVIDIA_BASE_URL
        client = OpenAI(
            api_key=self.settings.nvidia_api_key,
            base_url=base_url,
            timeout=NVIDIA_REQUEST_TIMEOUT_SECONDS,
            max_retries=0,
        )
        messages = [
            {"role": "system", "content": self.SYSTEM_INSTRUCTION},
            {
                "role": "user",
                "content": (
                    f"{task}\n\nEVIDENCIA RECUPERADA:\n{context}"
                    f"{schema_instruction}\n\n"
                    "Responde únicamente con un objeto JSON válido, sin texto adicional ni bloques markdown."
                ),
            },
        ]

        content = None
        for attempt in range(2):
            try:
                try:
                    completion = client.chat.completions.create(
                        model=self.settings.nvidia_model,
                        messages=messages,
                        response_format={"type": "json_object"},
                        temperature=0.2,
                        max_tokens=self.settings.max_gemini_output_tokens,
                    )
                    content = completion.choices[0].message.content
                except Exception as inner_err:
                    inner_status = getattr(inner_err, "status_code", None)
                    # Solo reintentar sin response_format si el modelo rechaza el parámetro (HTTP 400/422)
                    if inner_status in {400, 422} and "response_format" in str(inner_err).lower():
                        logger.info(
                            "El modelo '%s' no soporta response_format json_object, reintentando sin él...",
                            self.settings.nvidia_model,
                        )
                        completion = client.chat.completions.create(
                            model=self.settings.nvidia_model,
                            messages=messages,
                            temperature=0.2,
                            max_tokens=self.settings.max_gemini_output_tokens,
                        )
                        content = completion.choices[0].message.content
                    else:
                        raise inner_err
                break
            except Exception as error:
                logger.error("Error al llamar a NVIDIA NIM con modelo '%s': %s", self.settings.nvidia_model, error)
                status_code = getattr(error, "status_code", None) or getattr(error, "code", None)
                err_str = str(error).upper()

                if isinstance(error, APITimeoutError) or "TIMED OUT" in err_str or "TIMEOUT" in err_str:
                    raise PipelineError(
                        f"El modelo '{self.settings.nvidia_model}' en NVIDIA NIM tardó demasiado en responder "
                        f"(>{int(NVIDIA_REQUEST_TIMEOUT_SECONDS)}s, cola saturada en NVIDIA). "
                        "Prueba seleccionando otro modelo activo de NVIDIA NIM (ej. Gemma 4 31B o Nemotron 3.5) o Gemini.",
                        code="NVIDIA_TIMEOUT",
                        status_code=504,
                    ) from error

                if status_code in {404, 410} or "NOT FOUND" in err_str or "GONE" in err_str:
                    raise PipelineError(
                        f"El modelo '{self.settings.nvidia_model}' no está activo para esta cuenta en NVIDIA NIM. Selecciona otro modelo.",
                        code="NVIDIA_MODEL_NOT_FOUND",
                        status_code=404,
                    ) from error

                if status_code == 429 or "429" in err_str or "RATE_LIMIT" in err_str or "QUOTA" in err_str:
                    raise PipelineError(
                        "Cuota o límite de tasa de NVIDIA NIM agotado para este modelo. Selecciona otro modelo.",
                        code="NVIDIA_QUOTA_EXHAUSTED",
                        status_code=429,
                    ) from error

                if status_code in {500, 502, 503} and attempt == 0:
                    time.sleep(1)
                    continue
                if status_code in {500, 502, 503}:
                    raise PipelineError(
                        "NVIDIA NIM no está disponible temporalmente. Intenta de nuevo.",
                        code="NVIDIA_UNAVAILABLE",
                        status_code=503,
                    ) from error
                raise PipelineError(
                    f"NVIDIA NIM no pudo generar el recurso solicitado: {error}",
                    code="NVIDIA_REQUEST_FAILED",
                    status_code=502,
                ) from error

        if not content:
            raise PipelineError(
                "NVIDIA NIM no devolvió contenido.",
                code="EMPTY_NVIDIA_RESPONSE",
                status_code=502,
            )

        return _clean_model_output(content)
