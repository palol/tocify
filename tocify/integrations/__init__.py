"""Triage backends by architecture. Dispatch via TOCIFY_BACKEND; add new backends by registering here."""

import os


def _openai_backend():
    from tocify.integrations import openai_triage

    client = openai_triage.make_openai_client()
    return lambda interests, items: openai_triage.call_openai_triage(client, interests, items)


def _cursor_backend():
    from tocify.integrations import cursor_cli

    if not cursor_cli.is_available():
        raise RuntimeError("Cursor backend requested but CURSOR_API_KEY is not set.")
    return cursor_cli.call_cursor_triage


def _gemini_backend():
    from tocify.integrations import gemini_triage

    if not gemini_triage.is_available():
        raise RuntimeError("Gemini backend requested but GEMINI_API_KEY is not set.")
    client = gemini_triage.make_gemini_client()
    return lambda interests, items: gemini_triage.call_gemini_triage(client, interests, items)


# Registry: TOCIFY_BACKEND value -> callable that returns (interests, items) -> dict
_BACKENDS = {
    "openai": _openai_backend,
    "cursor": _cursor_backend,
    "gemini": _gemini_backend,
}

_MODEL_ENV_DEFAULTS = {
    "openai": ("OPENAI_MODEL", "gpt-4o"),
    "cursor": ("CURSOR_MODEL", "unknown"),
    "gemini": ("GEMINI_MODEL", "gemini-2.0-flash"),
}


def _resolve_backend_name() -> str:
    backend = os.getenv("TOCIFY_BACKEND", "").strip().lower()
    if not backend:
        backend = "cursor" if os.getenv("CURSOR_API_KEY", "").strip() else "openai"
    if backend not in _BACKENDS:
        raise RuntimeError(
            f"Unknown TOCIFY_BACKEND={backend!r}. Known: {list(_BACKENDS)}. "
            "Set OPENAI_API_KEY, CURSOR_API_KEY, or GEMINI_API_KEY for default backend, or force TOCIFY_BACKEND=openai|cursor|gemini."
        )
    return backend


def resolve_backend_name() -> str:
    """Single source of truth for backend selection. Used by integrations and runner (vault)."""
    return _resolve_backend_name()


def get_triage_runtime_metadata() -> dict[str, str]:
    backend = _resolve_backend_name()
    model_env, default_model = _MODEL_ENV_DEFAULTS[backend]
    model = os.getenv(model_env, "").strip() or default_model
    return {"triage_backend": backend, "triage_model": model}


def get_triage_backend_with_metadata():
    metadata = get_triage_runtime_metadata()
    backend = metadata["triage_backend"]
    return _BACKENDS[backend](), metadata


def get_triage_backend():
    """Return a callable (interests, items) -> dict with keys notes, ranked (and optionally week_of)."""
    triage_fn, _ = get_triage_backend_with_metadata()
    return triage_fn
