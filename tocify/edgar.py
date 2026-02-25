"""
SEC EDGAR backend: fetch company filings by CIK via official RSS/Atom feeds.
Same item schema as RSS (id, source, title, link, published_utc, summary).
"""

import os
from datetime import date, datetime, time as dt_time, timezone
from io import BytesIO

import feedparser
import requests
from dotenv import load_dotenv

from tocify.utils import normalize_summary, sha1

load_dotenv()

SUMMARY_MAX_CHARS = int(os.getenv("SUMMARY_MAX_CHARS", "500"))
EDGAR_TIMEOUT = int(os.getenv("EDGAR_TIMEOUT", "25"))
EDGAR_MAX_ITEMS_PER_CIK = int(os.getenv("EDGAR_MAX_ITEMS_PER_CIK", "50"))
EDGAR_MAX_ITEMS = int(os.getenv("EDGAR_MAX_ITEMS", "200"))

SEC_EDGAR_FEED_URL = "https://www.sec.gov/cgi-bin/browse-edgar"


def _normalize_cik(cik: str) -> str:
    """Zero-pad CIK to 10 digits for SEC URLs."""
    s = (cik or "").strip()
    if not s or not s.isdigit():
        return ""
    return s.zfill(10)


def _parse_entry_date(entry) -> datetime | None:
    """Return datetime (UTC) for a feedparser entry from published/updated, or None."""
    for attr in ("published_parsed", "updated_parsed"):
        t = getattr(entry, attr, None)
        if t:
            return datetime(*t[:6], tzinfo=timezone.utc)
    for key in ("published", "updated", "created"):
        val = entry.get(key)
        if val:
            try:
                from dateutil import parser as dtparser
                dt = dtparser.parse(val)
                return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
            except Exception:
                pass
    return None


def fetch_edgar_items(
    start_date: date,
    end_date: date,
    *,
    ciks: list[str] | None = None,
) -> list[dict]:
    """
    Fetch company filings from SEC EDGAR for the given date range.
    Returns list of dicts with keys: id, source, title, link, published_utc, summary
    (same schema as RSS items for merge/triage).

    ciks: list of SEC Central Index Key (company identifiers). If None, uses env EDGAR_CIKS (comma-separated).
    """
    if ciks is None:
        raw = (os.getenv("EDGAR_CIKS") or "").strip()
        ciks = [c.strip() for c in raw.split(",") if c.strip()]
    if not ciks:
        return []

    start_dt = datetime.combine(start_date, dt_time(0, 0, 0), tzinfo=timezone.utc)
    end_dt = datetime.combine(end_date, dt_time(23, 59, 59), tzinfo=timezone.utc)

    items: list[dict] = []
    for cik in ciks:
        normalized = _normalize_cik(cik)
        if not normalized:
            continue
        url = f"{SEC_EDGAR_FEED_URL}?action=getcurrent&CIK={normalized}&output=atom"
        try:
            resp = requests.get(url, timeout=EDGAR_TIMEOUT)
            resp.raise_for_status()
            d = feedparser.parse(BytesIO(resp.content))
        except Exception as e:
            import warnings
            warnings.warn(f"EDGAR fetch failed for CIK {normalized}: {e}", stacklevel=2)
            continue

        feed_title = (d.feed.get("title") if d.feed else None) or f"SEC CIK {normalized}"
        source_name = (feed_title or "SEC EDGAR").strip()
        if "SEC" not in source_name and "EDGAR" not in source_name:
            source_name = f"{source_name} (SEC EDGAR)"

        count = 0
        for e in d.entries:
            if count >= EDGAR_MAX_ITEMS_PER_CIK or len(items) >= EDGAR_MAX_ITEMS:
                break
            title = (e.get("title") or "").strip()
            link = (e.get("link") or "").strip()
            if not title or not link:
                continue
            dt_parsed = _parse_entry_date(e)
            if dt_parsed is None or dt_parsed < start_dt or dt_parsed > end_dt:
                continue
            published_utc = dt_parsed.isoformat()
            summary_raw = e.get("summary") or e.get("description") or ""
            if hasattr(summary_raw, "get"):
                summary_raw = summary_raw.get("value", summary_raw) or ""
            summary = normalize_summary(str(summary_raw), max_chars=SUMMARY_MAX_CHARS)
            item_id = sha1(f"{source_name}|{title}|{link}")
            items.append({
                "id": item_id,
                "source": source_name,
                "title": title,
                "link": link,
                "published_utc": published_utc,
                "summary": summary,
            })
            count += 1

    items.sort(key=lambda x: x.get("published_utc") or "", reverse=True)
    return items[:EDGAR_MAX_ITEMS]
