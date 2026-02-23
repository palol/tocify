"""
Google News RSS: fetch articles by search query and date window. Same item schema as RSS
(id, source, title, link, published_utc, summary). No API key; uses public RSS search.

Enable with ADD_GOOGLE_NEWS=1 or NEWS_BACKEND=googlenews. Queries are built from interests
keywords (all keywords by default; cap via GOOGLE_NEWS_MAX_QUERIES for safety).
"""

import os
from datetime import date, datetime, time as dt_time, timezone
from io import BytesIO
from urllib.parse import quote_plus

import feedparser
import requests
from dateutil import parser as dtparser
from dotenv import load_dotenv
from tqdm import tqdm

from tocify.utils import normalize_summary, sha1

load_dotenv()

SUMMARY_MAX_CHARS = int(os.getenv("SUMMARY_MAX_CHARS", "500"))
GOOGLE_NEWS_TIMEOUT = int(os.getenv("GOOGLE_NEWS_TIMEOUT", "25"))
GOOGLE_NEWS_MAX_ITEMS_PER_QUERY = min(100, max(1, int(os.getenv("GOOGLE_NEWS_MAX_ITEMS_PER_QUERY", "30"))))
GOOGLE_NEWS_MAX_TOTAL_ITEMS = int(os.getenv("GOOGLE_NEWS_MAX_TOTAL_ITEMS", "2000"))
GOOGLE_NEWS_MAX_QUERIES = int(os.getenv("GOOGLE_NEWS_MAX_QUERIES", "100"))
GOOGLE_NEWS_BASE_URL = "https://news.google.com/rss/search"
GOOGLE_NEWS_PARAMS = {"hl": "en-US", "gl": "US", "ceid": "US:en"}


def _parse_date(entry) -> datetime | None:
    """Return datetime (UTC) for a feedparser entry from published/updated fields, or None."""
    for attr in ("published_parsed", "updated_parsed"):
        t = getattr(entry, attr, None)
        if t:
            return datetime(*t[:6], tzinfo=timezone.utc)
    for key in ("published", "updated", "created"):
        val = entry.get(key)
        if val:
            try:
                dt = dtparser.parse(val)
                return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
            except Exception:
                pass
    return None


def fetch_google_news_items(
    start_date: date,
    end_date: date,
    queries: list[str],
    *,
    max_queries: int | None = None,
    timeout: int | None = None,
    max_items_per_query: int | None = None,
    max_total_items: int | None = None,
) -> list[dict]:
    """
    Fetch articles from Google News RSS search for the given date range and query list.
    Returns list of dicts with keys: id, source, title, link, published_utc, summary
    (same schema as RSS items for merge/triage).

    start_date, end_date: inclusive date window (UTC); items outside this window are dropped.
    queries: list of search terms; one RSS request per query.
    max_queries: cap on number of queries to run (default from env GOOGLE_NEWS_MAX_QUERIES).
    """
    if not queries:
        return []
    timeout = timeout if timeout is not None else GOOGLE_NEWS_TIMEOUT
    max_per_query = max_items_per_query if max_items_per_query is not None else GOOGLE_NEWS_MAX_ITEMS_PER_QUERY
    max_total = max_total_items if max_total_items is not None else GOOGLE_NEWS_MAX_TOTAL_ITEMS
    cap = max_queries if max_queries is not None else GOOGLE_NEWS_MAX_QUERIES
    to_run = queries[:cap]

    cutoff = datetime.combine(start_date, dt_time(0, 0, 0), tzinfo=timezone.utc)
    end_dt = datetime.combine(end_date, dt_time(23, 59, 59), tzinfo=timezone.utc)

    seen_ids: set[str] = set()
    all_items: list[dict] = []

    for q in to_run:
        q = (q or "").strip()
        if not q:
            continue
        url = f"{GOOGLE_NEWS_BASE_URL}?q={quote_plus(q)}&hl={GOOGLE_NEWS_PARAMS['hl']}&gl={GOOGLE_NEWS_PARAMS['gl']}&ceid={GOOGLE_NEWS_PARAMS['ceid']}"
        try:
            resp = requests.get(url, timeout=timeout)
            resp.raise_for_status()
            d = feedparser.parse(BytesIO(resp.content))
        except Exception as e:
            tqdm.write(f"[WARN] Google News RSS fetch failed {q!r}: {e}")
            continue

        source_label = f"Google News ({q})"
        for e in (d.entries or [])[:max_per_query]:
            title = (e.get("title") or "").strip()
            link = (e.get("link") or "").strip()
            if not title or not link:
                continue
            dt = _parse_date(e)
            if dt and (dt < cutoff or dt > end_dt):
                continue
            summary = (e.get("summary") or e.get("description") or "")
            if hasattr(summary, "get"):  # feedparser can return a dict with "value"
                summary = summary.get("value", "") if isinstance(summary, dict) else str(summary)
            summary = normalize_summary(str(summary), max_chars=SUMMARY_MAX_CHARS)
            item_id = sha1(f"{source_label}|{title}|{link}")
            if item_id in seen_ids:
                continue
            seen_ids.add(item_id)
            all_items.append({
                "id": item_id,
                "source": source_label,
                "title": title,
                "link": link,
                "published_utc": dt.isoformat() if dt else None,
                "summary": summary,
            })

    all_items.sort(key=lambda x: x.get("published_utc") or "", reverse=True)
    return all_items[:max_total]
