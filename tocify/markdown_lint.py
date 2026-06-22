"""Post-generation markdown lint: run mdformat and update YAML lastmod/updated."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from tocify.frontmatter import split_frontmatter_and_body, with_frontmatter

_MDFORMAT_EXTENSIONS = ("frontmatter", "footnote")


def _run_mdformat(path: Path) -> bool:
    """Run mdformat on path with frontmatter and footnote extensions. Return True if run."""
    try:
        import mdformat
    except ImportError:
        return False
    try:
        mdformat.file(path, extensions=_MDFORMAT_EXTENSIONS)
    except (ValueError, OSError):
        return False
    return True


def _update_lastmod_in_content(content: str, today: str) -> str:
    """Set lastmod and updated in frontmatter to today; return new content."""
    frontmatter, body = split_frontmatter_and_body(content)
    if not frontmatter:
        return content
    frontmatter = dict(frontmatter)
    frontmatter["lastmod"] = today
    frontmatter["updated"] = today
    return with_frontmatter(body, frontmatter)


def lint_file(
    path: Path,
    *,
    update_lastmod: bool = True,
) -> None:
    """Format markdown at path with mdformat and set lastmod/updated in frontmatter.

    If mdformat or plugins are not installed, only the lastmod/updated step runs.
    If path does not exist or is not a file, no-op.
    """
    try:
        if not path.is_file():
            return
    except OSError:
        return

    content = path.read_text(encoding="utf-8")
    _run_mdformat(path)
    content = path.read_text(encoding="utf-8")

    if update_lastmod:
        today = dt.datetime.now(dt.timezone.utc).date().isoformat()
        updated = _update_lastmod_in_content(content, today)
        if updated != content:
            path.write_text(updated, encoding="utf-8")
