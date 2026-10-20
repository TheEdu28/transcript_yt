"""Fábrica para resolver el ModelProvider activo y listar modelos dinámicamente."""

from __future__ import annotations

import logging
import re

from app.core.config import Settings, get_settings
from app.core.errors import PipelineError
from app.services.providers.base import ModelProvider
from app.services.providers.gemini_provider import GeminiProvider
from app.services.providers.openai_provider import OpenAIProvider

logger = logging.getLogger(__name__)

# Modelos que no son útiles para generación didáctica (embeddings, imagen, tts, etc.)
_GEMINI_SKIP_KEYWORDS = (
    "embedding", "aqa", "antigravity", "deep-research", "tts", "image",
    "audio", "lyria", "robotics", "computer-use", "transcribe", "banana"
)
_GROQ_SKIP_SUFFIXES = ("-whisper", "-vision")
_NVIDIA_SKIP_KEYWORDS = ("embed", "clip", "detector", "reward", "guard", "calibration")


def _is_valid_gemini_content_model(name: str) -> bool:
    """Filtra modelos de Gemini: solo texto para generación de contenido y versión >= 3.5."""
    short = name.removeprefix("models/").lower()

    # Debe ser de la familia gemini o gemma
    if not (short.startswith("gemini-") or short.startswith("gemma-")):
        return False

    # Excluir palabras clave de modelos especializados o no aptos para generar texto
    if any(kw in short for kw in _GEMINI_SKIP_KEYWORDS):
        return False

    # Mantener alias latest (ej: gemini-flash-latest, gemini-pro-latest)
    if "latest" in short:
        return True

    # Verificar versión numérica >= 3.5 para gemini
    match_gemini = re.search(r"gemini-(\d+(?:\.\d+)?)", short)
    if match_gemini:
        try:
            return float(match_gemini.group(1)) >= 3.5
        except ValueError:
            return False

    # Verificar versión numérica >= 3.5 para gemma
    match_gemma = re.search(r"gemma-(\d+(?:\.\d+)?)", short)
    if match_gemma:
        try:
            return float(match_gemma.group(1)) >= 3.5
        except ValueError:
            return False

    return False


def _fetch_gemini_models(api_key: str) -> list[dict]:
    """Consulta la API de Gemini y devuelve modelos de generación de texto >= 3.5."""
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
            if "generateContent" not in m.get("supportedGenerationMethods", []):
                continue
            if not _is_valid_gemini_content_model(name):
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


# Modelos de generación de contenido activos en NVIDIA NIM (excluyendo funciones retiradas 404/410)
_NVIDIA_ACTIVE_MODELS: dict[str, str] = {
    "deepseek-ai/deepseek-v4.1-flash": "DeepSeek V4.1 Flash (deepseek-ai/deepseek-v4.1-flash)",
    "google/gemma-4-31b-it": "Gemma 4 31B IT (google/gemma-4-31b-it)",
    "nvidia/nemotron-3.5-lightning-30b-a3b": "Nemotron 3.5 Lightning 30B",
    "meta/llama-3.2-11b-vision-instruct": "Llama 3.2 11B Instruct",
    "openai/gpt-oss-20b": "GPT-OSS 20B (openai/gpt-oss-20b)",
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning": "Nemotron 3 Nano 30B",
    "nvidia/nemotron-3-super-120b-a12b": "Nemotron 3 Super 120B",
}


def _fetch_nvidia_models(api_key: str, base_url: str | None = None) -> list[dict]:
    """Consulta la API de NVIDIA NIM y devuelve únicamente los modelos activos de generación."""
    url = (base_url or "https://integrate.api.nvidia.com/v1").rstrip("/") + "/models"
    try:
        import httpx
        resp = httpx.get(
            url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=8,
        )
        if resp.status_code == 429:
            return [{"quota_exhausted": True}]
        resp.raise_for_status()
        raw_ids = {m.get("id", "") for m in resp.json().get("data", [])}

        models = []
        for mid, label in _NVIDIA_ACTIVE_MODELS.items():
            if not raw_ids or mid in raw_ids:
                models.append({"model_id": f"nvidia/{mid}", "label": label})
        return models
    except Exception as exc:
        logger.warning("No se pudo obtener la lista de modelos de NVIDIA NIM: %s", exc)
        return [
            {"model_id": f"nvidia/{mid}", "label": label}
            for mid, label in _NVIDIA_ACTIVE_MODELS.items()
        ]


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

    # --- NVIDIA NIM ---
    if resolved.nvidia_api_key:
        nvidia_models = _fetch_nvidia_models(resolved.nvidia_api_key, resolved.nvidia_base_url)
        if nvidia_models and nvidia_models[0].get("quota_exhausted"):
            quota_exhausted_providers.add("nvidia")
            models.append({
                "model_id": f"nvidia/{resolved.nvidia_model}",
                "provider": "nvidia",
                "label": resolved.nvidia_model,
                "available": True,
                "quota_exhausted": True,
                "is_default": False,
            })
        else:
            for m in nvidia_models:
                models.append({**m, "provider": "nvidia", "available": True,
                                "quota_exhausted": False, "is_default": False})
    else:
        models.append({
            "model_id": f"nvidia/{resolved.nvidia_model}",
            "provider": "nvidia",
            "label": resolved.nvidia_model,
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
    elif provider in {"nvidia", "nvidia-nim", "nim"}:
        from app.services.providers.nvidia_provider import NvidiaProvider
        return NvidiaProvider(resolved_settings if not model_name else _settings_with(resolved_settings, nvidia_model=model_name))
    else:
        raise PipelineError(
            f"Proveedor '{provider}' no soportado. Valores válidos: 'gemini', 'openai', 'groq', 'nvidia'.",
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
