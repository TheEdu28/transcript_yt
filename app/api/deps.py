"""Dependencias reutilizables de FastAPI."""


def get_request_context() -> dict[str, str]:
    """Return request-scoped context when authentication is introduced."""
    return {}

