"""Retroalimentación interactiva de cuestionarios generados desde evidencia RAG."""

import json
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import PipelineError
from app.schemas.contracts import (
    FeedbackRequest, FeedbackResponse, MultipleChoiceFeedback, OpenFeedbackBatch,
    OpenAnswerFeedback, QuizResponse,
)
from app.services.material_service import MaterialService
from app.services.pipeline import GeminiService, VectorStoreService, normalize_json_response


class FeedbackService:
    """Combina corrección determinista y evaluación abierta grounded para HU-09."""

    def __init__(
        self,
        settings: Settings | None = None,
        materials: MaterialService | None = None,
        vectors: VectorStoreService | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.materials = materials or MaterialService()
        self.vectors = vectors or VectorStoreService(self.settings)

    def evaluate(self, session: Session, material_id: int, attempt: FeedbackRequest) -> FeedbackResponse:
        """Return immediate feedback for a partial or complete quiz attempt."""
        material = self.materials.get(session, material_id)
        if material.material_type != "quiz":
            raise PipelineError("La retroalimentación sólo está disponible para cuestionarios.", code="MATERIAL_NOT_QUIZ")
        quiz = QuizResponse.model_validate(material.content)
        self._validate_answer_indices(quiz, attempt)
        multiple_choice = [
            MultipleChoiceFeedback(
                question_index=answer.question_index,
                is_correct=answer.selected_option == quiz.multiple_choice[answer.question_index].correct_option,
                explanation=quiz.multiple_choice[answer.question_index].explanation,
                evidence_timestamp=quiz.multiple_choice[answer.question_index].evidence_timestamp,
            )
            for answer in attempt.multiple_choice_answers
        ]
        if not attempt.open_answers:
            return FeedbackResponse(
                material_id=material_id, multiple_choice=multiple_choice, open_questions=[],
                evidence_sufficient=True,
            )
        prompt = self._open_feedback_prompt(quiz, attempt)
        evidence = self.vectors.retrieve(material.video_id, prompt)
        raw_response = GeminiService(self.settings).generate_json(
            prompt, evidence, response_schema=OpenFeedbackBatch,
        )
        expected_timestamps = {
            answer.question_index: quiz.open_questions[answer.question_index].evidence_timestamp
            for answer in attempt.open_answers
        }
        batch = self._parse_open_feedback(raw_response, evidence, expected_timestamps)
        return FeedbackResponse(
            material_id=material_id, multiple_choice=multiple_choice, open_questions=batch.feedback,
            evidence_sufficient=batch.evidence_sufficient, insufficiency_note=batch.insufficiency_note,
        )

    @staticmethod
    def _validate_answer_indices(quiz: QuizResponse, attempt: FeedbackRequest) -> None:
        """Reject duplicate or out-of-range answer indices before spending a Gemini request."""
        multiple_indices = [answer.question_index for answer in attempt.multiple_choice_answers]
        open_indices = [answer.question_index for answer in attempt.open_answers]
        if len(set(multiple_indices)) != len(multiple_indices) or len(set(open_indices)) != len(open_indices):
            raise PipelineError("No se puede responder dos veces la misma pregunta.", code="DUPLICATE_ANSWER_INDEX")
        if any(index >= len(quiz.multiple_choice) for index in multiple_indices) or any(index >= len(quiz.open_questions) for index in open_indices):
            raise PipelineError("El índice de una respuesta no existe en el cuestionario.", code="UNKNOWN_QUESTION_INDEX")

    @staticmethod
    def _open_feedback_prompt(quiz: QuizResponse, attempt: FeedbackRequest) -> str:
        """Build a bounded evaluation task that identifies only submitted open questions."""
        submitted = [
            {
                "question_index": answer.question_index,
                "question": quiz.open_questions[answer.question_index].question,
                "expected_points": quiz.open_questions[answer.question_index].expected_points,
                "evidence_timestamp": quiz.open_questions[answer.question_index].evidence_timestamp,
                "student_answer": answer.answer,
            }
            for answer in attempt.open_answers
        ]
        return """Evalúa las respuestas abiertas del estudiante exclusivamente con la evidencia recuperada.
Devuelve JSON con feedback. Para cada respuesta indica los puntos logrados y faltantes usando sólo
expected_points, ofrece una sugerencia breve y conserva exactamente el evidence_timestamp entregado.
Si la evidencia no basta, devuelve evidence_sufficient=false y una lista feedback vacía.

RESPUESTAS A EVALUAR:
""" + json.dumps(submitted, ensure_ascii=False)

    @staticmethod
    def _parse_open_feedback(
        raw_response: str,
        evidence: list[dict[str, Any]],
        expected_timestamps: dict[int, str],
    ) -> OpenFeedbackBatch:
        """Validate provider feedback against submitted indices and retrieved evidence."""
        try:
            result = OpenFeedbackBatch.model_validate_json(normalize_json_response(raw_response))
        except Exception as error:
            raise PipelineError(
                "Gemini devolvió una retroalimentación con estructura inválida.",
                code="INVALID_FEEDBACK_RESPONSE", status_code=502,
            ) from error
        received_indices = [item.question_index for item in result.feedback]
        if not result.evidence_sufficient:
            if result.feedback:
                raise PipelineError(
                    "La respuesta insuficiente de Gemini contiene retroalimentación no respaldada.",
                    code="INCONSISTENT_EVIDENCE_RESPONSE", status_code=502,
                )
            return result
        if set(received_indices) != set(expected_timestamps) or len(received_indices) != len(set(received_indices)):
            raise PipelineError(
                "Gemini no devolvió retroalimentación para las preguntas abiertas solicitadas.",
                code="FEEDBACK_COUNT_MISMATCH", status_code=502,
            )
        available_timestamps = {
            str(value)
            for item in evidence
            for value in (item.get("start"), item.get("end"))
            if value is not None
        }
        for item in result.feedback:
            if item.evidence_timestamp not in available_timestamps or item.evidence_timestamp != expected_timestamps[item.question_index]:
                raise PipelineError(
                    "La retroalimentación cita un timestamp no fundamentado.",
                    code="UNGROUNDED_TIMESTAMP", status_code=502,
                )
        return result
