"""Deterministic canonical link resolution for weekly brief heading links."""

import re
from collections import defaultdict

from tocify.runner.link_hygiene import is_valid_http_url

HEADING_LINK_RE = re.compile(
    r"^(?P<prefix>\s*##\s+\[)(?P<title>.+?)(?P<middle>\]\()(?P<url>[^)]+)(?P<suffix>\)\s*)$",
    re.MULTILINE,
)
TITLE_WHITESPACE_RE = re.compile(r"\s+")


def normalize_title_for_match(title: str) -> str:
    return TITLE_WHITESPACE_RE.sub(" ", str(title or "").strip()).lower()


def build_brief_title_url_index(rows: list[dict], brief_filename: str) -> dict:
    exact_candidates: dict[str, list[str]] = defaultdict(list)
    normalized_candidates: dict[str, list[str]] = defaultdict(list)

    for row in rows:
        if str(row.get("brief_filename") or "").strip() != brief_filename:
            continue
        title = str(row.get("title") or "").strip()
        if not title:
            continue
        url = str(row.get("url") or "").strip()
        exact_candidates[title].append(url)
        normalized = normalize_title_for_match(title)
        if normalized:
            normalized_candidates[normalized].append(url)

    return {
        "exact_candidates": exact_candidates,
        "normalized_candidates": normalized_candidates,
    }


def resolve_weekly_heading_links(markdown: str, brief_filename: str, rows: list[dict]) -> tuple[str, dict]:
    """Resolve heading links of the form `## [Title](url)` using deterministic metadata matches."""
    index = build_brief_title_url_index(rows, brief_filename)
    exact_candidates: dict[str, list[str]] = index["exact_candidates"]
    normalized_candidates: dict[str, list[str]] = index["normalized_candidates"]

    stats = {
        "exact_matches": 0,
        "normalized_matches": 0,
        "ambiguous": 0,
        "missing": 0,
        "invalid_url": 0,
        "unchanged": 0,
    }

    def _replace(match: re.Match) -> str:
        title = str(match.group("title") or "").strip()
        current_url = str(match.group("url") or "").strip()

        candidates = exact_candidates.get(title, [])
        if len(candidates) == 1:
            canonical = candidates[0]
            if not is_valid_http_url(canonical):
                stats["invalid_url"] += 1
                stats["unchanged"] += 1
                return match.group(0)
            stats["exact_matches"] += 1
            if canonical == current_url:
                stats["unchanged"] += 1
                return match.group(0)
            return (
                f"{match.group('prefix')}{title}{match.group('middle')}"
                f"{canonical}{match.group('suffix')}"
            )
        if len(candidates) > 1:
            stats["ambiguous"] += 1
            stats["unchanged"] += 1
            return match.group(0)

        normalized = normalize_title_for_match(title)
        if not normalized:
            stats["missing"] += 1
            stats["unchanged"] += 1
            return match.group(0)

        normalized_rows = normalized_candidates.get(normalized, [])
        if len(normalized_rows) == 1:
            canonical = normalized_rows[0]
            if not is_valid_http_url(canonical):
                stats["invalid_url"] += 1
                stats["unchanged"] += 1
                return match.group(0)
            stats["normalized_matches"] += 1
            if canonical == current_url:
                stats["unchanged"] += 1
                return match.group(0)
            return (
                f"{match.group('prefix')}{title}{match.group('middle')}"
                f"{canonical}{match.group('suffix')}"
            )
        if len(normalized_rows) > 1:
            stats["ambiguous"] += 1
            stats["unchanged"] += 1
            return match.group(0)

        stats["missing"] += 1
        stats["unchanged"] += 1
        return match.group(0)

    return HEADING_LINK_RE.sub(_replace, markdown), stats
