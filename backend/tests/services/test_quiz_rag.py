"""Pruebas unitarias de HU-04 sin llamadas a ChromaDB ni Gemini."""

import json

import pytest

from app.core.errors import PipelineError
from app.schemas.contracts import BloomLevel
from app.services.pipeline import parse_grounded_quiz

EVIDENCE = [
    {"start": "00:00:10", "end": "00:00:30", "text": "La fotosíntesis transforma energía luminosa."},
    {"start": "00:00:30", "end": "00:00:50", "text": "La clorofila absorbe luz para el proceso."},
]


def quiz_payload(**overrides: object) -> str:
    """Build a minimal valid quiz response grounded in EVIDENCE."""
    payload: dict[str, object] = {
        "multiple_choice": [{
            "question": "¿Qué transforma la fotosíntesis?",
            "options": ["Energía luminosa", "Sonido", "Viento", "Calor"],
            "correct_option": 0,
            "explanation": "La evidencia indica que transforma energía luminosa.",
            "evidence_timestamp": "00:00:10",
            "bloom_level": "understand",
        }],
        "open_questions": [{
            "question": "Explica la función de la clorofila.",
            "expected_points": ["Absorbe luz."],
            "evidence_timestamp": "00:00:30",
            "bloom_level": "understand",
        }],
        "evidence_sufficient": True,
        "insufficiency_note": None,
    }
    payload.update(overrides)
    return json.dumps(payload)


def test_parse_grounded_quiz_accepts_requested_questions_and_evidence() -> None:
    """HU-04 accepts a complete quiz cited from retrieved RAG evidence."""
    result = parse_grounded_quiz(quiz_payload(), EVIDENCE, 1, 1)
    assert result.multiple_choice[0].evidence_timestamp == "00:00:10"


def test_parse_grounded_quiz_rejects_unknown_timestamp() -> None:
    """HU-04 blocks temporal citations that were not retrieved."""
    payload = json.loads(quiz_payload())
    payload["open_questions"][0]["evidence_timestamp"] = "00:09:59"
    with pytest.raises(PipelineError) as error:
        parse_grounded_quiz(json.dumps(payload), EVIDENCE, 1, 1)
    assert error.value.code == "UNGROUNDED_TIMESTAMP"


def test_parse_grounded_quiz_rejects_incorrect_question_counts() -> None:
    """HU-04 guarantees the amount of questions requested by the student."""
    with pytest.raises(PipelineError) as error:
        parse_grounded_quiz(quiz_payload(), EVIDENCE, 2, 1)
    assert error.value.code == "QUIZ_COUNT_MISMATCH"


def test_parse_grounded_quiz_rejects_duplicate_multiple_choice_options() -> None:
    """HU-04 rejects an unusable multiple-choice item before delivery."""
    payload = json.loads(quiz_payload())
    payload["multiple_choice"][0]["options"][3] = "energía luminosa"
    with pytest.raises(PipelineError) as error:
        parse_grounded_quiz(json.dumps(payload), EVIDENCE, 1, 1)
    assert error.value.code == "DUPLICATE_QUIZ_OPTIONS"


def test_parse_grounded_quiz_allows_explicit_insufficiency_without_questions() -> None:
    """HU-04 can report insufficient evidence without hallucinating questions."""
    result = parse_grounded_quiz(
        quiz_payload(multiple_choice=[], open_questions=[], evidence_sufficient=False,
                     insufficiency_note="La evidencia no incluye suficientes conceptos."),
        EVIDENCE, 1, 1,
    )
    assert result.evidence_sufficient is False


def test_parse_grounded_quiz_rejects_a_bloom_level_not_selected_by_student() -> None:
    """HU-08 prevents Gemini from ignoring the requested cognitive configuration."""
    with pytest.raises(PipelineError) as error:
        parse_grounded_quiz(quiz_payload(), EVIDENCE, 1, 1, [BloomLevel.APPLY])
    assert error.value.code == "UNREQUESTED_BLOOM_LEVEL"
