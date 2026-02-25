"""Resolve Google News wrapper URLs to destination publisher URLs."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import parse_qs, unquote, urlparse

import requests

GOOGLE_NEWS_QUERY_KEYS = ("url", "u", "q")
DEFAULT_REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; tocify/0.9; +https://github.com/palol/tocify)"
}


def _is_valid_http_url(url: str) -> bool:
    candidate = str(url or "").strip()
    if not candidate:
        return False
    parsed = urlparse(candidate)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def is_google_news_url(url: str) -> bool:
    parsed = urlparse(str(url or "").strip())
    host = (parsed.netloc or "").lower()
    return host == "news.google.com" or host.endswith(".news.google.com")


def _decode_url_candidate(raw_value: str) -> str:
    candidate = str(raw_value or "").strip()
    for _ in range(2):
        decoded = unquote(candidate).strip()
        if decoded == candidate:
            break
        candidate = decoded
    return candidate


def _extract_destination_from_query(url: str) -> str:
    parsed = urlparse(str(url or "").strip())
    query = parse_qs(parsed.query, keep_blank_values=False)
    for key in GOOGLE_NEWS_QUERY_KEYS:
        values = query.get(key) or query.get(key.upper())
        if not values:
            continue
        candidate = _decode_url_candidate(values[0])
        if _is_valid_http_url(candidate):
            return candidate
    return ""


def _resolve_via_redirect(url: str, timeout: int, max_redirects: int) -> str:
    session = requests.Session()
    session.max_redirects = max(1, int(max_redirects))
    try:
        response = session.get(
            url,
            timeout=max(1, int(timeout)),
            allow_redirects=True,
            headers=DEFAULT_REQUEST_HEADERS,
            stream=True,
        )
        try:
            return str(response.url or "").strip()
        finally:
            response.close()
    except requests.RequestException:
        return ""
    finally:
        session.close()


def _resolve_google_news_url_with_method(url: str, timeout: int, max_redirects: int) -> tuple[str, str]:
    original = str(url or "").strip()
    if not original or not is_google_news_url(original):
        return original, "failed"

    extracted = _extract_destination_from_query(original)
    if extracted and not is_google_news_url(extracted):
        return extracted, "query"

    redirected = _resolve_via_redirect(original, timeout, max_redirects)
    if redirected and not is_google_news_url(redirected) and _is_valid_http_url(redirected):
        return redirected, "redirect"

    redirected_extracted = _extract_destination_from_query(redirected)
    if redirected_extracted and not is_google_news_url(redirected_extracted):
        return redirected_extracted, "redirect"

    return original, "failed"


def resolve_google_news_url(url: str, *, timeout: int = 10, max_redirects: int = 10) -> str:
    """Resolve a Google News wrapper URL to the destination URL; keep original on failure."""
    resolved, _method = _resolve_google_news_url_with_method(url, timeout, max_redirects)
    return resolved


def resolve_google_news_links_in_items(
    items: list[dict],
    *,
    enabled: bool = True,
    timeout: int = 10,
    max_redirects: int = 10,
    workers: int = 8,
) -> tuple[list[dict], dict[str, int]]:
    """
    Resolve Google News links in item dicts in parallel.

    Only `item["link"]` is updated when a destination is found.
    """
    stats = {
        "attempted": 0,
        "resolved": 0,
        "query_param_resolved": 0,
        "redirect_resolved": 0,
        "failed": 0,
        "skipped_non_google": 0,
        "disabled": 0,
    }
    if not enabled:
        stats["disabled"] = 1
        return items, stats

    if not items:
        return items, stats

    google_links: list[str] = []
    for item in items:
        link = str(item.get("link") or "").strip() if isinstance(item, dict) else ""
        if is_google_news_url(link):
            google_links.append(link)
        else:
            stats["skipped_non_google"] += 1

    unique_links = list(dict.fromkeys(google_links))
    stats["attempted"] = len(unique_links)
    if not unique_links:
        return items, stats

    max_workers = min(max(1, int(workers)), len(unique_links))
    resolved_by_link: dict[str, tuple[str, str]] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_link = {
            executor.submit(_resolve_google_news_url_with_method, link, timeout, max_redirects): link
            for link in unique_links
        }
        for future in as_completed(future_to_link):
            link = future_to_link[future]
            try:
                resolved_by_link[link] = future.result()
            except Exception:
                resolved_by_link[link] = (link, "failed")

    for _link, (_resolved, method) in resolved_by_link.items():
        if method == "query":
            stats["query_param_resolved"] += 1
            stats["resolved"] += 1
        elif method == "redirect":
            stats["redirect_resolved"] += 1
            stats["resolved"] += 1
        else:
            stats["failed"] += 1

    out: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            out.append(item)
            continue
        original_link = str(item.get("link") or "").strip()
        if not is_google_news_url(original_link):
            out.append(item)
            continue
        resolved, _method = resolved_by_link.get(original_link, (original_link, "failed"))
        updated = dict(item)
        updated["link"] = resolved
        out.append(updated)
    return out, stats
