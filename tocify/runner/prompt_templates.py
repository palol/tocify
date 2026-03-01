"""Load runner prompts from vault config or bundled templates (gardener, monthly, annual)."""

from __future__ import annotations

import importlib.resources
from pathlib import Path


def load_prompt_template(basename: str, path: Path | None = None) -> str:
    """Load prompt text from path if it exists, else from bundled tocify/templates/<basename>.

    Same pattern as frontmatter default_note_frontmatter: vault override then bundled default.
    """
    if path is not None and path.exists():
        return path.read_text(encoding="utf-8")
    return _load_bundled_prompt(basename)


def _load_bundled_prompt(basename: str) -> str:
    """Load prompt from package tocify/templates/<basename>; fallback for dev layout."""
    try:
        ref = importlib.resources.files("tocify").joinpath("templates", basename)
        return ref.read_text(encoding="utf-8")
    except Exception:
        p = Path(__file__).resolve().parent.parent / "templates" / basename
        if p.exists():
            return p.read_text(encoding="utf-8")
        raise FileNotFoundError(f"Bundled prompt not found: tocify/templates/{basename}") from None
