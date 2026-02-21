"""Utilities for YAML frontmatter and AI tag normalization."""

from __future__ import annotations

from collections import Counter
import re
from typing import Any

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n?", re.DOTALL)
_TAG_CLEAN_RE = re.compile(r"[^a-z0-9]+")

_FRONTMATTER_KEY_ORDER = [
    "title",
    "date",
    "lastmod",
    "updated",
    "tags",
    "generator",
    "period",
    "topic",
    "week_of",
    "month",
    "year",
    "included",
    "scored",
    "triage_backend",
    "triage_model",
    "triage_backends",
    "triage_models",
    "sources",
    "links_to",
]


def _parse_scalar(raw: str) -> Any:
    value = raw.strip()
    if value == "":
        return ""
    if value == "null":
        return None
    if value == "true":
        return True
    if value == "false":
        return False
    if value.startswith('"') and value.endswith('"') and len(value) >= 2:
        inner = value[1:-1]
        return inner.replace(r"\\", "\\").replace(r'\"', '"')
    if value.startswith("'") and value.endswith("'") and len(value) >= 2:
        return value[1:-1].replace("''", "'")
    if re.fullmatch(r"-?\d+", value):
        try:
            return int(value)
        except ValueError:
            return value
    if re.fullmatch(r"-?\d+\.\d+", value):
        try:
            return float(value)
        except ValueError:
            return value
    return value


def parse_frontmatter(text: str) -> dict[str, Any]:
    data: dict[str, Any] = {}
    current_list_key: str | None = None
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        if stripped.startswith("- "):
            if current_list_key is None:
                continue
            data.setdefault(current_list_key, [])
            if not isinstance(data[current_list_key], list):
                data[current_list_key] = []
            data[current_list_key].append(_parse_scalar(stripped[2:]))
            continue

        if ":" not in stripped:
            current_list_key = None
            continue

        key, raw_value = stripped.split(":", 1)
        key = key.strip()
        value = raw_value.strip()
        if value == "[]":
            data[key] = []
            current_list_key = None
            continue
        if value == "":
            data[key] = []
            current_list_key = key
            continue
        data[key] = _parse_scalar(value)
        current_list_key = None

    return data


def split_frontmatter_and_body(markdown: str) -> tuple[dict[str, Any], str]:
    if not markdown.startswith("---\n"):
        return {}, markdown
    match = _FRONTMATTER_RE.match(markdown)
    if not match:
        return {}, markdown
    return parse_frontmatter(match.group(1)), markdown[match.end() :]


def _yaml_quote(value: str) -> str:
    escaped = value.replace("\\", r"\\").replace('"', r'\"')
    return f'"{escaped}"'


def _yaml_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return _yaml_quote(str(value))


def _ordered_keys(data: dict[str, Any]) -> list[str]:
    fixed = [k for k in _FRONTMATTER_KEY_ORDER if k in data]
    remaining = sorted(k for k in data if k not in _FRONTMATTER_KEY_ORDER)
    return fixed + remaining


def render_frontmatter(data: dict[str, Any]) -> str:
    lines = ["---"]
    for key in _ordered_keys(data):
        value = data[key]
        if value is None:
            continue
        if isinstance(value, list):
            if not value:
                lines.append(f"{key}: []")
                continue
            lines.append(f"{key}:")
            for item in value:
                lines.append(f"  - {_yaml_scalar(item)}")
            continue
        lines.append(f"{key}: {_yaml_scalar(value)}")
    lines.append("---")
    return "\n".join(lines)


def with_frontmatter(markdown: str, frontmatter: dict[str, Any]) -> str:
    _, body = split_frontmatter_and_body(markdown)
    body = body.lstrip("\n")
    out = render_frontmatter(frontmatter)
    if body:
        out = f"{out}\n\n{body}"
    if not out.endswith("\n"):
        out += "\n"
    return out


def normalize_ai_tags(tags: list[str] | None, max_tags: int = 12) -> list[str]:
    if not tags:
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in tags:
        tag = str(raw or "").strip().lower()
        if not tag:
            continue
        tag = _TAG_CLEAN_RE.sub("-", tag)
        tag = re.sub(r"-{2,}", "-", tag).strip("-")
        if not tag or len(tag) > 64:
            continue
        if tag in seen:
            continue
        seen.add(tag)
        normalized.append(tag)
        if len(normalized) >= max_tags:
            break
    return normalized


def aggregate_ai_tags(tag_lists: list[list[str]], max_tags: int = 12) -> list[str]:
    counts: Counter[str] = Counter()
    for tags in tag_lists:
        per_doc = set(normalize_ai_tags(tags, max_tags=100))
        for tag in per_doc:
            counts[tag] += 1
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [tag for tag, _ in ranked[:max_tags]]


def aggregate_ranked_item_tags(ranked_items: list[dict[str, Any]], max_tags: int = 12) -> list[str]:
    tag_lists: list[list[str]] = []
    for item in ranked_items:
        tags = item.get("tags")
        if isinstance(tags, list):
            tag_lists.append([str(x) for x in tags])
    return aggregate_ai_tags(tag_lists, max_tags=max_tags)
