"""Caso de uso RF-03: cuestionarios con taxonomía de Bloom."""


class QuizService:
    """Coordinate retrieval and Bloom-aligned question generation."""

    def generate(self, video_id: int, question_count: int, bloom_levels: list[str]) -> dict:
        """Create a questionnaire grounded in transcript evidence."""
        raise NotImplementedError

