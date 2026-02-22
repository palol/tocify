"""
News backend: fetch articles by date window. Same item schema as RSS (id, source, title, link, published_utc, summary).
Used for both present flow (recent news) and weekly flow (date-range queries).

NewsAPI free tier limits the Everything endpoint to the last 30 days. For date ranges older than 30 days
results may be empty; use NewsAPI paid or omit news for older weeks. Set NEWS_API_KEY or NEWSAPI_API_KEY
in env. Enable with NEWS_BACKEND=newsapi.
"""

import os
from datetime import date, datetime, time as dt_time, timezone

import requests
from dotenv import load_dotenv

from tocify.utils import normalize_summary, sha1

load_dotenv()

SUMMARY_MAX_CHARS = int(os.getenv("SUMMARY_MAX_CHARS", "500"))
NEWS_API_TIMEOUT = int(os.getenv("NEWS_API_TIMEOUT", "30"))
NEWS_API_PAGE_SIZE = min(100, max(1, int(os.getenv("NEWS_API_PAGE_SIZE", "100"))))
NEWS_API_MAX_ITEMS = int(os.getenv("NEWS_API_MAX_ITEMS", "200"))


def fetch_news_items(
    start_date: date,
    end_date: date,
    *,
    query: str | None = None,
    api_key: str | None = None,
    language: str = "en",
) -> list[dict]:
    """
    Fetch articles from NewsAPI everything endpoint for the given date range.
    Returns list of dicts with keys: id, source, title, link, published_utc, summary
    (same schema as RSS items for merge/triage).

    start_date, end_date: inclusive date window (UTC).
    query: optional search query (q parameter); if None, uses env NEWS_API_DEFAULT_QUERY or "news" (API requires q/sources/domains).
    api_key: NewsAPI key; if None, uses env NEWS_API_KEY or NEWSAPI_API_KEY.
    """
    key = (api_key or "").strip() or os.getenv("NEWS_API_KEY", "").strip() or os.getenv("NEWSAPI_API_KEY", "").strip()
    if not key:
        return []

    today = date.today()
    if (today - end_date).days > 30:
        import warnings
        warnings.warn(
            "NewsAPI free tier typically returns articles only from the last 30 days; "
            f"end_date={end_date!s} is older. Results may be empty. Use NewsAPI paid for older dates.",
            stacklevel=2,
        )

    from_iso = datetime.combine(start_date, dt_time(0, 0, 0), tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    to_iso = datetime.combine(end_date, dt_time(23, 59, 59), tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    q_value = (query or "").strip()[:500] if (query and query.strip()) else (os.getenv("NEWS_API_DEFAULT_QUERY", "news") or "news").strip()
    params: dict = {
        "from": from_iso,
        "to": to_iso,
        "language": language,
        "sortBy": "publishedAt",
        "pageSize": NEWS_API_PAGE_SIZE,
        "apiKey": key,
        "q": q_value or "news",
    }

    items: list[dict] = []
    page = 1
    while len(items) < NEWS_API_MAX_ITEMS:
        params["page"] = page
        try:
            resp = requests.get(
                "https://newsapi.org/v2/everything",
                params=params,
                timeout=NEWS_API_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            if page == 1:
                import warnings
                msg = str(e)
                if getattr(e, "response", None) is not None:
                    resp_err = e.response
                    if resp_err.status_code >= 400:
                        try:
                            body = resp_err.json()
                            code = body.get("code", "")
                            detail = body.get("message", "")
                            if code or detail:
                                msg = f"{e} — code={code!r} message={detail!r}"
                        except Exception:
                            pass
                warnings.warn(f"NewsAPI fetch failed: {msg}", stacklevel=2)
            break

        if data.get("status") != "ok":
            break
        articles = data.get("articles") or []
        if not articles:
            break

        for a in articles:
            if len(items) >= NEWS_API_MAX_ITEMS:
                break
            title = (a.get("title") or "").strip()
            link = (a.get("url") or "").strip()
            if not title or not link:
                continue
            source_name = (a.get("source") or {})
            if isinstance(source_name, dict):
                source_name = source_name.get("name") or source_name.get("id") or "News"
            source_name = (source_name or "News").strip()
            published_at = a.get("publishedAt")
            if published_at:
                try:
                    from dateutil import parser as dtparser
                    dt = dtparser.parse(published_at)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    published_utc = dt.isoformat()
                except Exception:
                    published_utc = published_at
            else:
                published_utc = None
            description = normalize_summary(a.get("description") or a.get("content") or "", max_chars=SUMMARY_MAX_CHARS)
            item_id = sha1(f"{source_name}|{title}|{link}")
            items.append({
                "id": item_id,
                "source": source_name,
                "title": title,
                "link": link,
                "published_utc": published_utc,
                "summary": description,
            })

        if len(articles) < params["pageSize"]:
            break
        page += 1

    items.sort(key=lambda x: x["published_utc"] or "", reverse=True)
    return items
