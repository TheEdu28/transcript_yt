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
        evidence = self._retrieve_evidence_for_attempt(material.video_id, quiz, attempt)
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

    def _retrieve_evidence_for_attempt(
        self,
        video_id: int,
        quiz: QuizResponse,
        attempt: FeedbackRequest,
    ) -> list[dict[str, Any]]:
        """Recupera la evidencia asegurando que incluya los fragmentos de cada pregunta abierta."""
        chunks_by_index: dict[int, dict[str, Any]] = {}
        if hasattr(self.vectors, "collection") and self.vectors.collection is not None:
            try:
                all_video_data = self.vectors.collection.get(where={"video_id": video_id})
                metadatas = all_video_data.get("metadatas") or []
                documents = all_video_data.get("documents") or []
                for doc, meta in zip(documents, metadatas):
                    chunk_idx = meta.get("chunk_index")
                    if chunk_idx is not None:
                        chunks_by_index[chunk_idx] = {
                            "chunk_index": chunk_idx,
                            "text": doc,
                            "start": meta.get("start"),
                            "end": meta.get("end"),
                        }
            except Exception:
                pass

        selected_chunks: dict[int, dict[str, Any]] = {}

        # 1. Incluir explícitamente los chunks que coinciden con los timestamps de las preguntas enviadas
        for ans in attempt.open_answers:
            if ans.question_index < len(quiz.open_questions):
                ts = quiz.open_questions[ans.question_index].evidence_timestamp
                matched = [
                    c for c in chunks_by_index.values()
                    if c.get("start") == ts or c.get("end") == ts or (
                        c.get("start") and c.get("end") and c["start"] <= ts <= c["end"]
                    )
                ]
                for c in matched:
                    selected_chunks[c["chunk_index"]] = c

        # 2. Búsqueda semántica por cada pregunta
        for ans in attempt.open_answers:
            if ans.question_index < len(quiz.open_questions):
                q = quiz.open_questions[ans.question_index]
                q_query = f"{q.question} {' '.join(q.expected_points)}"
                try:
                    sem_evidence = self.vectors.retrieve(video_id, q_query)
                    for item in sem_evidence:
                        idx = item.get("chunk_index")
                        if idx is not None:
                            if idx not in selected_chunks:
                                selected_chunks[idx] = item
                        else:
                            selected_chunks[len(selected_chunks)] = item
                except Exception:
                    pass

        # Si aún está vacío (o en tests unitarios simples), usar retrieve general
        if not selected_chunks:
            prompt = self._open_feedback_prompt(quiz, attempt)
            return self.vectors.retrieve(video_id, prompt)

        return [selected_chunks[k] for k in sorted(selected_chunks.keys())]

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
            ts = item.evidence_timestamp
            ts_matched = (
                ts in available_timestamps
                or any(
                    e.get("start") and e.get("end") and str(e["start"]) <= ts <= str(e["end"])
                    for e in evidence
                )
            )
            if not ts_matched or ts != expected_timestamps[item.question_index]:
                raise PipelineError(
                    "La retroalimentación cita un timestamp no fundamentado.",
                    code="UNGROUNDED_TIMESTAMP", status_code=502,
                )
        return result
