"""Lógica de calificación, penalización por reintentos y evaluación con IA."""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import PipelineError
from app.schemas.contracts import (
    AttemptSubmitRequest,
    OpenAnswer,
    OpenQuestionEvaluation,
    OpenQuestionsEvaluationBatch,
    QuizResponse,
)
from app.services.material_service import MaterialService
from app.services.pipeline import GeminiService, VectorStoreService, normalize_json_response

logger = logging.getLogger(__name__)


def compute_final_score(raw_score: float, attempt_number: int, penalty_per_attempt: float = 10.0) -> float:
    """Calcula el puntaje final aplicando penalización progresiva en reintentos.

    Reglas de negocio:
    - attempt_number == 1: final_score = raw_score (sin penalización).
    - attempt_number >= 2: final_score = max(0.0, raw_score - penalty_per_attempt * (attempt_number - 1)).

    Args:
        raw_score: Calificación base entre 0.0 y 100.0.
        attempt_number: Número de intento (>= 1).
        penalty_per_attempt: Puntos a descontar por reintento.

    Returns:
        float: Puntaje final redondeado a 2 decimales, acotado entre 0.0 y 100.0.
    """
    if attempt_number < 1:
        raise ValueError("attempt_number debe ser >= 1")

    clamped_raw = max(0.0, min(100.0, float(raw_score)))
    if attempt_number == 1:
        return round(clamped_raw, 2)

    penalty = penalty_per_attempt * (attempt_number - 1)
    return round(max(0.0, clamped_raw - penalty), 2)


def compute_quiz_raw_score(
    multiple_choice_correct_count: int,
    open_scores: list[float],
    total_mc_questions: int,
    total_open_questions: int,
) -> float:
    """Calcula el raw_score (0.0 a 100.0) combinando opción múltiple y preguntas abiertas."""
    total_questions = total_mc_questions + total_open_questions
    if total_questions == 0:
        return 0.0

    mc_points = float(multiple_choice_correct_count)
    open_points = sum(max(0.0, min(1.0, float(s))) for s in open_scores)

    raw = ((mc_points + open_points) / total_questions) * 100.0
    return round(max(0.0, min(100.0, raw)), 2)


def evaluate_quiz_answers(quiz_content: dict, user_answers: list[dict]) -> float:
    """Compara las respuestas seleccionadas contra correct_option del quiz.

    Devuelve un raw_score entre 0.0 y 100.0.
    """
    questions = quiz_content.get("multiple_choice", [])
    if not questions:
        return 0.0

    answers_map = {ans["question_index"]: ans["selected_option"] for ans in user_answers}
    correct_count = 0

    for idx, q in enumerate(questions):
        selected = answers_map.get(idx)
        if selected is not None and selected == q.get("correct_option"):
            correct_count += 1

    return round((correct_count / len(questions)) * 100.0, 2)


def compute_member_topic_summary(
    user_id: int, user_name: str, user_email: str, attempts: list
) -> dict:
    """Calcula el resumen de un miembro: mejor intento, último intento y promedios.

    Args:
        user_id: ID del usuario.
        user_name: Nombre del usuario.
        user_email: Email del usuario.
        attempts: Lista de objetos Attempt del usuario ordenados por attempt_number asc.

    Returns:
        dict compatible con MemberTopicSummary.
    """
    if not attempts:
        return {
            "user_id": user_id,
            "user_name": user_name,
            "user_email": user_email,
            "total_attempts": 0,
            "best_attempt": None,
            "latest_attempt": None,
            "average_final_score": None,
            "average_raw_score": None,
        }

    total = len(attempts)
    best_attempt = max(attempts, key=lambda a: (a.final_score, a.raw_score))
    latest_attempt = max(attempts, key=lambda a: a.attempt_number)

    avg_final = round(sum(a.final_score for a in attempts) / total, 2)
    avg_raw = round(sum(a.raw_score for a in attempts) / total, 2)

    return {
        "user_id": user_id,
        "user_name": user_name,
        "user_email": user_email,
        "total_attempts": total,
        "best_attempt": best_attempt,
        "latest_attempt": latest_attempt,
        "average_final_score": avg_final,
        "average_raw_score": avg_raw,
    }


class AttemptEvaluationResult:
    """Resultado estructurado de la evaluación de un intento."""

    def __init__(
        self,
        raw_score: float,
        answers_snapshot: dict[str, Any],
        open_evaluations: list[OpenQuestionEvaluation] | None = None,
        mc_feedback: list[dict[str, Any]] | None = None,
    ) -> None:
        self.raw_score = raw_score
        self.answers_snapshot = answers_snapshot
        self.open_evaluations = open_evaluations or []
        self.mc_feedback = mc_feedback or []


class QuizAttemptGradingService:
    """Evalúa intentos de temas/cuestionarios combinando lógica determinista y LLM grounded."""

    def __init__(
        self,
        settings: Settings | None = None,
        materials: MaterialService | None = None,
        vectors: VectorStoreService | None = None,
        gemini: GeminiService | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.materials = materials or MaterialService()
        self.vectors = vectors or VectorStoreService(self.settings)
        self.gemini = gemini or GeminiService(self.settings)

    def grade_submission(
        self,
        session: Session,
        material_id: int,
        submission: AttemptSubmitRequest,
    ) -> AttemptEvaluationResult:
        """Evalúa las respuestas de opción múltiple y abiertas, devolviendo el raw_score y feedback."""
        material = self.materials.get(session, material_id)
        if material.material_type != "quiz":
            raise PipelineError(
                "La evaluación sólo está disponible para cuestionarios.",
                code="MATERIAL_NOT_QUIZ",
                status_code=400,
            )

        quiz = QuizResponse.model_validate(material.content)
        self._validate_indices(quiz, submission)

        # 1. Evaluación determinista de opción múltiple
        mc_correct_count = 0
        mc_feedback: list[dict[str, Any]] = []
        user_mc_map = {a.question_index: a.selected_option for a in submission.multiple_choice_answers}

        for idx, q in enumerate(quiz.multiple_choice):
            selected = user_mc_map.get(idx)
            is_correct = selected is not None and selected == q.correct_option
            if is_correct:
                mc_correct_count += 1
            mc_feedback.append({
                "question_index": idx,
                "selected_option": selected,
                "is_correct": is_correct,
                "explanation": q.explanation,
                "evidence_timestamp": q.evidence_timestamp,
            })

        # 2. Evaluación de preguntas abiertas
        open_evaluations: list[OpenQuestionEvaluation] = []
        open_scores: list[float] = []

        if quiz.open_questions and submission.open_answers:
            open_evaluations = self._evaluate_open_answers(
                video_id=material.video_id,
                quiz=quiz,
                open_answers=submission.open_answers,
            )
            eval_map = {e.question_index: e for e in open_evaluations}
            for idx in range(len(quiz.open_questions)):
                evaluation = eval_map.get(idx)
                open_scores.append(evaluation.score if evaluation else 0.0)
        elif quiz.open_questions:
            # Hay preguntas abiertas en el cuestionario pero el estudiante no envió respuestas abiertas
            open_scores = [0.0] * len(quiz.open_questions)

        # 3. Cálculo de raw_score normalizado (0.0 a 100.0)
        total_mc = len(quiz.multiple_choice)
        total_open = len(quiz.open_questions)
        raw_score = compute_quiz_raw_score(
            multiple_choice_correct_count=mc_correct_count,
            open_scores=open_scores,
            total_mc_questions=total_mc,
            total_open_questions=total_open,
        )

        open_snapshot = []
        user_open_map = {a.question_index: a.answer for a in submission.open_answers}
        eval_map = {e.question_index: e for e in open_evaluations}
        for idx in range(len(quiz.open_questions)):
            evaluation = eval_map.get(idx)
            open_snapshot.append({
                "question_index": idx,
                "student_answer": user_open_map.get(idx, ""),
                "score": evaluation.score if evaluation else 0.0,
                "is_correct": evaluation.is_correct if evaluation else False,
                "feedback_text": evaluation.feedback_text if evaluation else "Sin respuesta enviada.",
                "missing_points": evaluation.missing_points if evaluation else quiz.open_questions[idx].expected_points,
            })

        answers_snapshot = {
            "multiple_choice": mc_feedback,
            "open_questions": open_snapshot,
        }

        return AttemptEvaluationResult(
            raw_score=raw_score,
            answers_snapshot=answers_snapshot,
            open_evaluations=open_evaluations,
            mc_feedback=mc_feedback,
        )

    def _evaluate_open_answers(
        self,
        video_id: int,
        quiz: QuizResponse,
        open_answers: list[OpenAnswer],
    ) -> list[OpenQuestionEvaluation]:
        """Recupera evidencia textual grounded de ChromaDB y evalúa con Gemini."""
        submitted = [
            {
                "question_index": answer.question_index,
                "question": quiz.open_questions[answer.question_index].question,
                "expected_points": quiz.open_questions[answer.question_index].expected_points,
                "evidence_timestamp": quiz.open_questions[answer.question_index].evidence_timestamp,
                "student_answer": answer.answer,
            }
            for answer in open_answers
        ]

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

        for ans in open_answers:
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

        for ans in open_answers:
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

        evidence = [selected_chunks[k] for k in sorted(selected_chunks.keys())]
        if not evidence:
            query = " \n ".join(
                f"{quiz.open_questions[a.question_index].question} {' '.join(quiz.open_questions[a.question_index].expected_points)}"
                for a in open_answers
            )
            evidence = self.vectors.retrieve(video_id, query)

        if not evidence:
            raise PipelineError(
                "No se pudo recuperar la evidencia necesaria para calificar las preguntas abiertas.",
                code="NO_EVALUATION_EVIDENCE",
                status_code=422,
            )

        prompt = (
            "Eres un evaluador académico riguroso en un sistema RAG educativo.\n"
            "Tu tarea es calificar las respuestas abiertas de los estudiantes utilizando EXCLUSIVAMENTE "
            "la información explícita provista en la sección EVIDENCIA RECUPERADA.\n\n"
            "REGLAS DE EVALUACIÓN Y GROUNDEDNESS:\n"
            "1. PROHIBIDO USAR CONOCIMIENTO EXTERNO: No asumas ni uses conceptos que no estén en la evidencia provista.\n"
            "2. CRITERIO DE PUNTUACIÓN (score de 0.0 a 1.0):\n"
            "   - 1.0: La respuesta es precisa, completa y respaldada por la evidencia.\n"
            "   - 0.5 a 0.8: La respuesta es parcialmente correcta según la evidencia, pero omitió ideas clave.\n"
            "   - 0.1 a 0.4: La respuesta es vaga, imprecisa o contiene afirmaciones no respaldadas.\n"
            "   - 0.0: La respuesta es incorrecta, vacía o contradictoria con la evidencia.\n"
            "3. SUFICIENCIA (is_correct): Asigna true si y solo si score >= 0.7; de lo contrario false.\n"
            "4. RETROALIMENTACIÓN (feedback_text): Breve explicación pedagógica contrastando con la evidencia provista.\n"
            "5. PUNTOS FALTANTES (missing_points): Lista de conceptos clave de la evidencia que faltaron. Si score es 1.0, lista vacía.\n\n"
            "PREGUNTAS Y RESPUESTAS A EVALUAR:\n"
            f"{json.dumps(submitted, ensure_ascii=False)}"
        )

        raw_response = self.gemini.generate_json(
            task=prompt,
            evidence=evidence,
            response_schema=OpenQuestionsEvaluationBatch,
        )

        try:
            batch = OpenQuestionsEvaluationBatch.model_validate_json(normalize_json_response(raw_response))
        except Exception as error:
            logger.error("Error al validar respuesta estructurada de Gemini: %s", error)
            raise PipelineError(
                "Gemini devolvió una evaluación con formato inválido.",
                code="INVALID_EVALUATION_RESPONSE",
                status_code=502,
            ) from error

        if not batch.evidence_sufficient:
            raise PipelineError(
                batch.insufficiency_note or "La evidencia recuperada no es suficiente para calificar.",
                code="INSUFFICIENT_EVIDENCE_FOR_GRADING",
                status_code=422,
            )

        expected_indices = {a.question_index for a in open_answers}
        received_indices = {item.question_index for item in batch.evaluations}
        if expected_indices != received_indices:
            raise PipelineError(
                "Gemini no devolvió la calificación de todas las preguntas abiertas enviadas.",
                code="EVALUATION_COUNT_MISMATCH",
                status_code=502,
            )

        for item in batch.evaluations:
            item.score = round(max(0.0, min(1.0, float(item.score))), 2)

        return batch.evaluations

    @staticmethod
    def _validate_indices(quiz: QuizResponse, submission: AttemptSubmitRequest) -> None:
        """Rechaza duplicados o índices fuera de rango antes de evaluar."""
        mc_indices = [a.question_index for a in submission.multiple_choice_answers]
        open_indices = [a.question_index for a in getattr(submission, "open_answers", [])]

        if len(set(mc_indices)) != len(mc_indices) or len(set(open_indices)) != len(open_indices):
            raise PipelineError(
                "No se puede responder dos veces la misma pregunta.",
                code="DUPLICATE_ANSWER_INDEX",
                status_code=400,
            )

        if any(idx >= len(quiz.multiple_choice) for idx in mc_indices):
            raise PipelineError(
                "El índice de una respuesta de opción múltiple no existe en el cuestionario.",
                code="UNKNOWN_MC_INDEX",
                status_code=400,
            )

        if any(idx >= len(quiz.open_questions) for idx in open_indices):
            raise PipelineError(
                "El índice de una respuesta abierta no existe en el cuestionario.",
                code="UNKNOWN_OPEN_INDEX",
                status_code=400,
            )
