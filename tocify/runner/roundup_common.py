"""Shared helpers for monthly roundup and annual review."""

from collections import Counter
from pathlib import Path

from tocify.frontmatter import aggregate_ai_tags, normalize_ai_tags, split_frontmatter_and_body
from tocify.runner.link_hygiene import (
    build_allowed_url_index,
    extract_urls_from_markdown,
    sanitize_markdown_links,
)
from tocify.runner._utils import string_list


def collect_source_metadata(paths: list[Path]) -> dict:
    """Aggregate tags and triage backend/model from source file frontmatter."""
    tag_lists: list[list[str]] = []
    backends: list[str] = []
    models: list[str] = []

    for path in paths:
        if not path.exists():
            continue
        frontmatter, _ = split_frontmatter_and_body(path.read_text(encoding="utf-8"))
        tags = normalize_ai_tags(string_list(frontmatter.get("tags")))
        if tags:
            tag_lists.append(tags)
        backend = str(frontmatter.get("triage_backend") or "").strip()
        model = str(frontmatter.get("triage_model") or "").strip()
        if backend:
            backends.append(backend)
        if model:
            models.append(model)

    tags = aggregate_ai_tags(tag_lists)
    metadata: dict = {
        "tags": tags,
        "triage_backend": "unknown",
        "triage_model": "unknown",
    }

    if backends:
        backend_counts = Counter(backends)
        backend_names = sorted(backend_counts)
        metadata["triage_backend"] = backend_names[0] if len(backend_names) == 1 else "mixed"
        if len(backend_names) > 1:
            metadata["triage_backends"] = backend_names

    if models:
        model_counts = Counter(models)
        model_names = sorted(model_counts)
        metadata["triage_model"] = model_names[0] if len(model_names) == 1 else "mixed"
        if len(model_names) > 1:
            metadata["triage_models"] = model_names

    return metadata


def build_allowed_url_index_from_sources(paths: list[Path]) -> dict[str, str]:
    """Collect all URLs from markdown in paths and return normalized -> canonical index."""
    urls: list[str] = []
    for path in paths:
        if not path.exists():
            continue
        urls.extend(extract_urls_from_markdown(path.read_text(encoding="utf-8")))
    return build_allowed_url_index(urls)


def sanitize_output_links(output_path: Path, allowed_source_url_index: dict[str, str]) -> dict:
    """Rewrite links in output_path to allowed canonicals; return stats. Mutates file if changed."""
    if not output_path.exists():
        return {"kept": 0, "rewritten": 0, "delinked": 0, "invalid": 0, "unmatched": 0}
    raw = output_path.read_text(encoding="utf-8")
    sanitized, stats = sanitize_markdown_links(raw, allowed_source_url_index)
    if sanitized != raw:
        output_path.write_text(sanitized, encoding="utf-8")
    return stats
