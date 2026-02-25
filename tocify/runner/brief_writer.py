"""Weekly brief rendering and link-canonicalization helpers."""

from __future__ import annotations

import importlib.util
import re
from datetime import datetime, timezone
from pathlib import Path

from tocify.frontmatter import aggregate_ranked_item_tags, normalize_ai_tags, with_frontmatter
from tocify.runner._utils import string_list as _string_list
from tocify.runner.link_hygiene import build_allowed_url_index, is_valid_http_url


def weekly_brief_title(topic: str, week_of: str) -> str:
    """Canonical title for a weekly brief (body H1 and frontmatter)."""
    return f"{topic.upper()} Weekly Brief (week of {week_of})"


def _weekly_date_created_utc(week_of: str) -> str:
    """Return logical 'date created' for weekly brief: Monday of that ISO week 00:00 UTC (YYYY-MM-DD HH:MM:SS)."""
    return f"{week_of} 00:00:00"


def render_brief_md(
    result: dict,
    items_by_id: dict[str, dict],
    kept: list[dict],
    topic: str,
    *,
    min_score_read: float,
    title_override: str | None = None,
) -> str:
    """Render triage result and kept items to weekly brief markdown with frontmatter.

    If title_override is set (e.g. brief_path.stem), frontmatter title uses it; body H1 stays human-readable.
    """
    week_of = result["week_of"]
    notes = result.get("notes", "").strip()
    ranked = result.get("ranked", [])
    today = datetime.now(timezone.utc).date().isoformat()
    display_title = weekly_brief_title(topic, week_of)
    frontmatter_title = title_override if title_override is not None else display_title
    triage_backend = str(result.get("triage_backend") or "unknown")
    triage_model = str(result.get("triage_model") or "unknown")

    lines = [f"# {display_title}", ""]
    if notes:
        lines += [notes, ""]
    lines += [
        f"**Included:** {len(kept)} (score ≥ {min_score_read:.2f})  ",
        f"**Scored:** {len(ranked)} total items",
        "",
        "---",
        "",
    ]
    if not kept:
        return "\n".join(lines + ["_No items met the relevance threshold this week._", ""])

    lines.extend(render_brief_entry_blocks(kept, items_by_id).splitlines())
    body = "\n".join(lines)
    frontmatter = {
        "title": frontmatter_title,
        "date": week_of,
        "date created": _weekly_date_created_utc(week_of),
        "lastmod": today,
        "tags": aggregate_ranked_item_tags(kept if kept else ranked),
        "generator": "tocify-weekly",
        "period": "weekly",
        "topic": topic,
        "week_of": week_of,
        "included": len(kept),
        "scored": len(ranked),
        "triage_backend": triage_backend,
        "triage_model": triage_model,
    }
    return with_frontmatter(body, frontmatter)


BRIEF_HEADER_INCLUDED_RE = re.compile(r"(\*\*Included:\*\*\s*)\d+")
BRIEF_HEADER_SCORED_RE = re.compile(r"(\*\*Scored:\*\*\s*)\d+")


def parse_brief_body_into_header_and_entries(body: str) -> tuple[str, list[str]]:
    """Split brief body into header (up to first ---) and list of entry blocks."""
    if not body or "\n---\n" not in body:
        return body.strip(), []
    parts = body.split("\n---\n")
    header = (parts[0] or "").strip()
    entry_blocks = [(p or "").strip() for p in parts[1:] if (p or "").strip()]
    return header, entry_blocks


def update_brief_header_counts(header: str, merged_included: int, merged_scored: int) -> str:
    """Replace Included and Scored counts in a weekly brief header."""
    header = BRIEF_HEADER_INCLUDED_RE.sub(rf"\g<1>{merged_included}", header)
    header = BRIEF_HEADER_SCORED_RE.sub(rf"\g<1>{merged_scored}", header)
    return header


def render_brief_entry_blocks(kept: list[dict], items_by_id: dict[str, dict]) -> str:
    """Render only weekly brief entry blocks for the kept ranked items."""
    lines: list[str] = []
    for ranked in kept:
        item = items_by_id.get(ranked["id"], {})
        tags = ", ".join(ranked.get("tags", [])) if ranked.get("tags") else ""
        pub = ranked.get("published_utc")
        summary = (item.get("summary") or "").strip()
        lines += [
            f"## [{ranked['title']}]({ranked['link']})",
            f"*{ranked['source']}*  ",
            f"Score: **{ranked['score']:.2f}**" + (f"  \nPublished: {pub}" if pub else ""),
            (f"Tags: {tags}" if tags else ""),
            "",
            (ranked.get("why") or "").strip(),
            "",
        ]
        if summary:
            lines += ["<details>", "<summary>RSS summary</summary>", "", summary, "", "</details>", ""]
        lines += ["---", ""]
    return "\n".join(lines)


def _merge_unique(values: list[str]) -> list[str]:
    out: list[str] = []
    seen = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def merge_brief_frontmatter(
    existing_frontmatter: dict,
    new_kept: list[dict],
    merged_included: int,
    merged_scored: int,
) -> dict:
    """Update frontmatter when appending new entries into an existing weekly brief.

    Does not overwrite 'date created'; keeps the original.
    """
    merged = dict(existing_frontmatter)
    merged["included"] = merged_included
    merged["scored"] = merged_scored
    merged["lastmod"] = datetime.now(timezone.utc).date().isoformat()
    # Preserve existing "date created" on merge (do not set or overwrite)
    existing_tags = normalize_ai_tags(_string_list(existing_frontmatter.get("tags")))
    new_tags = aggregate_ranked_item_tags(new_kept) if new_kept else []
    combined = _merge_unique(existing_tags + new_tags)
    merged["tags"] = sorted(normalize_ai_tags(combined))
    return merged


def build_allowed_url_index_from_link_rows(link_rows: list[dict]) -> dict[str, str]:
    """Build allowed URL index from per-brief metadata rows."""
    urls = [str(row.get("url") or "").strip() for row in link_rows if row.get("url")]
    return build_allowed_url_index(urls)


_weekly_link_resolver_fn = None


def _load_weekly_link_resolver():
    """Load and cache the weekly heading resolver (once per process)."""
    global _weekly_link_resolver_fn
    if _weekly_link_resolver_fn is not None:
        return _weekly_link_resolver_fn
    try:
        from tocify.runner.link_resolution import resolve_weekly_heading_links

        _weekly_link_resolver_fn = resolve_weekly_heading_links
        return _weekly_link_resolver_fn
    except Exception as err:
        module_path = Path(__file__).resolve().with_name("link_resolution.py")
        spec = importlib.util.spec_from_file_location("tocify_runner_link_resolution_runtime", module_path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Failed to load link resolver module at {module_path}") from err
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _weekly_link_resolver_fn = module.resolve_weekly_heading_links
        return _weekly_link_resolver_fn


def build_weekly_link_metadata_rows(
    brief_filename: str,
    kept: list[dict],
    items_by_id: dict[str, dict],
) -> list[dict]:
    """Return link metadata rows used for per-brief heading canonicalization."""
    rows: list[dict] = []
    for ranked in kept:
        item = items_by_id.get(ranked.get("id"), {})
        title = str(ranked.get("title") or item.get("title") or "").strip()
        if not title:
            continue
        canonical_url = str(item.get("link") or "").strip()
        if not is_valid_http_url(canonical_url):
            continue
        rows.append(
            {
                "brief_filename": brief_filename,
                "title": title,
                "url": canonical_url,
            }
        )
    return rows


def resolve_weekly_heading_links(md: str, brief_filename: str, rows: list[dict]) -> tuple[str, dict]:
    """Canonicalize weekly heading links (## [Title](url)) from metadata rows."""
    resolver = _load_weekly_link_resolver()
    return resolver(md, brief_filename, rows)


def build_weekly_allowed_url_index(kept: list[dict], items_by_id: dict[str, dict]) -> dict[str, str]:
    """Build an allowlist index from canonical item links in kept rows."""
    canonical_urls: list[str] = []
    for ranked in kept:
        item = items_by_id.get(ranked.get("id"), {})
        link = str(item.get("link") or "").strip()
        if link:
            canonical_urls.append(link)
    return build_allowed_url_index(canonical_urls)
