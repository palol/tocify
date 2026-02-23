"""
Company newsroom scraper: best-effort fetch of article links from newsroom index pages.
Same item schema as RSS (id, source, title, link, published_utc, summary).
Experimental: HTML structure varies by site; rate-limited and capped.
"""

import os
import re
import time
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import requests
from dotenv import load_dotenv

from tocify.utils import sha1

load_dotenv()

NEWSROOMS_TIMEOUT = int(os.getenv("NEWSROOMS_TIMEOUT", "20"))
NEWSROOMS_MAX_ITEMS_PER_URL = int(os.getenv("NEWSROOMS_MAX_ITEMS_PER_URL", "30"))
NEWSROOMS_MAX_ITEMS = int(os.getenv("NEWSROOMS_MAX_ITEMS", "100"))
NEWSROOMS_DELAY_SECONDS = float(os.getenv("NEWSROOMS_DELAY_SECONDS", "1.0"))

# Date in URL path, e.g. /2025/01/15/, /2025-01-15/, /jan-15-2025/
DATE_IN_PATH = re.compile(
    r"(?:^|/)(\d{4})[-/](\d{1,2})[-/](\d{1,2})(?:/|$)|"
    r"(?:^|/)(\d{4})[-/](\d{1,2})(?:/|$)"
)


def _date_from_path(path: str) -> date | None:
    """Try to extract a date from URL path; return None if not found."""
    m = DATE_IN_PATH.search(path)
    if not m:
        return None
    g = m.groups()
    if g[0] is not None:
        y, mo, d = int(g[0]), int(g[1]), int(g[2])
    elif g[3] is not None:
        y, mo = int(g[3]), int(g[4])
        d = 1
    else:
        return None
    try:
        return date(y, mo, d)
    except ValueError:
        return None


class _LinkExtractor(HTMLParser):
    """Extract same-domain links and optional date from index page."""

    def __init__(self, base_url: str, base_netloc: str):
        super().__init__()
        self.base_url = base_url
        self.base_netloc = base_netloc
        self.links: list[tuple[str, str]] = []  # (href, link_text)
        self._active_link_idx: int | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        href = None
        for k, v in attrs:
            if k == "href" and v:
                href = v.strip()
                break
        if not href or href.startswith("#") or href.startswith("mailto:"):
            return
        full = urljoin(self.base_url, href)
        parsed = urlparse(full)
        if parsed.netloc != self.base_netloc:
            return
        if not parsed.path or parsed.path == "/":
            return
        self.links.append((full, ""))
        self._active_link_idx = len(self.links) - 1

    def handle_endtag(self, tag: str) -> None:
        if tag == "a":
            self._active_link_idx = None

    def handle_data(self, data: str) -> None:
        if self._active_link_idx is not None and data:
            prev_href, prev_text = self.links[self._active_link_idx]
            self.links[self._active_link_idx] = (prev_href, (prev_text + data).strip())


def _fetch_newsroom_url(
    url: str,
    start_date: date,
    end_date: date,
    timeout: int,
) -> list[dict]:
    """Fetch one newsroom index URL and return items in schema (same domain, date in range when detectable)."""
    try:
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
        html = resp.text
    except Exception as e:
        import warnings
        warnings.warn(f"Newsroom fetch failed {url!r}: {e}", stacklevel=2)
        return []

    parsed_base = urlparse(url)
    netloc = parsed_base.netloc
    source_name = netloc.replace("www.", "") or "Newsroom"
    parser = _LinkExtractor(url, netloc)
    try:
        parser.feed(html)
    except Exception:
        return []

    items: list[dict] = []
    seen: set[str] = set()
    for link_url, link_text in parser.links:
        if len(items) >= NEWSROOMS_MAX_ITEMS_PER_URL:
            break
        if link_url in seen:
            continue
        seen.add(link_url)
        path = urlparse(link_url).path
        article_date = _date_from_path(path)
        if article_date is None:
            continue
        if article_date < start_date or article_date > end_date:
            continue
        title = link_text[:200] if link_text else path.split("/")[-1] or link_url
        if not title:
            title = link_url
        published_utc = datetime.combine(
            article_date, datetime.min.time(), tzinfo=timezone.utc
        ).isoformat()
        item_id = sha1(f"{source_name}|{title}|{link_url}")
        items.append({
            "id": item_id,
            "source": source_name,
            "title": title,
            "link": link_url,
            "published_utc": published_utc,
            "summary": "",
        })
    return items


def fetch_newsroom_items(
    start_date: date,
    end_date: date,
    *,
    urls: list[str] | None = None,
) -> list[dict]:
    """
    Fetch article links from company newsroom index pages for the given date range.
    Returns list of dicts with keys: id, source, title, link, published_utc, summary
    (same schema as RSS). Summary may be empty. Only links with a date in the URL path are included.

    urls: list of newsroom index page URLs. If None, uses env NEWSROOMS_URLS (newline-separated).
    """
    if urls is None:
        raw = (os.getenv("NEWSROOMS_URLS") or "").strip()
        urls = [u.strip() for u in raw.splitlines() if u.strip()]
    if not urls:
        return []

    timeout = NEWSROOMS_TIMEOUT
    delay = max(0.0, NEWSROOMS_DELAY_SECONDS)
    last_domain: str | None = None
    all_items: list[dict] = []
    for url in urls:
        domain = urlparse(url).netloc
        if last_domain == domain and delay > 0:
            time.sleep(delay)
        last_domain = domain
        batch = _fetch_newsroom_url(url, start_date, end_date, timeout)
        all_items.extend(batch)
        if len(all_items) >= NEWSROOMS_MAX_ITEMS:
            break

    all_items.sort(key=lambda x: x.get("published_utc") or "", reverse=True)
    return all_items[:NEWSROOMS_MAX_ITEMS]
