"""Shared helpers used by digest, news, and historical modules."""

import hashlib
import re


def sha1(s: str) -> str:
    """Return SHA-1 hex digest of the string."""
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


def normalize_summary(text: str, max_chars: int = 500) -> str:
    """Collapse whitespace, strip, and truncate to max_chars with ellipsis."""
    s = re.sub(r"\s+", " ", (text or "").strip())
    if len(s) > max_chars:
        s = s[:max_chars] + "…"
    return s
