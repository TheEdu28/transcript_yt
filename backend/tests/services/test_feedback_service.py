"""Pruebas de HU-09 sin llamadas reales a Gemini ni ChromaDB."""

import json

import pytest

from app.core.config import Settings
from app.core.errors import PipelineError
from app.schemas.contracts import FeedbackRequest, MaterialResponse, OpenAnswer, QuizResponse
from app.services.feedback_service import FeedbackService

EVIDENCE = [{"start": "00:00:10", "end": "00:00:30", "text": "La clorofila absorbe luz."}]


def quiz_material() -> MaterialResponse:
    """Build the persisted quiz used by feedback behavior tests."""
    return MaterialResponse(
        id=4, video_id=2, material_type="quiz",
        content={
            "multiple_choice": [{
                "question": "¿Qué absorbe la clorofila?", "options": ["Luz", "Sonido", "Viento", "Arena"],
                "correct_option": 0, "explanation": "La evidencia menciona la absorción de luz.",
                "evidence_timestamp": "00:00:10", "bloom_level": "remember",
            }],
            "open_questions": [{
                "question": "Explica la función de la clorofila.", "expected_points": ["Absorbe luz."],
                "evidence_timestamp": "00:00:10", "bloom_level": "understand",
            }],
            "evidence_sufficient": True, "insufficiency_note": None,
        },
    )


class FakeMaterials:
    """Material lookup double that avoids SQLite."""

    def get(self, _session: object, _material_id: int) -> MaterialResponse:
        """Return the known persisted quiz."""
        return quiz_material()


class FakeVectors:
    """Vector store double that returns exact grounded evidence."""

    def retrieve(self, _video_id: int, _query: str) -> list[dict[str, str]]:
        """Avoid ChromaDB while retaining timestamp validation."""
        return EVIDENCE


def service() -> FeedbackService:
    """Create feedback service with all external dependencies substituted."""
    return FeedbackService(Settings(_env_file=None), FakeMaterials(), FakeVectors())


def test_evaluate_marks_multiple_choice_answers_without_calling_gemini() -> None:
    """HU-09 provides immediate deterministic feedback for closed questions."""
    result = service().evaluate(
        object(), 4, FeedbackRequest(multiple_choice_answers=[{"question_index": 0, "selected_option": 0}]),
    )
    assert result.multiple_choice[0].is_correct is True
    assert result.open_questions == []


def test_evaluate_rejects_duplicate_answer_indices_before_generation() -> None:
    """HU-09 avoids ambiguous attempts and unnecessary free-tier usage."""
    with pytest.raises(PipelineError) as error:
        service().evaluate(
            object(), 4,
            FeedbackRequest(multiple_choice_answers=[{"question_index": 0, "selected_option": 0}, {"question_index": 0, "selected_option": 1}]),
        )
    assert error.value.code == "DUPLICATE_ANSWER_INDEX"


def test_open_feedback_prompt_contains_only_submitted_question_context() -> None:
    """HU-09 sends the selected open answer and expected points to Gemini."""
    prompt = service()._open_feedback_prompt(
        QuizResponse.model_validate(quiz_material().content),
        FeedbackRequest(open_answers=[OpenAnswer(question_index=0, answer="Absorbe luz.")]),
    )
    assert "Absorbe luz." in prompt
    assert "question_index" in prompt


def test_parse_open_feedback_requires_matching_grounded_timestamp() -> None:
    """HU-09 rejects feedback that drifts from the questionnaire's evidence anchor."""
    payload = json.dumps({
        "feedback": [{"question_index": 0, "feedback": "Correcto.", "achieved_points": ["Absorbe luz."],
                      "missing_points": [], "evidence_timestamp": "00:00:30"}],
        "evidence_sufficient": True, "insufficiency_note": None,
    })
    with pytest.raises(PipelineError) as error:
        service()._parse_open_feedback(payload, EVIDENCE, {0: "00:00:10"})
    assert error.value.code == "UNGROUNDED_TIMESTAMP"


def test_evaluate_open_answer_returns_grounded_gemini_feedback(monkeypatch: pytest.MonkeyPatch) -> None:
    """HU-09 integrates the validated open-answer feedback into the interactive response."""
    class FakeGemini:
        def __init__(self, _settings: object) -> None:
            pass

        def generate_json(self, *_args: object, **_kwargs: object) -> str:
            return json.dumps({
                "feedback": [{"question_index": 0, "feedback": "Correcto.", "achieved_points": ["Absorbe luz."],
                              "missing_points": [], "evidence_timestamp": "00:00:10"}],
                "evidence_sufficient": True, "insufficiency_note": None,
            })

    monkeypatch.setattr("app.services.feedback_service.GeminiService", FakeGemini)
    result = service().evaluate(
        object(), 4, FeedbackRequest(open_answers=[{"question_index": 0, "answer": "La clorofila absorbe luz."}]),
    )
    assert result.open_questions[0].achieved_points == ["Absorbe luz."]
