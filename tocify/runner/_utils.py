"""Shared runner helpers."""


def string_list(value) -> list[str]:
    """Normalize a value to a list of non-empty stripped strings; non-lists become []."""
    if not isinstance(value, list):
        return []
    return [str(v).strip() for v in value if str(v).strip()]
