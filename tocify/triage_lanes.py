"""Helpers for assigning and using research/news triage lanes."""

from __future__ import annotations

from pathlib import Path

TRIAGE_LANE_RESEARCH = "research"
TRIAGE_LANE_NEWS = "news"
NEWS_BACKENDS = frozenset({"newsapi", "googlenews", "newsrooms"})


def normalize_triage_lane(value: object, default: str = TRIAGE_LANE_RESEARCH) -> str:
    """Return a supported triage lane, falling back to default."""
    raw = str(value or "").strip().lower()
    if raw in (TRIAGE_LANE_RESEARCH, TRIAGE_LANE_NEWS):
        return raw
    default_raw = str(default or TRIAGE_LANE_RESEARCH).strip().lower()
    if default_raw == TRIAGE_LANE_NEWS:
        return TRIAGE_LANE_NEWS
    return TRIAGE_LANE_RESEARCH


def default_lane_for_backend(backend: str | None) -> str:
    """Map known historical/news backends to the default triage lane."""
    name = str(backend or "").strip().lower()
    if name in NEWS_BACKENDS:
        return TRIAGE_LANE_NEWS
    return TRIAGE_LANE_RESEARCH


def apply_backend_triage_lane(items: list[dict], backend: str | None) -> list[dict]:
    """Annotate items with the backend's default lane unless already set."""
    lane = default_lane_for_backend(backend)
    for item in items:
        if isinstance(item, dict):
            item["triage_lane"] = normalize_triage_lane(item.get("triage_lane"), lane)
    return items


def ensure_item_triage_lanes(items: list[dict], default: str = TRIAGE_LANE_RESEARCH) -> list[dict]:
    """Ensure every item has a valid triage lane."""
    for item in items:
        if isinstance(item, dict):
            item["triage_lane"] = normalize_triage_lane(item.get("triage_lane"), default)
    return items


def split_items_by_triage_lane(items: list[dict]) -> tuple[list[dict], list[dict]]:
    """Return (research_items, news_items)."""
    research_items: list[dict] = []
    news_items: list[dict] = []
    for item in ensure_item_triage_lanes(items):
        if item.get("triage_lane") == TRIAGE_LANE_NEWS:
            news_items.append(item)
        else:
            research_items.append(item)
    return research_items, news_items


def has_news_lane(items: list[dict]) -> bool:
    """Return True when any item is assigned to the news lane."""
    return any(
        isinstance(item, dict) and normalize_triage_lane(item.get("triage_lane")) == TRIAGE_LANE_NEWS
        for item in items
    )


def news_prompt_enabled(news_prompt_path: Path | str | None, items: list[dict]) -> bool:
    """Return True when the news prompt exists and at least one news item is present."""
    if news_prompt_path is None:
        return False
    return Path(news_prompt_path).exists() and has_news_lane(items)


def merge_ranked_items(*ranked_lists: list[dict]) -> list[dict]:
    """Merge ranked rows by id, keeping the higher-score entry for duplicates."""

    def score_value(row: dict) -> float:
        try:
            return float(row.get("score"))
        except (TypeError, ValueError):
            return float("-inf")

    best_by_id: dict[str, dict] = {}
    for ranked in ranked_lists:
        for row in ranked if isinstance(ranked, list) else []:
            if not isinstance(row, dict):
                continue
            row_id = str(row.get("id") or "").strip()
            if not row_id:
                continue
            previous = best_by_id.get(row_id)
            if previous is None or score_value(row) >= score_value(previous):
                best_by_id[row_id] = row
    return sorted(best_by_id.values(), key=score_value, reverse=True)


def filter_ranked_items_by_lane_thresholds(
    ranked: list[dict],
    items_by_id: dict[str, dict],
    *,
    min_score_read: float,
    min_score_read_news: float,
    max_returned: int,
) -> list[dict]:
    """Filter ranked rows using research/news lane thresholds while preserving order."""
    if max_returned <= 0:
        return []

    kept: list[dict] = []
    for row in ranked if isinstance(ranked, list) else []:
        if not isinstance(row, dict):
            continue
        row_id = str(row.get("id") or "").strip()
        if not row_id:
            continue
        try:
            score = float(row.get("score"))
        except (TypeError, ValueError):
            continue
        item = items_by_id.get(row_id) or {}
        lane = normalize_triage_lane(item.get("triage_lane"))
        threshold = min_score_read_news if lane == TRIAGE_LANE_NEWS else min_score_read
        if score < threshold:
            continue
        kept.append(row)
        if len(kept) >= max_returned:
            break
    return kept


def format_score_threshold_label(min_score_read: float, min_score_read_news: float) -> str:
    """Format the digest score threshold label for one or two lanes."""
    if min_score_read_news == min_score_read:
        return f"score >= {min_score_read:.2f}"
    return f"score >= {min_score_read:.2f} research / {min_score_read_news:.2f} news"
