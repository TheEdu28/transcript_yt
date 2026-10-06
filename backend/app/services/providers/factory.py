"""Fábrica para resolver el ModelProvider activo y listar modelos dinámicamente."""

from __future__ import annotations

import logging

from app.core.config import Settings, get_settings
from app.core.errors import PipelineError
from app.services.providers.base import ModelProvider
from app.services.providers.gemini_provider import GeminiProvider
from app.services.providers.openai_provider import OpenAIProvider

logger = logging.getLogger(__name__)

# Modelos que no son útiles para generación de texto (embeddings, imagen, etc.)
_GEMINI_SKIP_PREFIXES = ("models/embedding", "models/aqa", "models/text-embedding")
_GROQ_SKIP_SUFFIXES = ("-whisper", "-vision")


def _fetch_gemini_models(api_key: str) -> list[dict]:
    """Consulta la API de Gemini y devuelve modelos de generación de texto."""
    try:
        import httpx
        resp = httpx.get(
            "https://generativelanguage.googleapis.com/v1beta/models",
            params={"key": api_key},
            timeout=8,
        )
        if resp.status_code == 429:
            return [{"quota_exhausted": True}]
        resp.raise_for_status()
        models = []
        for m in resp.json().get("models", []):
            name = m.get("name", "")
            if any(name.startswith(p) for p in _GEMINI_SKIP_PREFIXES):
                continue
            if "generateContent" not in m.get("supportedGenerationMethods", []):
                continue
            short = name.removeprefix("models/")
            models.append({"model_id": f"gemini/{short}", "label": m.get("displayName", short)})
        return models
    except Exception as exc:
        logger.warning("No se pudo obtener la lista de modelos de Gemini: %s", exc)
        return []


def _fetch_groq_models(api_key: str) -> list[dict]:
    """Consulta la API de Groq y devuelve modelos de chat activos."""
    try:
        import httpx
        resp = httpx.get(
            "https://api.groq.com/openai/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=8,
        )
        if resp.status_code == 429:
            return [{"quota_exhausted": True}]
        resp.raise_for_status()
        models = []
        for m in resp.json().get("data", []):
            mid = m.get("id", "")
            if any(mid.endswith(s) for s in _GROQ_SKIP_SUFFIXES):
                continue
            if m.get("object") != "model":
                continue
            models.append({"model_id": f"groq/{mid}", "label": mid})
        return models
    except Exception as exc:
        logger.warning("No se pudo obtener la lista de modelos de Groq: %s", exc)
        return []


def list_available_models(settings: Settings | None = None) -> dict:
    """Devuelve todos los modelos disponibles consultando las APIs dinámicamente.

    Devuelve un dict compatible con ``ModelsResponse``.
    """
    resolved = settings or get_settings()
    models: list[dict] = []
    quota_exhausted_providers: set[str] = set()

    # --- Gemini ---
    if resolved.gemini_api_key:
        gemini_models = _fetch_gemini_models(resolved.gemini_api_key)
        if gemini_models and gemini_models[0].get("quota_exhausted"):
            quota_exhausted_providers.add("gemini")
            models.append({
                "model_id": f"gemini/{resolved.gemini_model}",
                "provider": "gemini",
                "label": resolved.gemini_model,
                "available": True,
                "quota_exhausted": True,
                "is_default": False,
            })
        else:
            for m in gemini_models:
                models.append({**m, "provider": "gemini", "available": True,
                                "quota_exhausted": False, "is_default": False})
    else:
        models.append({
            "model_id": f"gemini/{resolved.gemini_model}",
            "provider": "gemini",
            "label": resolved.gemini_model,
            "available": False,
            "quota_exhausted": False,
            "is_default": False,
        })

    # --- Groq ---
    if resolved.groq_api_key:
        groq_models = _fetch_groq_models(resolved.groq_api_key)
        if groq_models and groq_models[0].get("quota_exhausted"):
            quota_exhausted_providers.add("groq")
            models.append({
                "model_id": f"groq/{resolved.groq_model}",
                "provider": "groq",
                "label": resolved.groq_model,
                "available": True,
                "quota_exhausted": True,
                "is_default": False,
            })
        else:
            for m in groq_models:
                models.append({**m, "provider": "groq", "available": True,
                                "quota_exhausted": False, "is_default": False})
    else:
        models.append({
            "model_id": f"groq/{resolved.groq_model}",
            "provider": "groq",
            "label": resolved.groq_model,
            "available": False,
            "quota_exhausted": False,
            "is_default": False,
        })

    # Determinar modelo predeterminado
    default_id = resolved.active_model_id or f"{resolved.active_model_provider}/{resolved.gemini_model if resolved.active_model_provider == 'gemini' else resolved.groq_model}"
    # Si el default configurado existe en la lista, marcarlo; si no, usar el primero disponible
    default_exists = any(m["model_id"] == default_id for m in models)
    if not default_exists:
        available = [m for m in models if m["available"] and not m["quota_exhausted"]]
        default_id = available[0]["model_id"] if available else (models[0]["model_id"] if models else "")

    for m in models:
        m["is_default"] = m["model_id"] == default_id

    return {"models": models, "default_model_id": default_id}


def _parse_model_id(model_id: str) -> tuple[str, str]:
    """Extrae (provider, model_name) de un model_id con formato 'provider/model'."""
    if "/" in model_id:
        provider, _, model_name = model_id.partition("/")
        return provider.strip().lower(), model_name.strip()
    return model_id.strip().lower(), model_id.strip()


def get_model_provider(
    settings: Settings | None = None,
    *,
    provider_name: str | None = None,
    model_id: str | None = None,
) -> ModelProvider:
    """Devuelve la instancia de ModelProvider para el model_id o provider_name dado."""
    resolved_settings = settings or get_settings()

    if model_id:
        provider, model_name = _parse_model_id(model_id)
    else:
        provider = (provider_name or resolved_settings.active_model_provider or "gemini").strip().lower()
        model_name = None

    if provider == "gemini":
        if model_name:
            # Clonar settings con el modelo específico sin mutar el singleton
            import copy
            s = copy.copy(resolved_settings)
            object.__setattr__(s, "gemini_model", model_name) if hasattr(s, "__dict__") else None
            try:
                s.gemini_model = model_name  # type: ignore[misc]
            except Exception:
                pass
        return GeminiProvider(resolved_settings if not model_name else _settings_with(resolved_settings, gemini_model=model_name))
    elif provider in {"openai", "chatgpt"}:
        return OpenAIProvider(resolved_settings if not model_name else _settings_with(resolved_settings, openai_model=model_name))
    elif provider == "groq":
        from app.services.providers.groq_provider import GroqProvider
        return GroqProvider(resolved_settings if not model_name else _settings_with(resolved_settings, groq_model=model_name))
    else:
        raise PipelineError(
            f"Proveedor '{provider}' no soportado. Valores válidos: 'gemini', 'openai', 'groq'.",
            code="UNKNOWN_MODEL_PROVIDER",
            status_code=400,
        )


def _settings_with(settings: Settings, **overrides) -> Settings:
    """Devuelve una copia de Settings con los campos sobreescritos."""
    data = settings.model_dump()
    data.update(overrides)
    return Settings(**data)


# Alias de compatibilidad para código existente
def list_available_providers(settings: Settings | None = None) -> dict:
    result = list_available_models(settings)
    # Construir la forma antigua que esperan tests existentes
    seen: dict[str, dict] = {}
    for m in result["models"]:
        p = m["provider"]
        if p not in seen:
            seen[p] = {"name": p, "label": p.capitalize(), "available": m["available"], "model": m["label"]}
    active = (settings or get_settings()).active_model_provider or "gemini"
    return {"providers": list(seen.values()), "active_provider": active}
