"""Shared helpers used by digest, news, and historical modules."""

import hashlib
import html
import re


def sha1(s: str) -> str:
    """Return SHA-1 hex digest of the string."""
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


_HTML_TAG_RE = re.compile(r"<[^>]+>")


def html_to_plain_text(s: str) -> str:
    """Extract plain text from HTML. Uses lxml when possible; falls back to regex + unescape on parse failure."""
    if not (s or "").strip():
        return ""
    try:
        from lxml import html as lxml_html

        root = lxml_html.fromstring(s)
        return (root.text_content() or "").strip()
    except Exception:
        text = _HTML_TAG_RE.sub(" ", str(s))
        return html.unescape(text).strip()


def normalize_summary(text: str, max_chars: int = 500, *, strip_html: bool = True) -> str:
    """Collapse whitespace, strip, and truncate to max_chars with ellipsis.

    When strip_html is True (default), HTML is converted to plain text first so
    truncation never produces broken tags (parse5-safe for briefs).
    """
    raw = (text or "").strip()
    if strip_html and raw:
        raw = html_to_plain_text(raw)
    s = re.sub(r"\s+", " ", raw).strip()
    if len(s) > max_chars:
        s = s[:max_chars] + "…"
    return s
