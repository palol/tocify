"""Weekly digest for one topic: fetch (tocify), prefilter, triage, topic redundancy, gardener, brief + CSV."""

import csv
import importlib.util
import json
import math
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import date, datetime, time as dt_time, timezone, timedelta
from pathlib import Path
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

from dotenv import load_dotenv
try:
    from newspaper import Article
except Exception:  # pragma: no cover - optional dependency
    Article = None

import tocify
from tocify.frontmatter import (
    aggregate_ranked_item_tags,
    normalize_ai_tags,
    split_frontmatter_and_body,
    with_frontmatter,
)
from tocify.runner.vault import VAULT_ROOT, get_topic_paths, run_structured_prompt

load_dotenv()

# Env (same names as neural-noise / tocify)
MAX_ITEMS_PER_FEED = int(os.getenv("MAX_ITEMS_PER_FEED", "50"))
MAX_TOTAL_ITEMS = int(os.getenv("MAX_TOTAL_ITEMS", "400"))
LOOKBACK_DAYS = int(os.getenv("LOOKBACK_DAYS", "7"))
SUMMARY_MAX_CHARS = int(os.getenv("SUMMARY_MAX_CHARS", "500"))
PREFILTER_KEEP_TOP = int(os.getenv("PREFILTER_KEEP_TOP", "200"))
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "50"))
MIN_SCORE_READ = float(os.getenv("MIN_SCORE_READ", "0.65"))
MAX_RETURNED = int(os.getenv("MAX_RETURNED", "40"))
USE_NEWSPAPER = os.getenv("USE_NEWSPAPER", "0").strip().lower() in ("1", "true", "yes")
NEWSPAPER_MAX_ITEMS = int(os.getenv("NEWSPAPER_MAX_ITEMS", "100"))
NEWSPAPER_TIMEOUT = int(os.getenv("NEWSPAPER_TIMEOUT", "10"))
TOPIC_REDUNDANCY_ENABLED = os.getenv("TOPIC_REDUNDANCY", "1").strip().lower() in ("1", "true", "yes")
TOPIC_REDUNDANCY_LOOKBACK_DAYS = int(os.getenv("TOPIC_REDUNDANCY_LOOKBACK_DAYS", "56"))
TOPIC_REDUNDANCY_BATCH_SIZE = int(os.getenv("TOPIC_REDUNDANCY_BATCH_SIZE", "25"))
TOPIC_GARDENER_ENABLED = os.getenv("TOPIC_GARDENER", "1").strip().lower() in ("1", "true", "yes")

BRIEFS_ARTICLES_COLUMNS = [
    "topic", "week_of", "url", "title", "source", "published_utc", "score", "brief_filename",
    "why", "tags",
]

TRACKING_PARAMS = frozenset({
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "msclkid", "ref", "mc_cid", "mc_eid", "_ga",
})
URL_IN_TEXT_RE = re.compile(r"https?://[^\s<>()\]\}]+", re.IGNORECASE)
FOOTNOTE_DEF_LINE_RE = re.compile(r"^\[\^(\d+)\]:\s*(\S+)\s*$")
FOOTNOTE_MARKER_RE = re.compile(r"\[\^(\d+)\]")
MENTIONS_SUFFIX_RE = re.compile(r"\s*_\(\s*mentions:\s*\d+\s+sources?\s*\)_\s*$", re.IGNORECASE)


def parse_week_spec(s: str) -> str:
    """Parse 'YYYY week N' (ISO week); return Monday of that week as YYYY-MM-DD."""
    s = (s or "").strip()
    m = re.match(r"^(\d{4})\s+week\s+(\d+)$", s, re.IGNORECASE)
    if not m:
        raise ValueError(f"Invalid week spec: expected 'YYYY week N', got {s!r}")
    year, week = int(m.group(1)), int(m.group(2))
    if week < 1 or week > 53:
        raise ValueError(f"Invalid ISO week number: {week} (must be 1-53)")
    d = date.fromisocalendar(year, week, 1)
    return d.isoformat()


def normalize_url_for_dedup(url: str) -> str:
    if not (url or url.strip()):
        return ""
    s = url.strip()
    parsed = urlparse(s)
    query = parse_qs(parsed.query, keep_blank_values=False)
    filtered = {k: v for k, v in query.items() if k.lower() not in TRACKING_PARAMS}
    new_query = urlencode(sorted(filtered.items()), doseq=True)
    no_fragment = parsed._replace(query=new_query, fragment="")
    return urlunparse(no_fragment)


def load_briefs_articles_urls(csv_path: Path, topic: str | None = None) -> set[str]:
    seen = set()
    if not csv_path.exists():
        return seen
    with open(csv_path, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        if "url" not in fieldnames:
            return seen
        has_topic_col = "topic" in fieldnames
        for row in reader:
            if topic is not None and has_topic_col and (row.get("topic") or "").strip() != topic:
                continue
            u = (row.get("url") or "").strip()
            if u:
                seen.add(normalize_url_for_dedup(u))
    return seen


def load_recent_topic_files(topics_dir: Path, max_age_days: int) -> list[Path]:
    if not topics_dir.exists() or max_age_days <= 0:
        return []
    now = datetime.now(timezone.utc)
    cutoff_ts = (now - timedelta(days=max_age_days)).timestamp()
    out = []
    for p in topics_dir.glob("*.md"):
        if not p.is_file():
            continue
        try:
            if p.stat().st_mtime >= cutoff_ts:
                out.append(p)
        except OSError:
            continue
    out.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return out


def enrich_item_with_newspaper(item: dict, timeout: int) -> dict:
    if Article is None:
        return item
    link = (item.get("link") or "").strip()
    if not link:
        return item

    def download_and_parse():
        article = Article(link)
        article.download()
        article.parse()
        return article.text or ""

    try:
        with ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(download_and_parse)
            text = fut.result(timeout=timeout)
    except (FuturesTimeoutError, Exception):
        return item

    text = re.sub(r"\s+", " ", (text or "").strip())
    if not text:
        return item
    if len(text) > SUMMARY_MAX_CHARS:
        text = text[:SUMMARY_MAX_CHARS] + "…"
    item["summary"] = text
    return item


# ---- topic redundancy ----
TOPIC_REDUNDANCY_PROMPT = """You have reference topic documents (each summarizes a story or theme we already cover in our newsletter). Below are candidate RSS items.

For each candidate item:
1. Which topic file, if any, does this article belong to? (same story or theme)
2. If it matches a topic: does this article add **new knowledge** beyond what the topic summary and its sources already cover?

If an item matches a topic AND does **not** add new knowledge, it is redundant and should be excluded from the brief.

Reference topic documents:
{topic_refs}

Candidate RSS items:
{items_json}

Return **only** a single JSON object, no markdown code fences, no commentary. Schema:
{{"redundant_ids": ["<id1>", "<id2>", ...], "redundant_mentions": [{{"id": "<id>", "topic_slug": "<slug>", "matched_fact_bullet": "- <exact bullet line from topic file>", "source_url": "<article url>"}}]}}
Rules for redundant_mentions:
- Include one record only when the item is redundant due to repeated knowledge already captured by a specific topic fact bullet.
- `matched_fact_bullet` must copy the exact bullet line from the topic markdown.
- Ignore YAML frontmatter fields and footnote definition lines (e.g., `[^1]: https://...`) during matching.
- `source_url` should be the candidate item's link URL.
- If no repeated-fact match is available, use an empty list.
List the "id" of each candidate item that is redundant."""

TOPIC_REDUNDANCY_SCHEMA = {
    "type": "object",
    "properties": {
        "redundant_ids": {"type": "array", "items": {"type": "string"}},
        "redundant_mentions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "topic_slug": {"type": "string"},
                    "matched_fact_bullet": {"type": "string"},
                    "source_url": {"type": "string"},
                },
                "required": ["id", "topic_slug", "matched_fact_bullet", "source_url"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["redundant_ids", "redundant_mentions"],
    "additionalProperties": False,
}


def _sanitize_topic_body_for_redundancy(body: str) -> str:
    lines: list[str] = []
    for raw_line in (body or "").splitlines():
        if FOOTNOTE_DEF_LINE_RE.match(raw_line.strip()):
            continue
        lines.append(raw_line.rstrip())
    return "\n".join(lines).strip()


def _render_topic_refs_for_redundancy(topic_paths: list[Path]) -> str:
    refs: list[str] = []
    for path in topic_paths:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        _, body = split_frontmatter_and_body(text)
        sanitized = _sanitize_topic_body_for_redundancy(body)
        if not sanitized:
            continue
        refs.append(
            f"[BEGIN TOPIC: {path.stem} @ {path.resolve()}]\n"
            f"{sanitized}\n"
            f"[END TOPIC: {path.stem}]"
        )
    return "\n\n".join(refs)


def _call_cursor_topic_redundancy(
    topic_paths: list[Path], items: list[dict], allowed_source_url_index: dict[str, str] | None = None
) -> tuple[set[str], list[dict]]:
    if not topic_paths or not items:
        return set(), []
    if allowed_source_url_index is None:
        allowed_source_url_index = _build_allowed_source_url_index(items)
    topic_refs = _render_topic_refs_for_redundancy(topic_paths) or "(no readable topic content)"
    lean_items = [
        {
            "id": it["id"],
            "title": it.get("title", ""),
            "link": it.get("link", ""),
            "source": it.get("source", ""),
            "summary": (it.get("summary") or "")[:SUMMARY_MAX_CHARS],
        }
        for it in items
    ]
    prompt = TOPIC_REDUNDANCY_PROMPT.format(
        topic_refs=topic_refs,
        items_json=json.dumps(lean_items, ensure_ascii=False),
    )
    try:
        parsed = run_structured_prompt(
            prompt,
            schema=TOPIC_REDUNDANCY_SCHEMA,
            purpose="topic-redundancy",
            trust=True,
        )
    except ValueError:
        return set(), []
    redundant = parsed.get("redundant_ids")
    if not isinstance(redundant, list):
        redundant_ids: set[str] = set()
    else:
        redundant_ids = {str(x).strip() for x in redundant if str(x).strip()}

    item_by_id = {str(it.get("id") or "").strip(): it for it in items}
    mentions: list[dict] = []
    raw_mentions = parsed.get("redundant_mentions")
    if isinstance(raw_mentions, list):
        for raw in raw_mentions:
            if not isinstance(raw, dict):
                continue
            item_id = str(raw.get("id") or "").strip()
            if not item_id or item_id not in item_by_id:
                continue
            topic_slug = str(raw.get("topic_slug") or "").strip()
            matched_fact_bullet = str(raw.get("matched_fact_bullet") or "").strip()
            source_url = _resolve_allowed_source_url(
                str(raw.get("source_url") or "").strip(),
                str(item_by_id[item_id].get("link") or "").strip(),
                allowed_source_url_index,
            )
            if not topic_slug or not matched_fact_bullet or not source_url:
                continue
            mentions.append(
                {
                    "id": item_id,
                    "topic_slug": topic_slug,
                    "matched_fact_bullet": matched_fact_bullet,
                    "source_url": source_url,
                }
            )
    return redundant_ids, mentions


def _dedupe_redundant_mentions(mentions: list[dict]) -> list[dict]:
    deduped: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    for raw in mentions:
        if not isinstance(raw, dict):
            continue
        topic_slug = str(raw.get("topic_slug") or "").strip().lower()
        matched_fact_bullet = str(raw.get("matched_fact_bullet") or "").strip()
        source_url = str(raw.get("source_url") or "").strip()
        if not topic_slug or not matched_fact_bullet or not source_url:
            continue
        key = (topic_slug, matched_fact_bullet, source_url)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(
            {
                "id": str(raw.get("id") or "").strip(),
                "topic_slug": topic_slug,
                "matched_fact_bullet": matched_fact_bullet,
                "source_url": source_url,
            }
        )
    return deduped


def filter_topic_redundant_items(
    topic_paths: list[Path],
    items: list[dict],
    batch_size: int,
    allowed_source_url_index: dict[str, str] | None = None,
) -> tuple[list[dict], int, list[dict]]:
    if not topic_paths or not items:
        return items, 0, []
    if allowed_source_url_index is None:
        allowed_source_url_index = _build_allowed_source_url_index(items)
    all_redundant: set[str] = set()
    all_mentions: list[dict] = []
    for i in range(0, len(items), batch_size):
        batch = items[i : i + batch_size]
        redundant, mentions = _call_cursor_topic_redundancy(
            topic_paths, batch, allowed_source_url_index=allowed_source_url_index
        )
        all_redundant |= redundant
        all_mentions.extend([m for m in mentions if str(m.get("id") or "").strip() in redundant])
    kept = [it for it in items if it["id"] not in all_redundant]
    return kept, len(items) - len(kept), _dedupe_redundant_mentions(all_mentions)


# ---- topic gardener ----
TOPIC_GARDENER_PROMPT = """You are curating a **global digital garden** of evergreen topic pages.

Below are (1) this week's weekly brief, and (2) existing topic files. Propose **create** or **update** actions.

Rules:
- **create**: New topic when the brief introduces a distinct theme. Use lowercase-hyphen slug. Include title, body_markdown, sources, links_to, tags.
  - `body_markdown` must be a **fact bullet list** (`- Fact...`), not prose paragraphs.
- **update**: When an item adds to an existing topic. Provide slug, append_sources, optionally summary_addendum and tags.
  - `summary_addendum` must be a **fact bullet list** (`- Fact...`) when present.
- Every markdown text addition must include source attribution using markdown footnotes with URL definitions, e.g. [^1] and [^1]: https://example.com.

This week's brief (category: {topic}):
{brief_content}

Existing topic files (slug and preview):
{existing_topics}

Return **only** a single JSON object. Schema:
{{"topic_actions": [{{ "action": "create" | "update", "slug": "<slug>", "title": "<title>", "body_markdown": "<markdown>", "sources": ["url"], "links_to": ["slug"], "append_sources": ["url"], "summary_addendum": "<markdown>", "tags": ["tag"] }}]}}
Bullet examples for markdown fields:
- body_markdown: "- Fact one.\\n- Fact two."
- summary_addendum: "- New finding one.\\n- New finding two."
Omit topic_actions or use [] if nothing to do."""

TOPIC_GARDENER_SCHEMA = {
    "type": "object",
    "properties": {
        "topic_actions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["create", "update"]},
                    "slug": {"type": "string"},
                    "title": {"type": ["string", "null"]},
                    "body_markdown": {"type": ["string", "null"]},
                    "sources": {"type": ["array", "null"], "items": {"type": "string"}},
                    "links_to": {"type": ["array", "null"], "items": {"type": "string"}},
                    "append_sources": {"type": ["array", "null"], "items": {"type": "string"}},
                    "summary_addendum": {"type": ["string", "null"]},
                    "tags": {"type": ["array", "null"], "items": {"type": "string"}},
                },
                "required": [
                    "action",
                    "slug",
                    "title",
                    "body_markdown",
                    "sources",
                    "links_to",
                    "append_sources",
                    "summary_addendum",
                    "tags",
                ],
                "additionalProperties": False,
            },
        },
    },
    "required": ["topic_actions"],
    "additionalProperties": False,
}


def _dedupe_urls(urls: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in urls:
        u = str(raw).strip()
        if not u:
            continue
        if u in seen:
            continue
        seen.add(u)
        out.append(u)
    return out


def _build_allowed_source_url_index(items: list[dict]) -> dict[str, str]:
    """Map normalized URL -> canonical metadata URL from item links."""
    index: dict[str, str] = {}
    for item in items:
        link = str(item.get("link") or "").strip()
        norm = normalize_url_for_dedup(link)
        if not norm or norm in index:
            continue
        index[norm] = link
    return index


def _filter_urls_to_allowed(urls: list[str], allowed_source_url_index: dict[str, str] | None) -> list[str]:
    deduped = _dedupe_urls(urls)
    if allowed_source_url_index is None:
        return deduped
    out: list[str] = []
    seen_norm: set[str] = set()
    for raw in deduped:
        norm = normalize_url_for_dedup(raw)
        if not norm:
            continue
        canonical = allowed_source_url_index.get(norm)
        if not canonical or norm in seen_norm:
            continue
        seen_norm.add(norm)
        out.append(canonical)
    return out


def _resolve_allowed_source_url(
    source_url: str, item_link: str, allowed_source_url_index: dict[str, str] | None
) -> str:
    if allowed_source_url_index is None:
        return (source_url or "").strip() or (item_link or "").strip()
    for raw in (source_url, item_link):
        candidate = str(raw or "").strip()
        if not candidate:
            continue
        norm = normalize_url_for_dedup(candidate)
        if not norm:
            continue
        canonical = allowed_source_url_index.get(norm)
        if canonical:
            return canonical
    return ""


def _extract_urls_from_markdown(text: str) -> list[str]:
    urls = []
    for m in URL_IN_TEXT_RE.findall(text or ""):
        u = m.rstrip(".,;:!?)\"'")
        if u:
            urls.append(u)
    return _dedupe_urls(urls)


def _string_list(value) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(v).strip() for v in value if str(v).strip()]


def _merge_unique(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = str(raw or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _extract_brief_metadata(brief_path: Path) -> dict:
    if not brief_path.exists():
        return {"tags": [], "triage_backend": "unknown", "triage_model": "unknown"}
    frontmatter, _ = split_frontmatter_and_body(brief_path.read_text(encoding="utf-8"))
    tags = normalize_ai_tags(_string_list(frontmatter.get("tags")))
    triage_backend = str(frontmatter.get("triage_backend") or "unknown").strip() or "unknown"
    triage_model = str(frontmatter.get("triage_model") or "unknown").strip() or "unknown"
    return {"tags": tags, "triage_backend": triage_backend, "triage_model": triage_model}


def _with_source_footnotes(markdown: str, source_urls: list[str]) -> str:
    body = (markdown or "").strip()
    sources = _dedupe_urls(source_urls)
    if not sources:
        return body

    markers = "".join(f"[^{i}]" for i in range(1, len(sources) + 1))
    defs = "\n".join(f"[^{i}]: {u}" for i, u in enumerate(sources, start=1))

    if body:
        return f"{body} {markers}\n\n{defs}"
    return f"{markers}\n\n{defs}"


BULLET_LINE_RE = re.compile(r"^\s*[-*+]\s+")
NUMBERED_LINE_RE = re.compile(r"^\s*\d+[.)]\s+")


def _normalize_to_fact_bullets(markdown: str) -> str:
    text = (markdown or "").strip()
    if not text:
        return ""

    facts: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if BULLET_LINE_RE.match(line):
            fact = BULLET_LINE_RE.sub("", line, count=1).strip()
            if fact:
                facts.append(fact)
            continue

        if NUMBERED_LINE_RE.match(line):
            fact = NUMBERED_LINE_RE.sub("", line, count=1).strip()
            if fact:
                facts.append(fact)
            continue

        if FOOTNOTE_DEF_LINE_RE.match(line):
            continue

        line = re.sub(r"^#{1,6}\s+", "", line).strip()
        segments = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\[])", line)
        for seg in segments:
            fact = seg.strip()
            if fact:
                facts.append(fact)

    deduped = _merge_unique(facts)
    return "\n".join(f"- {f}" for f in deduped)


def _normalize_fact_for_match(text: str) -> str:
    line = str(text or "").strip()
    line = BULLET_LINE_RE.sub("", line, count=1)
    line = NUMBERED_LINE_RE.sub("", line, count=1)
    line = FOOTNOTE_MARKER_RE.sub("", line)
    line = MENTIONS_SUFFIX_RE.sub("", line)
    line = re.sub(r"\s+", " ", line).strip().lower()
    return line


def _extract_footnote_definitions(markdown: str) -> dict[int, str]:
    definitions: dict[int, str] = {}
    for raw_line in (markdown or "").splitlines():
        m = FOOTNOTE_DEF_LINE_RE.match(raw_line.strip())
        if not m:
            continue
        idx = int(m.group(1))
        url = m.group(2).strip()
        if idx not in definitions:
            definitions[idx] = url
    return definitions


def _next_footnote_index(definitions: dict[int, str]) -> int:
    return max(definitions.keys(), default=0) + 1


def _apply_redundant_mention_to_body(body: str, matched_fact_bullet: str, source_url: str) -> tuple[str, str]:
    lines = (body or "").splitlines()
    target = _normalize_fact_for_match(matched_fact_bullet)
    if not target:
        return body, "invalid"

    bullet_idx = -1
    for idx, line in enumerate(lines):
        if not BULLET_LINE_RE.match(line):
            continue
        if _normalize_fact_for_match(line) == target:
            bullet_idx = idx
            break
    if bullet_idx < 0:
        return body, "missing_bullet"

    definitions = _extract_footnote_definitions(body)
    url_to_idx = {u: i for i, u in definitions.items()}
    source_url = str(source_url or "").strip()
    if not source_url:
        return body, "invalid"

    changed = False
    created_defs: list[tuple[int, str]] = []

    line = lines[bullet_idx]
    suffix_match = MENTIONS_SUFFIX_RE.search(line)
    line_suffix = ""
    if suffix_match:
        line_without_suffix = line[:suffix_match.start()].rstrip()
        line_suffix = line[suffix_match.start():]
    else:
        line_without_suffix = line.rstrip()
    marker_indices = {int(x) for x in FOOTNOTE_MARKER_RE.findall(line_without_suffix)}
    line_urls = {definitions[i] for i in marker_indices if i in definitions}

    if source_url not in line_urls:
        marker_idx = url_to_idx.get(source_url)
        if marker_idx is None:
            marker_idx = _next_footnote_index(definitions)
            definitions[marker_idx] = source_url
            url_to_idx[source_url] = marker_idx
            created_defs.append((marker_idx, source_url))
            changed = True

        marker = f"[^{marker_idx}]"
        if marker not in line_without_suffix:
            spacer = "" if re.search(r"\[\^\d+\]\s*$", line_without_suffix) else " "
            line_without_suffix = f"{line_without_suffix}{spacer}{marker}"
            changed = True

    updated_line = f"{line_without_suffix}{line_suffix}"
    if updated_line != line:
        lines[bullet_idx] = updated_line
        changed = True

    if not changed:
        return body, "already_recorded"

    updated_body = "\n".join(lines)
    if created_defs:
        defs_block = "\n".join(f"[^{idx}]: {url}" for idx, url in created_defs)
        updated_body = f"{updated_body.rstrip()}\n\n{defs_block}"
    return updated_body, "applied"


def _apply_redundant_mentions(topics_dir: Path, mentions: list[dict], today: str) -> dict[str, int]:
    stats = {
        "mentions_input": len(mentions),
        "mentions_applied": 0,
        "mentions_already_recorded": 0,
        "mentions_missing_topic": 0,
        "mentions_missing_bullet": 0,
        "mentions_invalid": 0,
        "files_updated": 0,
    }
    if not mentions:
        return stats

    mentions_by_slug: dict[str, list[dict]] = {}
    for raw in mentions:
        if not isinstance(raw, dict):
            stats["mentions_invalid"] += 1
            continue
        slug = re.sub(r"[^a-z0-9\-]", "", str(raw.get("topic_slug") or "").strip().lower().replace("_", "-"))
        matched_fact_bullet = str(raw.get("matched_fact_bullet") or "").strip()
        source_url = str(raw.get("source_url") or "").strip()
        if not slug or not matched_fact_bullet or not source_url:
            stats["mentions_invalid"] += 1
            continue
        mentions_by_slug.setdefault(slug, []).append(
            {
                "matched_fact_bullet": matched_fact_bullet,
                "source_url": source_url,
            }
        )

    for slug, slug_mentions in mentions_by_slug.items():
        path = topics_dir / f"{slug}.md"
        if not path.exists():
            stats["mentions_missing_topic"] += len(slug_mentions)
            continue
        content = path.read_text(encoding="utf-8")
        frontmatter, body = split_frontmatter_and_body(content)
        updated_body = body
        changed = False
        sources_to_merge: list[str] = []
        for mention in slug_mentions:
            updated_body, status = _apply_redundant_mention_to_body(
                updated_body,
                mention["matched_fact_bullet"],
                mention["source_url"],
            )
            if status == "applied":
                stats["mentions_applied"] += 1
                changed = True
                sources_to_merge.append(mention["source_url"])
            elif status == "already_recorded":
                stats["mentions_already_recorded"] += 1
            elif status == "missing_bullet":
                stats["mentions_missing_bullet"] += 1
            else:
                stats["mentions_invalid"] += 1

        if changed:
            updated_frontmatter = dict(frontmatter)
            updated_frontmatter["lastmod"] = today
            updated_frontmatter["updated"] = today
            existing_sources = _string_list(updated_frontmatter.get("sources"))
            updated_frontmatter["sources"] = _dedupe_urls(existing_sources + sources_to_merge)
            path.write_text(with_frontmatter(updated_body, updated_frontmatter), encoding="utf-8")
            stats["files_updated"] += 1

    return stats


def _list_existing_topic_previews(topics_dir: Path, max_preview_chars: int = 400) -> list[dict]:
    if not topics_dir.exists():
        return []
    out = []
    for p in sorted(topics_dir.glob("*.md")):
        if not p.is_file():
            continue
        slug = p.stem
        try:
            text = p.read_text(encoding="utf-8")
            preview = text.strip()[:max_preview_chars]
            if len(text.strip()) > max_preview_chars:
                preview += "…"
        except Exception:
            preview = ""
        out.append({"slug": slug, "preview": preview})
    return out


def _call_cursor_topic_gardener(brief_content: str, existing_topics: list[dict], topic: str) -> list[dict]:
    existing_str = "\n\n".join(
        f"- **{t['slug']}**:\n{t['preview']}" for t in existing_topics
    ) or "(no existing topics yet)"
    prompt = TOPIC_GARDENER_PROMPT.format(
        topic=topic,
        brief_content=brief_content,
        existing_topics=existing_str,
    )
    try:
        parsed = run_structured_prompt(
            prompt,
            schema=TOPIC_GARDENER_SCHEMA,
            purpose="topic-gardener",
            trust=True,
        )
    except ValueError:
        return []
    actions = parsed.get("topic_actions")
    if not isinstance(actions, list):
        return []
    return actions


def _apply_topic_action(
    topics_dir: Path,
    action: dict,
    today: str,
    *,
    default_tags: list[str] | None = None,
    topic: str | None = None,
    triage_backend: str = "unknown",
    triage_model: str = "unknown",
    allowed_source_url_index: dict[str, str] | None = None,
) -> None:
    act = (action.get("action") or "").strip().lower()
    slug = (action.get("slug") or "").strip()
    if not slug or act not in ("create", "update"):
        return
    slug = re.sub(r"[^a-z0-9\-]", "", slug.lower().replace("_", "-")) or "untitled"
    path = topics_dir / f"{slug}.md"
    default_tags = normalize_ai_tags(default_tags or [])

    if act == "create":
        title = (action.get("title") or slug).strip()
        body_markdown = _normalize_to_fact_bullets((action.get("body_markdown") or "").strip())
        sources = action.get("sources") if isinstance(action.get("sources"), list) else []
        sources = [str(s).strip() for s in sources if str(s).strip()]
        sources = _filter_urls_to_allowed(
            sources + _extract_urls_from_markdown(body_markdown),
            allowed_source_url_index,
        )
        links_to = action.get("links_to") if isinstance(action.get("links_to"), list) else []
        links_to = [str(s).strip() for s in links_to if str(s).strip()]
        action_tags = normalize_ai_tags(_string_list(action.get("tags")))
        merged_tags = normalize_ai_tags(_merge_unique(action_tags + default_tags))
        if body_markdown and not sources:
            raise ValueError("create action has body_markdown but no source URLs")
        body_with_footnotes = _with_source_footnotes(body_markdown, sources)
        frontmatter = {
            "title": title,
            "date": today,
            "lastmod": today,
            "updated": today,
            "tags": merged_tags,
            "generator": "tocify-gardener",
            "period": "evergreen",
            "topic": topic or None,
            "triage_backend": triage_backend,
            "triage_model": triage_model,
            "sources": sources,
            "links_to": links_to,
        }
        path.write_text(with_frontmatter(body_with_footnotes, frontmatter), encoding="utf-8")
        return

    if act == "update" and path.exists():
        existing_frontmatter, existing_body = split_frontmatter_and_body(path.read_text(encoding="utf-8"))
        append_sources = action.get("append_sources")
        if isinstance(append_sources, list):
            append_sources = [str(s).strip() for s in append_sources if str(s).strip()]
        else:
            append_sources = []
        append_sources = _filter_urls_to_allowed(append_sources, allowed_source_url_index)
        summary_addendum = _normalize_to_fact_bullets((action.get("summary_addendum") or "").strip())
        action_tags = normalize_ai_tags(_string_list(action.get("tags")))
        existing_tags = normalize_ai_tags(_string_list(existing_frontmatter.get("tags")))
        merged_tags = normalize_ai_tags(_merge_unique(existing_tags + action_tags + default_tags))
        to_append = []
        sources_for_summary = _filter_urls_to_allowed(
            append_sources + _extract_urls_from_markdown(summary_addendum),
            allowed_source_url_index,
        )
        if summary_addendum:
            if not sources_for_summary:
                raise ValueError("update action has summary_addendum but no source URLs")
            summary_with_footnotes = _with_source_footnotes(summary_addendum, sources_for_summary)
            to_append.append(f"\n\n## Recent update ({today})\n\n{summary_with_footnotes}")
        elif append_sources:
            source_note = _with_source_footnotes(_normalize_to_fact_bullets("Source refresh."), append_sources)
            to_append.append(f"\n\n## Recent update ({today})\n\n{source_note}")
        if append_sources:
            to_append.append("\n\n### New sources\n\n" + "\n".join(f"- {u}" for u in append_sources))
        updated_body = existing_body + "".join(to_append)
        existing_sources = _string_list(existing_frontmatter.get("sources"))
        merged_sources = _dedupe_urls(existing_sources + sources_for_summary)
        frontmatter = dict(existing_frontmatter)
        frontmatter["title"] = str(frontmatter.get("title") or slug).strip() or slug
        frontmatter["date"] = str(frontmatter.get("date") or today)
        frontmatter["lastmod"] = today
        frontmatter["updated"] = today
        frontmatter["tags"] = merged_tags
        frontmatter["generator"] = "tocify-gardener"
        frontmatter["period"] = str(frontmatter.get("period") or "evergreen")
        frontmatter["topic"] = topic or frontmatter.get("topic")
        frontmatter["triage_backend"] = triage_backend or str(frontmatter.get("triage_backend") or "unknown")
        frontmatter["triage_model"] = triage_model or str(frontmatter.get("triage_model") or "unknown")
        frontmatter["sources"] = merged_sources
        links_to = _string_list(frontmatter.get("links_to"))
        frontmatter["links_to"] = links_to
        path.write_text(with_frontmatter(updated_body, frontmatter), encoding="utf-8")


def run_topic_gardener(
    topics_dir: Path,
    brief_path: Path,
    topic: str,
    allowed_source_url_index: dict[str, str] | None = None,
) -> None:
    topics_dir.mkdir(parents=True, exist_ok=True)
    if not brief_path.exists():
        return
    brief_content = brief_path.read_text(encoding="utf-8")
    brief_meta = _extract_brief_metadata(brief_path)
    existing_topics = _list_existing_topic_previews(topics_dir)
    actions = _call_cursor_topic_gardener(brief_content, existing_topics, topic)
    today = datetime.now(timezone.utc).date().isoformat()
    applied = 0
    for a in actions:
        if not isinstance(a, dict):
            continue
        try:
            _apply_topic_action(
                topics_dir,
                a,
                today,
                default_tags=brief_meta["tags"],
                topic=topic,
                triage_backend=brief_meta["triage_backend"],
                triage_model=brief_meta["triage_model"],
                allowed_source_url_index=allowed_source_url_index,
            )
            applied += 1
        except Exception as e:
            print(f"[WARN] Topic gardener: failed to apply action {a.get('slug', '?')}: {e}")
    if applied > 0:
        print(f"Topic gardener: applied {applied} topic action(s) under {topics_dir}")


def render_brief_md(
    result: dict, items_by_id: dict[str, dict], kept: list[dict], topic: str
) -> str:
    week_of = result["week_of"]
    notes = result.get("notes", "").strip()
    ranked = result.get("ranked", [])
    today = datetime.now(timezone.utc).date().isoformat()
    title = f"{topic.upper()} Weekly Brief (week of {week_of})"
    triage_backend = str(result.get("triage_backend") or "unknown")
    triage_model = str(result.get("triage_model") or "unknown")

    lines = [f"# {title}", ""]
    if notes:
        lines += [notes, ""]
    lines += [
        f"**Included:** {len(kept)} (score ≥ {MIN_SCORE_READ:.2f})  ",
        f"**Scored:** {len(ranked)} total items",
        "",
        "---",
        "",
    ]
    if not kept:
        return "\n".join(lines + ["_No items met the relevance threshold this week._", ""])

    for r in kept:
        it = items_by_id.get(r["id"], {})
        tags = ", ".join(r.get("tags", [])) if r.get("tags") else ""
        pub = r.get("published_utc")
        summary = (it.get("summary") or "").strip()
        lines += [
            f"## [{r['title']}]({r['link']})",
            f"*{r['source']}*  ",
            f"Score: **{r['score']:.2f}**" + (f"  \nPublished: {pub}" if pub else ""),
            (f"Tags: {tags}" if tags else ""),
            "",
            (r.get("why") or "").strip(),
            "",
        ]
        if summary:
            lines += ["<details>", "<summary>RSS summary</summary>", "", summary, "", "</details>", ""]
        lines += ["---", ""]
    body = "\n".join(lines)
    frontmatter = {
        "title": title,
        "date": week_of,
        "lastmod": today,
        "tags": aggregate_ranked_item_tags(kept if kept else ranked),
        "generator": "tocify-weekly",
        "period": "weekly",
        "topic": topic,
        "week_of": week_of,
        "included": len(kept),
        "scored": len(ranked),
        "triage_backend": triage_backend,
        "triage_model": triage_model,
    }
    return with_frontmatter(body, frontmatter)


def _load_weekly_link_resolver():
    try:
        from tocify.runner.link_resolution import resolve_weekly_heading_links

        return resolve_weekly_heading_links
    except Exception:
        module_path = Path(__file__).resolve().with_name("link_resolution.py")
        spec = importlib.util.spec_from_file_location("tocify_runner_link_resolution_runtime", module_path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Failed to load link resolver module at {module_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.resolve_weekly_heading_links


def _build_weekly_link_metadata_rows(
    brief_filename: str, kept: list[dict], items_by_id: dict[str, dict]
) -> list[dict]:
    rows: list[dict] = []
    for ranked in kept:
        item = items_by_id.get(ranked.get("id"), {})
        title = str(ranked.get("title") or item.get("title") or "").strip()
        if not title:
            continue
        canonical_url = str(item.get("link") or "").strip()
        fallback_url = str(ranked.get("link") or "").strip()
        url = canonical_url or fallback_url
        if not url:
            continue
        rows.append(
            {
                "brief_filename": brief_filename,
                "title": title,
                "url": url,
            }
        )
    return rows


def _resolve_weekly_heading_links(md: str, brief_filename: str, rows: list[dict]) -> tuple[str, dict]:
    resolver = _load_weekly_link_resolver()
    return resolver(md, brief_filename, rows)


def append_briefs_articles(
    csv_path: Path,
    topic: str,
    week_of: str,
    kept: list[dict],
    items_by_id: dict[str, dict],
    brief_filename: str,
) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    file_exists = csv_path.exists()
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=BRIEFS_ARTICLES_COLUMNS)
        if not file_exists:
            writer.writeheader()
        for r in kept:
            it = items_by_id.get(r["id"], {})
            row = {
                "topic": topic,
                "week_of": week_of,
                "url": r.get("link") or it.get("link", ""),
                "title": r.get("title") or it.get("title", ""),
                "source": r.get("source") or it.get("source", ""),
                "published_utc": r.get("published_utc") or it.get("published_utc") or "",
                "score": str(r.get("score", "")),
                "brief_filename": brief_filename,
                "why": (r.get("why") or "").strip().replace("\n", " "),
                "tags": "|".join(r.get("tags") or []),
            }
            writer.writerow(row)


def run_weekly(
    topic: str,
    week_spec: str | None = None,
    dry_run: int = 0,
    vault_root: Path | None = None,
) -> None:
    """Run weekly digest for one topic. Uses tocify for fetch/prefilter/triage/render params; runner adds vault, redundancy, gardener."""
    root = vault_root or VAULT_ROOT
    paths = get_topic_paths(topic, vault_root=root)
    if not paths.feeds_path.exists():
        raise FileNotFoundError(f"Feeds file not found: {paths.feeds_path}")
    if not paths.interests_path.exists():
        raise FileNotFoundError(f"Interests file not found: {paths.interests_path}")
    if not paths.prompt_path.exists():
        raise FileNotFoundError(f"Prompt file not found: {paths.prompt_path}")

    interests = tocify.parse_interests_md(paths.interests_path.read_text(encoding="utf-8"))
    feeds = tocify.load_feeds(str(paths.feeds_path))

    if week_spec is not None:
        week_of = parse_week_spec(week_spec)
        end_date = datetime.strptime(week_of, "%Y-%m-%d").date()
    else:
        today = datetime.now(timezone.utc).date()
        week_of = date.fromisocalendar(
            today.isocalendar()[0], today.isocalendar()[1], 1
        ).isoformat()
        end_date = None
    triage_metadata = tocify.get_triage_runtime_metadata()

    items = tocify.fetch_rss_items(feeds, end_date=end_date)
    print(f"Fetched {len(items)} RSS items (pre-filter) [topic={topic}]")

    paths.briefs_dir.mkdir(parents=True, exist_ok=True)
    brief_filename = f"{week_of}_{topic}_weekly-brief.md"
    brief_path = paths.briefs_dir / brief_filename

    if not items:
        no_items_body = (
            f"# {topic.upper()} Weekly Brief (week of {week_of})\n\n"
            f"_No RSS items found in the last {LOOKBACK_DAYS} days._\n"
        )
        no_items_frontmatter = {
            "title": f"{topic.upper()} Weekly Brief (week of {week_of})",
            "date": week_of,
            "lastmod": datetime.now(timezone.utc).date().isoformat(),
            "tags": [],
            "generator": "tocify-weekly",
            "period": "weekly",
            "topic": topic,
            "week_of": week_of,
            "included": 0,
            "scored": 0,
            "triage_backend": triage_metadata["triage_backend"],
            "triage_model": triage_metadata["triage_model"],
        }
        brief_path.write_text(with_frontmatter(no_items_body, no_items_frontmatter), encoding="utf-8")
        print(f"No items; wrote {brief_path}")
        return

    items = tocify.keyword_prefilter(
        items, interests["keywords"], keep_top=PREFILTER_KEEP_TOP
    )
    seen_norm = {}
    deduped = []
    for it in items:
        link = (it.get("link") or "").strip()
        norm = normalize_url_for_dedup(link)
        if norm and norm not in seen_norm:
            seen_norm[norm] = True
            deduped.append(it)
    if len(deduped) < len(items):
        print(f"Deduped by normalized URL: {len(items)} -> {len(deduped)}")
    items = deduped

    briefs_urls = load_briefs_articles_urls(paths.briefs_articles_csv, topic=topic)
    before_cross = len(items)
    items = [it for it in items if normalize_url_for_dedup((it.get("link") or "").strip()) not in briefs_urls]
    if before_cross > len(items):
        print(f"Cross-week filter: dropped {before_cross - len(items)} items, {len(items)} remaining")

    topics_dir = root / "topics"
    allowed_source_url_index = _build_allowed_source_url_index(items)
    redundant_mentions: list[dict] = []
    if TOPIC_REDUNDANCY_ENABLED and items:
        topics_dir.mkdir(parents=True, exist_ok=True)
    if TOPIC_REDUNDANCY_ENABLED and topics_dir.exists() and items:
        topic_paths = load_recent_topic_files(topics_dir, TOPIC_REDUNDANCY_LOOKBACK_DAYS)
        if topic_paths:
            print(f"Topic redundancy: checking {len(items)} items against {len(topic_paths)} topic file(s)")
            items, dropped, redundant_mentions = filter_topic_redundant_items(
                topic_paths, items, TOPIC_REDUNDANCY_BATCH_SIZE, allowed_source_url_index=allowed_source_url_index
            )
            if dropped > 0:
                print(f"Topic redundancy: dropped {dropped} items, {len(items)} remaining")
            if redundant_mentions:
                print(f"Topic redundancy: identified {len(redundant_mentions)} repeated-fact mention(s)")

    if redundant_mentions and not dry_run:
        mention_today = datetime.now(timezone.utc).date().isoformat()
        mention_stats = _apply_redundant_mentions(topics_dir, redundant_mentions, mention_today)
        print(
            "Topic redundancy mentions: "
            f"applied={mention_stats['mentions_applied']}, "
            f"already_recorded={mention_stats['mentions_already_recorded']}, "
            f"missing_topic={mention_stats['mentions_missing_topic']}, "
            f"missing_bullet={mention_stats['mentions_missing_bullet']}, "
            f"invalid={mention_stats['mentions_invalid']}, "
            f"files_updated={mention_stats['files_updated']}"
        )
    elif redundant_mentions and dry_run:
        print(f"Dry run: would apply {len(redundant_mentions)} repeated-fact mention(s) to topic pages")

    if dry_run:
        items = items[:dry_run]
        print(f"Dry run: capped to {len(items)} items (no CSV append)")

    print(f"Sending {len(items)} RSS items to model (post-filter)")

    if USE_NEWSPAPER:
        to_enrich = items[:NEWSPAPER_MAX_ITEMS]
        print(f"Enriching up to {len(to_enrich)} items with newspaper (timeout={NEWSPAPER_TIMEOUT}s each)")
        for i, it in enumerate(to_enrich):
            enrich_item_with_newspaper(it, NEWSPAPER_TIMEOUT)
            if i < len(to_enrich) - 1:
                time.sleep(0.2)
            if (i + 1) % 10 == 0:
                print(f"  Enriched {i + 1}/{len(to_enrich)}")
        print("Newspaper enrichment done")

    items_by_id = {it["id"]: it for it in items}

    os.environ["TOCIFY_PROMPT_PATH"] = str(paths.prompt_path)
    triage_fn, triage_metadata = tocify.get_triage_backend_with_metadata()
    result = tocify.triage_in_batches(interests, items, BATCH_SIZE, triage_fn)
    result["week_of"] = week_of
    result["triage_backend"] = triage_metadata["triage_backend"]
    result["triage_model"] = triage_metadata["triage_model"]

    ranked = result.get("ranked", [])
    kept = [r for r in ranked if r["score"] >= MIN_SCORE_READ][:MAX_RETURNED]
    md = render_brief_md(result, items_by_id, kept, topic)
    link_rows = _build_weekly_link_metadata_rows(brief_filename, kept, items_by_id)
    try:
        md, link_stats = _resolve_weekly_heading_links(md, brief_filename, link_rows)
        print(
            "Link resolver: "
            f"exact={link_stats['exact_matches']}, "
            f"normalized={link_stats['normalized_matches']}, "
            f"ambiguous={link_stats['ambiguous']}, "
            f"missing={link_stats['missing']}, "
            f"invalid_url={link_stats['invalid_url']}, "
            f"unchanged={link_stats['unchanged']}"
        )
    except Exception as e:
        print(f"[WARN] Link resolver failed; keeping rendered links unchanged: {e}")
    brief_path.write_text(md, encoding="utf-8")
    print(f"Wrote {brief_path}")

    if not dry_run and kept:
        append_briefs_articles(
            paths.briefs_articles_csv,
            topic,
            result["week_of"],
            kept,
            items_by_id,
            brief_filename,
        )
        print(f"Appended {len(kept)} rows to {paths.briefs_articles_csv}")

    if TOPIC_GARDENER_ENABLED and not dry_run and kept:
        topics_dir.mkdir(parents=True, exist_ok=True)
        kept_items_for_sources = [
            {"link": (r.get("link") or items_by_id.get(r.get("id"), {}).get("link") or "").strip()}
            for r in kept
        ]
        run_topic_gardener(
            topics_dir,
            brief_path,
            topic,
            allowed_source_url_index=_build_allowed_source_url_index(kept_items_for_sources),
        )
