"""Servicio de base de datos vectorial ChromaDB y generación de embeddings locales."""

from __future__ import annotations

from typing import Any

from app.core.config import Settings
from app.services.ingestion.chunker import TranscriptChunk


def timestamp(seconds: float) -> str:
    """Formatea segundos como HH:MM:SS para metadatos de Chroma."""
    total = max(0, round(seconds))
    return f"{total // 3600:02d}:{(total % 3600) // 60:02d}:{total % 60:02d}"


class VectorStoreService:
    """Embeddings locales con sentence-transformers y colección Chroma persistente."""

    _embedder: Any = None

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        import chromadb
        from chromadb.config import Settings as ChromaSettings

        try:
            import chromadb.telemetry.product.posthog as chroma_ph
            chroma_ph.Posthog.capture = lambda self, event: None  # type: ignore[assignment]
        except Exception:
            pass

        self.client = chromadb.PersistentClient(
            path=str(settings.chroma_persist_directory),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self.collection = self.client.get_or_create_collection(
            name=settings.chroma_collection_name, metadata={"hnsw:space": "cosine"},
        )

    def _encoder(self) -> Any:
        if self._embedder is None:
            from sentence_transformers import SentenceTransformer

            try:
                self._embedder = SentenceTransformer(self.settings.embedding_model, local_files_only=True)
            except Exception:
                self._embedder = SentenceTransformer(self.settings.embedding_model)
        return self._embedder

    def index(self, video_id: int, chunks: list[TranscriptChunk]) -> None:
        """Genera vectores localmente y reemplaza índices repetidos de forma idempotente."""
        documents = [chunk.text for chunk in chunks]
        embeddings = self._encoder().encode(documents, normalize_embeddings=True).tolist()
        self.collection.upsert(
            ids=[f"{video_id}:{chunk.index}" for chunk in chunks],
            documents=documents,
            embeddings=embeddings,
            metadatas=[
                {
                    "video_id": video_id,
                    "chunk_index": chunk.index,
                    "start": timestamp(chunk.start),
                    "end": timestamp(chunk.end),
                }
                for chunk in chunks
            ],
        )

    def retrieve(self, video_id: int, query: str) -> list[dict[str, Any]]:
        """Recupera los chunks más afines al query."""
        available = len(self.collection.get(where={"video_id": video_id}, include=[]).get("ids", []))
        if available == 0:
            return []
        query_vector = self._encoder().encode([query], normalize_embeddings=True).tolist()
        results = self.collection.query(
            query_embeddings=query_vector,
            n_results=min(self.settings.rag_retrieval_limit, available),
            where={"video_id": video_id},
        )
        records: list[dict[str, Any]] = []
        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]
        for document, metadata, distance in zip(documents, metadatas, distances):
            records.append({
                "chunk_index": metadata.get("chunk_index"),
                "text": document,
                "start": metadata.get("start"),
                "end": metadata.get("end"),
                "distance": distance,
            })
        records.sort(key=lambda r: (r.get("chunk_index") if r.get("chunk_index") is not None else 0))
        return records

    def delete_by_video(self, video_id: int) -> None:
        """Elimina todos los vectores asociados a un video_id."""
        matching = self.collection.get(where={"video_id": video_id}, include=[])
        ids = matching.get("ids", [])
        if ids:
            self.collection.delete(ids=ids)
