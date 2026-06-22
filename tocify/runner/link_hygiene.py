"""Shared URL extraction, normalization, and markdown link hygiene helpers."""

from __future__ import annotations

import html
import re
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

TRACKING_PARAMS = frozenset(
    {
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_term",
        "utm_content",
        "fbclid",
        "gclid",
        "msclkid",
        "ref",
        "mc_cid",
        "mc_eid",
        "_ga",
    }
)
UNVERIFIED_LINK_PLACEHOLDER = "(link removed)"

MARKDOWN_LINK_RE = re.compile(r"\[(?P<label>[^\]]+)\]\((?P<url>https?://[^)\s]+)\)")
HTML_ANCHOR_RE = re.compile(
    r"<a\b[^>]*\bhref\s*=\s*(?P<quote>[\"'])(?P<url>https?://[^\"'>\s]+)(?P=quote)[^>]*>(?P<label>.*?)</a>",
    re.IGNORECASE | re.DOTALL,
)
HTML_TAG_RE = re.compile(r"<[^>]+>")
AUTOLINK_RE = re.compile(r"<(?P<url>https?://[^>\s]+)>")
BARE_URL_RE = re.compile(r"(?<!\()(?<!<)(?P<url>https?://[^\s<>()\]\}]+)", re.IGNORECASE)


def is_valid_http_url(url: str) -> bool:
    raw = str(url or "").strip()
    if not raw:
        return False
    parsed = urlparse(raw)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def normalize_url_for_match(url: str) -> str:
    raw = str(url or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw)
    query = parse_qs(parsed.query, keep_blank_values=False)
    filtered = {k: v for k, v in query.items() if k.lower() not in TRACKING_PARAMS}
    normalized_query = urlencode(sorted(filtered.items()), doseq=True)
    cleaned = parsed._replace(query=normalized_query, fragment="")
    return urlunparse(cleaned)


def build_allowed_url_index(urls: list[str]) -> dict[str, str]:
    """Map normalized URL -> first-seen canonical URL."""
    index: dict[str, str] = {}
    for raw in urls:
        candidate = str(raw or "").strip()
        if not is_valid_http_url(candidate):
            continue
        normalized = normalize_url_for_match(candidate)
        if not normalized or normalized in index:
            continue
        index[normalized] = candidate
    return index


def _dedupe_urls(urls: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in urls:
        candidate = str(raw or "").strip()
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        out.append(candidate)
    return out


def _split_trailing_punctuation(url: str) -> tuple[str, str]:
    core = str(url or "")
    trailing = ""
    while core and core[-1] in ".,;:!?)\"'":
        trailing = core[-1] + trailing
        core = core[:-1]
    return core, trailing


def _normalize_anchor_label(label_html: str) -> str:
    text = HTML_TAG_RE.sub("", str(label_html or ""))
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _escape_markdown_link_label(label: str) -> str:
    return str(label or "").replace("[", r"\[").replace("]", r"\]")


def extract_urls_from_markdown(markdown: str) -> list[str]:
    urls: list[str] = []

    for m in MARKDOWN_LINK_RE.finditer(markdown or ""):
        url = str(m.group("url") or "").strip()
        if url:
            urls.append(url)

    for m in HTML_ANCHOR_RE.finditer(markdown or ""):
        url = str(m.group("url") or "").strip()
        if url:
            urls.append(url)

    for m in AUTOLINK_RE.finditer(markdown or ""):
        url = str(m.group("url") or "").strip()
        if url:
            urls.append(url)

    for m in BARE_URL_RE.finditer(markdown or ""):
        raw = str(m.group("url") or "").strip()
        core, _ = _split_trailing_punctuation(raw)
        if core:
            urls.append(core)

    return _dedupe_urls(urls)


def _resolve_canonical(url: str, allowed_source_url_index: dict[str, str]) -> tuple[str, str]:
    candidate = str(url or "").strip()
    if not is_valid_http_url(candidate):
        return "invalid", ""
    normalized = normalize_url_for_match(candidate)
    if not normalized:
        return "invalid", ""
    canonical = allowed_source_url_index.get(normalized)
    if canonical:
        return "trusted", canonical
    return "unmatched", ""


def sanitize_markdown_links(markdown: str, allowed_source_url_index: dict[str, str]) -> tuple[str, dict]:
    """
    Keep or canonicalize trusted links; de-link untrusted links.

    Untrusted URL text is replaced by `(link removed)` to avoid preserving filler links.
    """
    stats = {
        "kept": 0,
        "rewritten": 0,
        "html_converted": 0,
        "delinked": 0,
        "invalid": 0,
        "unmatched": 0,
    }

    def _track_untrusted(status: str) -> None:
        if status == "invalid":
            stats["invalid"] += 1
        else:
            stats["unmatched"] += 1
        stats["delinked"] += 1

    def _replace_html_anchor(match: re.Match[str]) -> str:
        label = _normalize_anchor_label(str(match.group("label") or ""))
        url = str(match.group("url") or "").strip()
        status, canonical = _resolve_canonical(url, allowed_source_url_index)
        if status != "trusted":
            _track_untrusted(status)
            return label or UNVERIFIED_LINK_PLACEHOLDER
        stats["html_converted"] += 1
        if canonical != url:
            stats["rewritten"] += 1
        markdown_label = _escape_markdown_link_label(label or canonical)
        return f"[{markdown_label}]({canonical})"

    sanitized = HTML_ANCHOR_RE.sub(_replace_html_anchor, markdown or "")

    def _replace_markdown_link(match: re.Match[str]) -> str:
        label = str(match.group("label") or "").strip()
        url = str(match.group("url") or "").strip()
        status, canonical = _resolve_canonical(url, allowed_source_url_index)
        if status != "trusted":
            _track_untrusted(status)
            return label or UNVERIFIED_LINK_PLACEHOLDER
        if canonical == url:
            stats["kept"] += 1
            return match.group(0)
        stats["rewritten"] += 1
        return f"[{label}]({canonical})"

    sanitized = MARKDOWN_LINK_RE.sub(_replace_markdown_link, sanitized)

    def _replace_autolink(match: re.Match[str]) -> str:
        url = str(match.group("url") or "").strip()
        status, canonical = _resolve_canonical(url, allowed_source_url_index)
        if status != "trusted":
            _track_untrusted(status)
            return UNVERIFIED_LINK_PLACEHOLDER
        if canonical == url:
            stats["kept"] += 1
            return match.group(0)
        stats["rewritten"] += 1
        return f"<{canonical}>"

    sanitized = AUTOLINK_RE.sub(_replace_autolink, sanitized)

    def _replace_bare(match: re.Match[str]) -> str:
        raw = str(match.group("url") or "").strip()
        core, trailing = _split_trailing_punctuation(raw)
        status, canonical = _resolve_canonical(core, allowed_source_url_index)
        if status != "trusted":
            _track_untrusted(status)
            return f"{UNVERIFIED_LINK_PLACEHOLDER}{trailing}"
        if canonical == core:
            stats["kept"] += 1
            return f"{core}{trailing}"
        stats["rewritten"] += 1
        return f"{canonical}{trailing}"

    sanitized = BARE_URL_RE.sub(_replace_bare, sanitized)
    return sanitized, stats
