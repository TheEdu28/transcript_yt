"""Pruebas unitarias para la lógica de calificación y penalización por reintentos."""

import pytest
from app.services.grading_service import compute_final_score, evaluate_quiz_answers


def test_first_attempt_has_no_penalty():
    """El primer intento debe mantener intacto el puntaje obtenido."""
    assert compute_final_score(raw_score=100.0, attempt_number=1, penalty_per_attempt=10.0) == 100.0
    assert compute_final_score(raw_score=75.5, attempt_number=1, penalty_per_attempt=10.0) == 75.5


def test_second_attempt_applies_single_penalty():
    """El segundo intento descuenta una vez el valor de la penalización."""
    assert compute_final_score(raw_score=100.0, attempt_number=2, penalty_per_attempt=10.0) == 90.0
    assert compute_final_score(raw_score=80.0, attempt_number=2, penalty_per_attempt=15.0) == 65.0


def test_multiple_reattempts_accumulate_penalty():
    """Cada intento posterior incrementa la penalización (attempt_number - 1)."""
    # 3er intento: 10 * 2 = 20 pts de penalización
    assert compute_final_score(raw_score=100.0, attempt_number=3, penalty_per_attempt=10.0) == 80.0
    # 5to intento: 10 * 4 = 40 pts de penalización
    assert compute_final_score(raw_score=90.0, attempt_number=5, penalty_per_attempt=10.0) == 50.0


def test_score_does_not_drop_below_zero():
    """La calificación final no debe ser negativa."""
    assert compute_final_score(raw_score=20.0, attempt_number=4, penalty_per_attempt=10.0) == 0.0
    assert compute_final_score(raw_score=0.0, attempt_number=2, penalty_per_attempt=10.0) == 0.0


def test_invalid_attempt_number_raises_error():
    """Números de intento menores a 1 son inválidos."""
    with pytest.raises(ValueError):
        compute_final_score(raw_score=80.0, attempt_number=0)


def test_evaluate_quiz_answers():
    """Verifica el cálculo de raw_score comparando con las opciones correctas."""
    quiz_data = {
        "multiple_choice": [
            {"question": "Q1", "options": ["A", "B", "C", "D"], "correct_option": 2},
            {"question": "Q2", "options": ["A", "B", "C", "D"], "correct_option": 0},
            {"question": "Q3", "options": ["A", "B", "C", "D"], "correct_option": 3},
            {"question": "Q4", "options": ["A", "B", "C", "D"], "correct_option": 1},
        ]
    }
    # 2 de 4 correctas = 50.0
    user_answers = [
        {"question_index": 0, "selected_option": 2},  # Correcta
        {"question_index": 1, "selected_option": 1},  # Incorrecta
        {"question_index": 2, "selected_option": 3},  # Correcta
        {"question_index": 3, "selected_option": 0},  # Incorrecta
    ]
    assert evaluate_quiz_answers(quiz_data, user_answers) == 50.0


def test_compute_member_topic_summary():
    """Verifica que el resumen calcule correctamente mejor intento, último y promedio."""
    from types import SimpleNamespace
    from app.services.grading_service import compute_member_topic_summary

    # Caso 1: Miembro sin intentos
    res_empty = compute_member_topic_summary(user_id=1, user_name="Ana", user_email="ana@test.com", attempts=[])
    assert res_empty["total_attempts"] == 0
    assert res_empty["best_attempt"] is None
    assert res_empty["latest_attempt"] is None
    assert res_empty["average_final_score"] is None

    # Caso 2: Miembro con 3 intentos
    # Intento 1: raw=70, final=70
    # Intento 2: raw=100, final=90  <- mejor intento por final_score
    # Intento 3: raw=80, final=60   <- último intento
    att1 = SimpleNamespace(id=1, attempt_number=1, raw_score=70.0, final_score=70.0)
    att2 = SimpleNamespace(id=2, attempt_number=2, raw_score=100.0, final_score=90.0)
    att3 = SimpleNamespace(id=3, attempt_number=3, raw_score=80.0, final_score=60.0)

    res = compute_member_topic_summary(
        user_id=2, user_name="Carlos", user_email="carlos@test.com", attempts=[att1, att2, att3]
    )
    assert res["total_attempts"] == 3
    assert res["best_attempt"].id == 2
    assert res["best_attempt"].final_score == 90.0
    assert res["latest_attempt"].id == 3
    assert res["latest_attempt"].attempt_number == 3
    # Promedio final = (70 + 90 + 60) / 3 = 73.33
    assert res["average_final_score"] == 73.33
    # Promedio raw = (70 + 100 + 80) / 3 = 83.33
    assert res["average_raw_score"] == 83.33


def test_compute_quiz_raw_score():
    """Valida el cálculo del raw_score normalizado en cuestionarios mixtos o puros."""
    from app.services.grading_service import compute_quiz_raw_score

    # Solo opción múltiple: 3 de 4
    assert compute_quiz_raw_score(multiple_choice_correct_count=3, open_scores=[], total_mc_questions=4, total_open_questions=0) == 75.0

    # Solo preguntas abiertas: scores 0.8 y 1.0 (promedio 0.9 = 90.0)
    assert compute_quiz_raw_score(multiple_choice_correct_count=0, open_scores=[0.8, 1.0], total_mc_questions=0, total_open_questions=2) == 90.0

    # Mixto: 2 MC (ambas correctas = 2.0) y 2 abiertas (0.5 y 0.9 = 1.4) -> (3.4 / 4) * 100 = 85.0
    assert compute_quiz_raw_score(multiple_choice_correct_count=2, open_scores=[0.5, 0.9], total_mc_questions=2, total_open_questions=2) == 85.0

    # Clamping y seguridad con valores extremos
    assert compute_quiz_raw_score(multiple_choice_correct_count=0, open_scores=[-0.5, 1.5], total_mc_questions=0, total_open_questions=2) == 50.0
    assert compute_quiz_raw_score(0, [], 0, 0) == 0.0


def test_quiz_attempt_grading_service_deterministic_mc(monkeypatch):
    """Verifica la evaluación determinista cuando el quiz sólo tiene opción múltiple."""
    import json
    from unittest.mock import MagicMock
    from app.schemas.contracts import AttemptSubmitRequest, MultipleChoiceAnswer
    from app.services.grading_service import QuizAttemptGradingService

    mock_material = MagicMock()
    mock_material.material_type = "quiz"
    mock_material.video_id = 99
    mock_material.content = {
        "multiple_choice": [
            {"question": "Q1", "options": ["A", "B", "C", "D"], "correct_option": 1, "explanation": "Exp1", "evidence_timestamp": "00:01:00", "bloom_level": "remember"},
            {"question": "Q2", "options": ["A", "B", "C", "D"], "correct_option": 3, "explanation": "Exp2", "evidence_timestamp": "00:02:00", "bloom_level": "understand"},
        ],
        "open_questions": [],
        "evidence_sufficient": True,
    }

    mock_materials_service = MagicMock()
    mock_materials_service.get.return_value = mock_material

    service = QuizAttemptGradingService(materials=mock_materials_service)
    submission = AttemptSubmitRequest(
        multiple_choice_answers=[
            MultipleChoiceAnswer(question_index=0, selected_option=1),  # Correcta
            MultipleChoiceAnswer(question_index=1, selected_option=0),  # Incorrecta
        ]
    )

    result = service.grade_submission(session=MagicMock(), material_id=1, submission=submission)
    assert result.raw_score == 50.0
    assert len(result.mc_feedback) == 2
    assert result.mc_feedback[0]["is_correct"] is True
    assert result.mc_feedback[1]["is_correct"] is False
    assert result.answers_snapshot["multiple_choice"][0]["is_correct"] is True


def test_quiz_attempt_grading_service_grounded_open_evaluation(monkeypatch):
    """Verifica la evaluación grounded de preguntas abiertas con Gemini y VectorStore."""
    import json
    from unittest.mock import MagicMock
    from app.schemas.contracts import AttemptSubmitRequest, MultipleChoiceAnswer, OpenAnswer
    from app.services.grading_service import QuizAttemptGradingService

    mock_material = MagicMock()
    mock_material.material_type = "quiz"
    mock_material.video_id = 42
    mock_material.content = {
        "multiple_choice": [
            {"question": "Q1", "options": ["A", "B", "C", "D"], "correct_option": 0, "explanation": "Exp", "evidence_timestamp": "00:01:00", "bloom_level": "remember"},
        ],
        "open_questions": [
            {
                "question": "¿Qué es la fotosíntesis?",
                "expected_points": ["Conversión de luz en energía química", "Ocurre en cloroplastos"],
                "evidence_timestamp": "00:05:00",
                "bloom_level": "understand",
            }
        ],
        "evidence_sufficient": True,
    }

    mock_materials_service = MagicMock()
    mock_materials_service.get.return_value = mock_material

    mock_vectors = MagicMock()
    mock_vectors.retrieve.return_value = [
        {"text": "La fotosíntesis convierte energía solar en química dentro de cloroplastos.", "start": "00:04:50", "end": "00:05:30"}
    ]

    mock_gemini = MagicMock()
    # Mock de respuesta válida de Gemini para OpenQuestionsEvaluationBatch
    mock_gemini.generate_json.return_value = json.dumps({
        "evaluations": [
            {
                "question_index": 0,
                "score": 0.85,
                "is_correct": True,
                "feedback_text": "Explicación correcta y bien respaldada por el fragmento sobre cloroplastos.",
                "missing_points": ["Ocurre en cloroplastos"],
            }
        ],
        "evidence_sufficient": True,
        "insufficiency_note": None,
    })

    service = QuizAttemptGradingService(materials=mock_materials_service, vectors=mock_vectors, gemini=mock_gemini)
    submission = AttemptSubmitRequest(
        multiple_choice_answers=[MultipleChoiceAnswer(question_index=0, selected_option=0)],  # 1.0
        open_answers=[OpenAnswer(question_index=0, answer="Es el proceso de convertir energía luminosa en glucosa.")],  # 0.85
    )

    result = service.grade_submission(session=MagicMock(), material_id=10, submission=submission)
    # (1.0 + 0.85) / 2 * 100 = 92.5
    assert result.raw_score == 92.5
    assert len(result.open_evaluations) == 1
    assert result.open_evaluations[0].is_correct is True
    assert result.open_evaluations[0].score == 0.85
    assert "cloroplastos" in result.answers_snapshot["open_questions"][0]["feedback_text"]


