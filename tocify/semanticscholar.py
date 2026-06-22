"""
Semantic Scholar backend: fetch papers by date window. Same item schema as RSS
(id, source, title, link, published_utc, summary). Uses the Academic Graph paper search API.
"""

import os
import re
import warnings
from datetime import date, datetime, timezone

import requests
from dotenv import load_dotenv

from tocify.utils import normalize_summary, sha1

load_dotenv()

SUMMARY_MAX_CHARS = int(os.getenv("SUMMARY_MAX_CHARS", "500"))
SEMANTIC_SCHOLAR_TIMEOUT = int(os.getenv("SEMANTIC_SCHOLAR_TIMEOUT", "30"))
SEMANTIC_SCHOLAR_PAGE_SIZE = min(100, max(1, int(os.getenv("SEMANTIC_SCHOLAR_PAGE_SIZE", "100"))))
SEMANTIC_SCHOLAR_MAX_ITEMS = min(1000, max(1, int(os.getenv("SEMANTIC_SCHOLAR_MAX_ITEMS", "200"))))
SEMANTIC_SCHOLAR_API_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
SEMANTIC_SCHOLAR_FIELDS = ",".join([
    "title",
    "abstract",
    "publicationDate",
    "year",
    "url",
    "externalIds",
    "venue",
    "publicationVenue",
])
QUERY_MAX_CHARS = 500


def _semantic_scholar_api_key(api_key: str | None = None) -> str:
    return (
        (api_key or "").strip()
        or os.getenv("SEMANTIC_SCHOLAR_API_KEY", "").strip()
        or os.getenv("S2_API_KEY", "").strip()
    )


def _normalize_query(query: str | None) -> str:
    raw = str(query or "").replace("-", " ")
    raw = re.sub(r"\s+", " ", raw).strip()
    return raw[:QUERY_MAX_CHARS]


def _coerce_publication_date(publication_date: object, year: object) -> date | None:
    raw = str(publication_date or "").strip()
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
            return date.fromisoformat(raw)
        if re.fullmatch(r"\d{4}-\d{2}", raw):
            y, month = raw.split("-", 1)
            return date(int(y), int(month), 1)
        if re.fullmatch(r"\d{4}", raw):
            return date(int(raw), 1, 1)
    except ValueError:
        pass

    try:
        parsed_year = int(year)
        if parsed_year > 0:
            return date(parsed_year, 1, 1)
    except (TypeError, ValueError):
        return None
    return None


def _paper_link(paper: dict) -> str:
    external_ids = paper.get("externalIds") or {}
    if isinstance(external_ids, dict):
        for key in ("DOI", "doi"):
            doi = str(external_ids.get(key) or "").strip()
            if doi:
                return doi if doi.startswith("http") else f"https://doi.org/{doi}"
    return str(paper.get("url") or "").strip()


def _paper_source(paper: dict) -> str:
    publication_venue = paper.get("publicationVenue") or {}
    if isinstance(publication_venue, dict):
        venue_name = str(publication_venue.get("name") or "").strip()
        if venue_name:
            return venue_name
    venue = str(paper.get("venue") or "").strip()
    return venue or "Semantic Scholar"


def fetch_semantic_scholar_items(
    start_date: date,
    end_date: date,
    *,
    query: str | None = None,
    api_key: str | None = None,
) -> list[dict]:
    """
    Fetch papers from Semantic Scholar for the given date range.
    Returns list of dicts with keys: id, source, title, link, published_utc, summary
    (same schema as RSS items for merge/triage).

    query: required plain-text search query. Hyphenated terms are normalized to spaces
    because the API treats hyphenated search terms as no-match.
    """
    normalized_query = _normalize_query(query)
    if not normalized_query:
        return []

    params_base: dict[str, object] = {
        "query": normalized_query,
        "fields": SEMANTIC_SCHOLAR_FIELDS,
        "publicationDateOrYear": f"{start_date.isoformat()}:{end_date.isoformat()}",
    }
    headers = {}
    key = _semantic_scholar_api_key(api_key)
    if key:
        headers["x-api-key"] = key

    items: list[dict] = []
    seen_ids: set[str] = set()
    offset = 0

    while len(items) < SEMANTIC_SCHOLAR_MAX_ITEMS and offset < 1000:
        page_size = min(SEMANTIC_SCHOLAR_PAGE_SIZE, SEMANTIC_SCHOLAR_MAX_ITEMS - len(items), 1000 - offset)
        params = dict(params_base)
        params["offset"] = offset
        params["limit"] = page_size

        try:
            resp = requests.get(
                SEMANTIC_SCHOLAR_API_URL,
                params=params,
                headers=headers,
                timeout=SEMANTIC_SCHOLAR_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            if not items:
                warnings.warn(f"Semantic Scholar fetch failed: {e}", stacklevel=2)
            break

        papers = data.get("data") or []
        if not papers:
            break

        for paper in papers:
            title = str(paper.get("title") or "").strip()
            link = _paper_link(paper)
            if not title or not link:
                continue

            published = _coerce_publication_date(paper.get("publicationDate"), paper.get("year"))
            # Weekly runs only enforce the exact window here, so keep backend-side filtering strict.
            if published is None or published < start_date or published > end_date:
                continue

            item_id = sha1(f"Semantic Scholar|{title}|{link}")
            if item_id in seen_ids:
                continue
            seen_ids.add(item_id)

            items.append({
                "id": item_id,
                "source": _paper_source(paper),
                "title": title,
                "link": link,
                "published_utc": datetime.combine(
                    published, datetime.min.time(), tzinfo=timezone.utc
                ).isoformat(),
                "summary": normalize_summary(
                    str(paper.get("abstract") or ""),
                    max_chars=SUMMARY_MAX_CHARS,
                ),
            })
            if len(items) >= SEMANTIC_SCHOLAR_MAX_ITEMS:
                break

        if len(papers) < page_size:
            break
        next_offset = data.get("next")
        if isinstance(next_offset, int) and next_offset > offset:
            offset = next_offset
        else:
            offset += page_size

    items.sort(key=lambda x: x.get("published_utc") or "", reverse=True)
    return items
