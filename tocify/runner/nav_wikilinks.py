"""Append prev/next wikilink nav blocks to weekly briefs and monthly roundups (idempotent)."""

import re


# Patterns to strip existing nav blocks (idempotent re-runs).
WEEKLY_NAV_LINE_RE = re.compile(
    r"\n?>?\s*\[!info\]\s*\[\[[^\]|]+\|previous\]\]\s*<<\s*weekly\s*>>\s*\[\[[^\]|]+\|next\]\]\s*\n?$",
    re.IGNORECASE,
)
MONTHLY_NAV_LINE_RE = re.compile(
    r"\n?>?\s*\[\[[^\]|]+\|previous\]\]\s*<<\s*monthly\s*>>\s*\[\[[^\]|]+\|next\]\]\s*\n?$",
    re.IGNORECASE,
)


def weekly_prev_next_slugs(brief_filename: str) -> tuple[str, str]:
    """Return (prev_slug, next_slug) for a weekly brief filename (e.g. '2026 week 08.md').

    Slug format: 'YYYY week NN' (no .md). Handles year boundary: week 01 prev = last year week 52, week 52 next = next year week 01.
    """
    # Expect "YYYY week NN.md" or "YYYY week N.md"
    match = re.match(r"^(\d{4})\s+week\s+(\d{1,2})\.md$", brief_filename.strip(), re.IGNORECASE)
    if not match:
        return ("", "")
    year = int(match.group(1))
    week = int(match.group(2))
    prev_year = year if week > 1 else year - 1
    prev_week = week - 1 if week > 1 else 52
    next_year = year if week < 52 else year + 1
    next_week = week + 1 if week < 52 else 1
    prev_slug = f"{prev_year} week {prev_week:02d}"
    next_slug = f"{next_year} week {next_week:02d}"
    return (prev_slug, next_slug)


def monthly_prev_next_slugs(month_iso: str) -> tuple[str, str]:
    """Return (prev_slug, next_slug) for a month YYYY-MM (e.g. '2026-01')."""
    try:
        parts = month_iso.strip().split("-")
        if len(parts) != 2:
            return ("", "")
        y, m = int(parts[0]), int(parts[1])
        if not (1 <= m <= 12):
            return ("", "")
        prev_y = y if m > 1 else y - 1
        prev_m = m - 1 if m > 1 else 12
        next_y = y if m < 12 else y + 1
        next_m = m + 1 if m < 12 else 1
        return (f"{prev_y}-{prev_m:02d}", f"{next_y}-{next_m:02d}")
    except (ValueError, TypeError):
        return ("", "")


def _strip_trailing_nav(body: str, pattern: re.Pattern) -> str:
    """Remove a single trailing nav line matching pattern; ensure no trailing junk."""
    return pattern.sub("", body).rstrip()


def ensure_trailing_weekly_nav(markdown: str, brief_filename: str) -> str:
    """Ensure markdown ends with the weekly nav block (idempotent). brief_filename e.g. '2026 week 08.md'."""
    from tocify.frontmatter import split_frontmatter_and_body, with_frontmatter

    frontmatter, body = split_frontmatter_and_body(markdown)
    body = _strip_trailing_nav(body, WEEKLY_NAV_LINE_RE)
    prev_slug, next_slug = weekly_prev_next_slugs(brief_filename)
    nav_line = f"> [!info] [[{prev_slug}|previous]] << weekly >> [[{next_slug}|next]]"
    body = (body.rstrip() + "\n\n" + nav_line + "\n").rstrip() + "\n"
    return with_frontmatter(body, frontmatter) if frontmatter else body


def ensure_trailing_monthly_nav(body: str, month_iso: str) -> str:
    """Ensure body ends with the monthly nav block (idempotent). month_iso e.g. '2026-01'. Returns body only (no frontmatter)."""
    body = _strip_trailing_nav(body, MONTHLY_NAV_LINE_RE)
    prev_slug, next_slug = monthly_prev_next_slugs(month_iso)
    nav_line = f"> [[{prev_slug}|previous]] << monthly >> [[{next_slug}|next]]"
    return (body.rstrip() + "\n\n" + nav_line + "\n").rstrip() + "\n"
