"""Adaptador de búsqueda y obtención de metadatos de YouTube."""


class YouTubeService:
    """Implement video search and metadata retrieval in a future increment."""

    def search(self, keywords: str, max_results: int) -> list[dict]:
        """Search videos through YouTube Data API v3."""
        raise NotImplementedError

    def fetch_metadata(self, video_url: str) -> dict:
        """Obtain metadata needed before ingestion."""
        raise NotImplementedError

