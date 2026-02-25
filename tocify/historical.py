"""
Historical article fetch: date-range backends (journals + news) returning same item schema as RSS.
Used for 2003-2024 or any date range. Present flow uses RSS + optional news; historical uses these backends.
"""

import os
from datetime import date, datetime, timezone

import requests
from dotenv import load_dotenv

from tocify.utils import normalize_summary, sha1

load_dotenv()

SUMMARY_MAX_CHARS = int(os.getenv("SUMMARY_MAX_CHARS", "500"))
OPENALEX_TIMEOUT = int(os.getenv("OPENALEX_TIMEOUT", "30"))
OPENALEX_PAGE_SIZE = min(200, max(1, int(os.getenv("OPENALEX_PAGE_SIZE", "200"))))
OPENALEX_MAX_ITEMS_PER_RANGE = int(os.getenv("OPENALEX_MAX_ITEMS_PER_RANGE", "10000"))
HISTORICAL_MAX_ITEMS = int(os.getenv("HISTORICAL_MAX_ITEMS", "2000"))


def _fetch_openalex(
    start_date: date,
    end_date: date,
    *,
    search: str | None = None,
) -> list[dict]:
    """Fetch works from OpenAlex for the date range. Returns list of item dicts (id, source, title, link, published_utc, summary)."""
    from_str = start_date.isoformat()
    to_str = end_date.isoformat()
    filters = f"from_publication_date:{from_str},to_publication_date:{to_str}"
    params: dict = {
        "filter": filters,
        "per-page": OPENALEX_PAGE_SIZE,
        "sort": "publication_date:desc",
    }
    if search and search.strip():
        params["search"] = search.strip()

    items: list[dict] = []
    cursor: str | None = "*"
    while cursor and len(items) < OPENALEX_MAX_ITEMS_PER_RANGE:
        params["cursor"] = cursor
        try:
            resp = requests.get(
                "https://api.openalex.org/works",
                params=params,
                timeout=OPENALEX_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            if not items:
                import warnings
                warnings.warn(f"OpenAlex fetch failed: {e}", stacklevel=2)
            break

        results = data.get("results") or []
        meta = data.get("meta") or {}
        cursor = meta.get("next_cursor")

        for w in results:
            title = (w.get("title") or w.get("display_name") or "").strip()
            if not title:
                continue
            doi = (w.get("doi") or "").strip()
            if doi and not doi.startswith("http"):
                doi = f"https://doi.org/{doi}"
            link = doi or (w.get("id") or "").strip()
            if not link:
                continue
            pub_date = w.get("publication_date")
            if pub_date:
                try:
                    dt = datetime.strptime(pub_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                    published_utc = dt.isoformat()
                except Exception:
                    published_utc = pub_date
            else:
                published_utc = None
            source_name = "OpenAlex"
            primary = w.get("primary_location") or {}
            src = primary.get("source") if isinstance(primary.get("source"), dict) else None
            if src:
                source_name = (src.get("display_name") or src.get("id") or "OpenAlex").strip()
            abstract = w.get("abstract_inverted_index")
            if abstract is None:
                abstract = w.get("abstract") or ""
            if isinstance(abstract, dict):
                try:
                    pairs: list[tuple[int, str]] = []
                    for word, pos in abstract.items():
                        if isinstance(pos, list):
                            for p in pos:
                                pairs.append((p, word))
                        else:
                            pairs.append((pos, word))
                    pairs.sort(key=lambda x: x[0])
                    abstract = " ".join(w for _, w in pairs)
                except Exception:
                    abstract = ""
            summary = normalize_summary(str(abstract), max_chars=SUMMARY_MAX_CHARS)
            item_id = sha1(f"{source_name}|{title}|{link}")
            items.append({
                "id": item_id,
                "source": source_name,
                "title": title,
                "link": link,
                "published_utc": published_utc,
                "summary": summary,
            })

        if not results or len(results) < params["per-page"]:
            break

    return items


def fetch_historical_items(
    start_date: date,
    end_date: date,
    backends: list[str] | None = None,
    *,
    openalex_search: str | None = None,
    news_query: str | None = None,
    googlenews_queries: list[str] | None = None,
    clinicaltrials_query: str | None = None,
    edgar_ciks: list[str] | None = None,
    newsrooms_urls: list[str] | None = None,
) -> list[dict]:
    """
    Fetch articles from historical backends for the given date range.
    Returns list of dicts with keys: id, source, title, link, published_utc, summary
    (same schema as RSS for merge/triage).

    backends: list of "openalex", "newsapi", "googlenews", "clinicaltrials", "edgar", "newsrooms".
    If None, uses env HISTORICAL_BACKENDS (comma-separated) or ["openalex"].
    googlenews_queries: list of search terms for Google News RSS (one request per query). If empty when googlenews is in backends, skip.
    clinicaltrials_query: optional search term for ClinicalTrials.gov. If None when clinicaltrials in backends, uses env CLINICALTRIALS_QUERY.
    edgar_ciks: optional list of SEC CIKs for company filings. If None when edgar in backends, uses env EDGAR_CIKS or per-topic file.
    newsrooms_urls: optional list of newsroom index URLs to scrape. If None when newsrooms in backends, uses per-topic file or env.
    """
    if backends is None:
        raw = (os.getenv("HISTORICAL_BACKENDS") or "openalex").strip()
        backends = [b.strip().lower() for b in raw.split(",") if b.strip()]

    all_items: list[dict] = []
    seen_ids: set[str] = set()

    for name in backends:
        try:
            if name == "openalex":
                batch = _fetch_openalex(start_date, end_date, search=openalex_search)
                for it in batch:
                    iid = it.get("id")
                    if iid and iid not in seen_ids:
                        seen_ids.add(iid)
                        all_items.append(it)
            elif name == "newsapi":
                from tocify.news import fetch_news_items
                batch = fetch_news_items(start_date, end_date, query=news_query or None)
                for it in batch:
                    iid = it.get("id")
                    if iid and iid not in seen_ids:
                        seen_ids.add(iid)
                        all_items.append(it)
            elif name == "googlenews":
                queries = googlenews_queries or []
                if queries:
                    from tocify.googlenews import fetch_google_news_items
                    batch = fetch_google_news_items(start_date, end_date, queries)
                    for it in batch:
                        iid = it.get("id")
                        if iid and iid not in seen_ids:
                            seen_ids.add(iid)
                            all_items.append(it)
            elif name == "clinicaltrials":
                from tocify.clinicaltrials import fetch_clinicaltrials_items
                q = clinicaltrials_query or os.getenv("CLINICALTRIALS_QUERY", "").strip() or None
                batch = fetch_clinicaltrials_items(start_date, end_date, query=q)
                for it in batch:
                    iid = it.get("id")
                    if iid and iid not in seen_ids:
                        seen_ids.add(iid)
                        all_items.append(it)
            elif name == "edgar":
                ciks = edgar_ciks
                if ciks is None:
                    raw_ciks = (os.getenv("EDGAR_CIKS") or "").strip()
                    ciks = [c.strip() for c in raw_ciks.split(",") if c.strip()]
                if ciks:
                    from tocify.edgar import fetch_edgar_items
                    batch = fetch_edgar_items(start_date, end_date, ciks=ciks)
                    for it in batch:
                        iid = it.get("id")
                        if iid and iid not in seen_ids:
                            seen_ids.add(iid)
                            all_items.append(it)
            elif name == "newsrooms":
                urls = newsrooms_urls
                if urls is None:
                    raw_urls = (os.getenv("NEWSROOMS_URLS") or "").strip()
                    urls = [u.strip() for u in raw_urls.splitlines() if u.strip()]
                if urls:
                    from tocify.newsrooms import fetch_newsroom_items
                    batch = fetch_newsroom_items(start_date, end_date, urls=urls)
                    for it in batch:
                        iid = it.get("id")
                        if iid and iid not in seen_ids:
                            seen_ids.add(iid)
                            all_items.append(it)
        except Exception as e:
            import warnings
            warnings.warn(f"Historical backend {name!r} failed: {e}", stacklevel=2)

    all_items.sort(key=lambda x: x.get("published_utc") or "", reverse=True)
    return all_items[:HISTORICAL_MAX_ITEMS]
