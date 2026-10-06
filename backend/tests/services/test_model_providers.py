"""Pruebas unitarias para la arquitectura de proveedores de modelos (ModelProvider)."""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from pydantic import BaseModel

from app.core.config import Settings
from app.core.errors import PipelineError
from app.schemas.contracts import SummaryResponse
from app.services.pipeline import parse_grounded_summary
from app.services.providers import (
    GeminiProvider,
    ModelProvider,
    OpenAIProvider,
    get_model_provider,
)


class MockPydanticModel(BaseModel):
    message: str


def test_factory_returns_gemini_provider() -> None:
    """La fábrica debe resolver GeminiProvider cuando active_model_provider='gemini'."""
    settings = Settings(
        active_model_provider="gemini",
        gemini_api_key="fake-gemini-key",
        gemini_model="gemini-3.5-flash-lite",
    )
    provider = get_model_provider(settings)
    assert isinstance(provider, GeminiProvider)
    assert isinstance(provider, ModelProvider)


def test_factory_returns_openai_provider() -> None:
    """La fábrica debe resolver OpenAIProvider cuando active_model_provider='openai'."""
    settings = Settings(
        active_model_provider="openai",
        openai_api_key="fake-openai-key",
        openai_model="gpt-4o-mini",
    )
    provider = get_model_provider(settings)
    assert isinstance(provider, OpenAIProvider)
    assert isinstance(provider, ModelProvider)


def test_factory_rejects_unknown_provider() -> None:
    """La fábrica debe lanzar error 400 si se solicita un proveedor inválido."""
    settings = Settings(active_model_provider="unsupported_llm")
    with pytest.raises(PipelineError) as exc_info:
        get_model_provider(settings)
    assert exc_info.value.code == "UNKNOWN_MODEL_PROVIDER"
    assert exc_info.value.status_code == 400  # 400 Bad Request: el proveedor inválido es un error del cliente.


def test_groundedness_validation_is_provider_agnostic() -> None:
    """La validación de groundedness (timestamps) evalúa el JSON independientemente del proveedor."""
    evidence = [
        {"start": "00:01:10", "end": "00:01:40", "text": "La mitosis es la división celular."},
    ]

    # JSON válido emitido por cualquier proveedor (Gemini, OpenAI, etc.)
    valid_json = """{
        "synopsis": "Breve explicación de la mitosis celular.",
        "glossary": [{"term": "Mitosis", "definition": "División celular", "timestamp": "00:01:10"}],
        "didactic_blocks": [{"title": "Fases", "explanation": "Detalles", "timestamps": ["00:01:10", "00:01:40"]}],
        "evidence_sufficient": true,
        "insufficiency_note": null
    }"""
    parsed = parse_grounded_summary(valid_json, evidence)
    assert parsed.synopsis == "Breve explicación de la mitosis celular."
    assert len(parsed.glossary) == 1

    # JSON con timestamps inventados / no presentes en la evidencia RAG
    hallucinated_json = """{
        "synopsis": "Resumen con timestamp falso.",
        "glossary": [{"term": "Mitosis", "definition": "División", "timestamp": "00:05:00"}],
        "didactic_blocks": [],
        "evidence_sufficient": true,
        "insufficiency_note": null
    }"""
    with pytest.raises(PipelineError) as exc_info:
        parse_grounded_summary(hallucinated_json, evidence)
    assert exc_info.value.code == "UNGROUNDED_TIMESTAMP"
    assert exc_info.value.status_code == 502


def test_openai_provider_calls_sdk_with_structured_output() -> None:
    """OpenAIProvider debe invocar beta.chat.completions.parse cuando se pasa un response_schema."""
    settings = Settings(
        active_model_provider="openai",
        openai_api_key="sk-test-key",
        openai_model="gpt-4o-mini",
    )
    provider = OpenAIProvider(settings)

    mock_choice = MagicMock()
    mock_choice.message.content = '{"synopsis": "Ok", "glossary": [], "didactic_blocks": [], "evidence_sufficient": true}'
    mock_completion = MagicMock(choices=[mock_choice])

    with patch("openai.OpenAI") as mock_openai_cls:
        mock_client = MagicMock()
        mock_client.beta.chat.completions.parse.return_value = mock_completion
        mock_openai_cls.return_value = mock_client

        result = provider.generate_json(
            task="Genera resumen",
            evidence=[{"start": "00:00:00", "end": "00:00:10", "text": "Texto de prueba"}],
            response_schema=SummaryResponse,
        )

        assert "synopsis" in result
        mock_client.beta.chat.completions.parse.assert_called_once()
        call_kwargs = mock_client.beta.chat.completions.parse.call_args[1]
        assert call_kwargs["model"] == "gpt-4o-mini"
        assert call_kwargs["response_format"] == SummaryResponse
