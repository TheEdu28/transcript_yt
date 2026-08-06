"""Puerto para generación con Gemini API."""


class GeminiService:
    """Generate structured text from retrieved transcript context."""

    def generate_structured(self, prompt: str, context: list[dict]) -> dict:
        """Call Gemini and validate its structured response in a later iteration."""
        raise NotImplementedError

