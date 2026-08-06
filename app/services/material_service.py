"""Caso de uso RF-02: construcción de material didáctico."""


class MaterialService:
    """Coordinate RAG retrieval and three-layer material generation."""

    def generate(self, video_id: int, target_level: str) -> dict:
        """Create synopsis, glossary and didactic blocks grounded in a transcript."""
        raise NotImplementedError

