"""Puerto para embeddings y ChromaDB local."""


class VectorStoreService:
    """Index and retrieve transcript chunks for grounded generation."""

    def index_transcript(self, video_id: int, chunks: list[str]) -> None:
        """Embed and persist transcript chunks in ChromaDB."""
        raise NotImplementedError

    def retrieve(self, query: str, limit: int) -> list[dict]:
        """Retrieve semantically relevant chunks for a RAG prompt."""
        raise NotImplementedError

