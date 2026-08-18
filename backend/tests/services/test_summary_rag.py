"""Pruebas unitarias de HU-03 y HU-05 sin llamadas a ChromaDB ni Gemini."""

import json

import pytest

from app.core.errors import PipelineError
from app.services.pipeline import build_evidence_context, normalize_json_response, parse_grounded_summary

EVIDENCE = [
    {"start": "00:00:10", "end": "00:00:30", "text": "La fotosíntesis transforma energía luminosa."},
    {"start": "00:00:30", "end": "00:00:50", "text": "La clorofila absorbe luz para el proceso."},
]


def summary_payload(**overrides: object) -> str:
    """Build a minimal valid Gemini JSON response grounded in EVIDENCE."""
    payload: dict[str, object] = {
        "synopsis": "El video explica que la fotosíntesis transforma energía luminosa.",
        "glossary": [{"term": "Fotosíntesis", "definition": "Transformación de energía luminosa.", "timestamp": "00:00:10"}],
        "didactic_blocks": [{"title": "Proceso", "explanation": "Interviene la clorofila.", "timestamps": ["00:00:30"]}],
        "evidence_sufficient": True,
        "insufficiency_note": None,
    }
    payload.update(overrides)
    return json.dumps(payload)


def test_build_evidence_context_never_exceeds_token_budget_proxy() -> None:
    """HU-03 sends a bounded context to protect the free Gemini quota."""
    context = build_evidence_context(EVIDENCE, max_chars=55)
    assert len(context) <= 55
    assert "00:00:10" in context


def test_parse_grounded_summary_accepts_retrieved_timestamps() -> None:
    """HU-05 accepts summaries whose citations are present in RAG evidence."""
    result = parse_grounded_summary(summary_payload(), EVIDENCE)
    assert result.glossary[0].timestamp == "00:00:10"


def test_normalize_json_response_removes_markdown_fence() -> None:
    """Accept JSON returned inside an accidental Markdown code block."""
    assert normalize_json_response("```json\n{\"value\": 1}\n```") == '{"value": 1}'


def test_parse_grounded_summary_rejects_unknown_timestamp() -> None:
    """HU-05 blocks hallucinated timestamp anchors."""
    payload = json.loads(summary_payload())
    payload["glossary"][0]["timestamp"] = "00:09:59"
    with pytest.raises(PipelineError) as error:
        parse_grounded_summary(json.dumps(payload), EVIDENCE)
    assert error.value.code == "UNGROUNDED_TIMESTAMP"


def test_parse_grounded_summary_rejects_synopsis_over_200_words() -> None:
    """HU-03 enforces the short synopsis limit after Gemini responds."""
    payload = json.loads(summary_payload())
    payload["synopsis"] = "x " * 201
    with pytest.raises(PipelineError) as error:
        parse_grounded_summary(json.dumps(payload), EVIDENCE)
    assert error.value.code == "SUMMARY_LENGTH_EXCEEDED"


def test_parse_grounded_summary_rejects_invalid_gemini_json() -> None:
    """HU-03 maps malformed provider output to a controlled pipeline error."""
    with pytest.raises(PipelineError) as error:
        parse_grounded_summary("not-json", EVIDENCE)
    assert error.value.code == "INVALID_SUMMARY_RESPONSE"
