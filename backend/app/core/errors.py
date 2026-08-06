"""Errores de dominio traducibles a respuestas HTTP seguras."""


class PipelineError(Exception):
    """A known processing failure, with an API-safe code and HTTP status."""

    def __init__(self, message: str, *, code: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code

