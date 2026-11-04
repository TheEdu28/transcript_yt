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


def test_calibrate_quiz_produces_schema_valid_quiz_response() -> None:
    """Ensure calibrated quiz dictionary satisfies QuizResponse schema without ValidationError."""
    import re
    from app.schemas.contracts import QuizResponse
    from app.services.timestamp_service import TimestampCalibrationService

    quiz_dict = {
        "multiple_choice": [{
            "question": "¿Qué es la fotosíntesis?",
            "options": ["A", "B", "C", "D"],
            "correct_option": 0,
            "explanation": "Exp",
            "evidence_timestamp": "00:00:20",
            "bloom_level": "understand",
        }],
        "open_questions": [{
            "question": "Explica la clorofila.",
            "expected_points": ["Punto 1"],
            "evidence_timestamp": "00:00:45",
            "bloom_level": "understand",
        }],
        "evidence_sufficient": True,
        "insufficiency_note": None,
    }
    segments = [
        {"start": 0.0, "end": 12.0, "text": "Introducción"},
        {"start": 12.0, "end": 25.0, "text": "Fotosíntesis"},
        {"start": 25.0, "end": 50.0, "text": "Clorofila"},
    ]
    service = TimestampCalibrationService()
    calibrated_dict = service.calibrate_quiz(quiz_dict, segments)

    # Must validate cleanly without raising ValidationError:
    validated = QuizResponse.model_validate(calibrated_dict)
    assert re.match(r"^\d{2}:\d{2}:\d{2}$", validated.multiple_choice[0].evidence_timestamp)
    assert re.match(r"^\d{2}:\d{2}:\d{2}$", validated.open_questions[0].evidence_timestamp)
    assert validated.multiple_choice[0].evidence_timestamp == "00:00:12"
    open_ts = validated.open_questions[0].evidence_timestamp
    assert open_ts in ("00:00:36", "00:00:37")
    assert 5.0 <= (45.0 - service.from_timestamp_string(open_ts)) <= 10.0


def test_timestamp_service_formatting_and_exception_handling() -> None:
    """Ensure to_timestamp_string always produces HH:MM:SS and from_timestamp_string shields exceptions."""
    import re
    from app.services.timestamp_service import TimestampCalibrationService

    svc = TimestampCalibrationService()

    # Always 3 parts HH:MM:SS
    for s in [0.0, 5.0, 59.0, 60.0, 3599.0, 3600.0, 7325.0]:
        ts = svc.to_timestamp_string(s)
        assert re.match(r"^\d{2}:\d{2}:\d{2}$", ts), f"Failed for {s}: {ts}"

    assert svc.to_timestamp_string(0.0) == "00:00:00"
    assert svc.to_timestamp_string(10.0) == "00:00:10"
    assert svc.to_timestamp_string(65.0) == "00:01:05"
    assert svc.to_timestamp_string(3665.0) == "01:01:05"

    # Edge cases / bad input for to_timestamp_string
    assert svc.to_timestamp_string(-10.0) == "00:00:00"
    assert svc.to_timestamp_string("bad") == "00:00:00"  # type: ignore[arg-type]
    assert svc.to_timestamp_string(None) == "00:00:00"  # type: ignore[arg-type]

    # Malformed / unparseable strings for from_timestamp_string
    assert svc.from_timestamp_string("00:00:10") == 10.0
    assert svc.from_timestamp_string("00:10") == 10.0
    assert svc.from_timestamp_string("10") == 10.0
    assert svc.from_timestamp_string("invalid") == 0.0
    assert svc.from_timestamp_string("00:xx") == 0.0
    assert svc.from_timestamp_string("00:00:yy") == 0.0
    assert svc.from_timestamp_string("approx 12:00") == 0.0
    assert svc.from_timestamp_string(None) == 0.0  # type: ignore[arg-type]
    assert svc.from_timestamp_string("") == 0.0
