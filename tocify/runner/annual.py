"""Generate annual review from monthly roundups."""

import argparse
import datetime as dt
from collections import Counter
from pathlib import Path

from tqdm import tqdm

from tocify.frontmatter import aggregate_ai_tags, normalize_ai_tags, split_frontmatter_and_body, with_frontmatter
from tocify.runner.link_hygiene import (
    build_allowed_url_index,
    extract_urls_from_markdown,
    sanitize_markdown_links,
)
from tocify.runner.vault import (
    get_topic_paths,
    load_monthly_roundups_for_year,
    run_agent_and_save_output,
    VAULT_ROOT,
)

ANNUAL_REVIEW_PROMPT_TEMPLATE = """You are helping an expert analyst prepare an annual review for their newsletter.

**Use the Minto Pyramid Principle: structure the review to lead with the main conclusions and storylines of the year, then organize supporting information hierarchically.**

Generate an annual review for the year {year}. Use only the following monthly roundups as your source. Do not invent content.

Monthly roundups (in chronological order):
{roundup_refs}

**IMPORTANT: Write the review to the following file path: {output_file_path}**

Format the review as follows:
1. Title: e.g. "# {topic_upper} Annual Review — {year}" and a date range subtitle
2. "## Introduction" — 2–4 paragraphs with the year's main conclusions and storylines.
3. "## Timelines" — Chronological narrative or month-by-month highlights.
4. "## Trends" — Thematic arcs across the year. Use subheadings if helpful.
5. Optional: "## Suggested Titles" — 3–5 possible newsletter titles.

Keep content comprehensive but polished. Use only information from the attached roundups."""


def _string_list(value) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(v).strip() for v in value if str(v).strip()]


def _collect_source_metadata(paths: list[Path]) -> dict:
    tag_lists: list[list[str]] = []
    backends: list[str] = []
    models: list[str] = []

    for path in paths:
        if not path.exists():
            continue
        frontmatter, _ = split_frontmatter_and_body(path.read_text(encoding="utf-8"))
        tags = normalize_ai_tags(_string_list(frontmatter.get("tags")))
        if tags:
            tag_lists.append(tags)
        backend = str(frontmatter.get("triage_backend") or "").strip()
        model = str(frontmatter.get("triage_model") or "").strip()
        if backend:
            backends.append(backend)
        if model:
            models.append(model)

    metadata: dict = {
        "tags": aggregate_ai_tags(tag_lists),
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


def _build_allowed_url_index_from_sources(paths: list[Path]) -> dict[str, str]:
    urls: list[str] = []
    for path in paths:
        if not path.exists():
            continue
        urls.extend(extract_urls_from_markdown(path.read_text(encoding="utf-8")))
    return build_allowed_url_index(urls)


def _sanitize_output_links(output_path: Path, allowed_source_url_index: dict[str, str]) -> dict:
    if not output_path.exists():
        return {"kept": 0, "rewritten": 0, "delinked": 0, "invalid": 0, "unmatched": 0}
    raw = output_path.read_text(encoding="utf-8")
    sanitized, stats = sanitize_markdown_links(raw, allowed_source_url_index)
    if sanitized != raw:
        output_path.write_text(sanitized, encoding="utf-8")
    return stats


def _apply_annual_frontmatter(
    output_path: Path,
    *,
    year: int,
    topic: str,
    source_roundups: list[Path],
) -> None:
    body = output_path.read_text(encoding="utf-8") if output_path.exists() else ""
    source_meta = _collect_source_metadata(source_roundups)
    frontmatter = {
        "title": f"{topic.upper()} Annual Review — {year}",
        "date": f"{year}-12-31",
        "lastmod": dt.datetime.now(dt.timezone.utc).date().isoformat(),
        "tags": source_meta["tags"],
        "generator": "tocify-annual",
        "period": "annual",
        "topic": topic,
        "year": year,
        "triage_backend": source_meta["triage_backend"],
        "triage_model": source_meta["triage_model"],
        "triage_backends": source_meta.get("triage_backends"),
        "triage_models": source_meta.get("triage_models"),
    }
    output_path.write_text(with_frontmatter(body, frontmatter), encoding="utf-8")


def main(
    year: int,
    topic: str = "bci",
    output: Path | None = None,
    model: str | None = None,
    vault_root: Path | None = None,
) -> None:
    root = vault_root or VAULT_ROOT
    paths = get_topic_paths(topic, vault_root=root)

    roundup_paths = load_monthly_roundups_for_year(year, topic, vault_root=root)
    if not roundup_paths:
        raise SystemExit(f"[ERROR] No monthly roundups found for year {year}")
    allowed_source_url_index = _build_allowed_url_index_from_sources(roundup_paths)

    if len(roundup_paths) < 12:
        tqdm.write(f"[WARN] Only {len(roundup_paths)} monthly roundups for {year} (partial year)")

    output_path = output or paths.briefs_dir / f"{year}_{topic}_annual-review.md"
    log_path = paths.logs_dir / f"{year}_{topic}_annual-review.log.md"

    paths.briefs_dir.mkdir(parents=True, exist_ok=True)
    paths.logs_dir.mkdir(parents=True, exist_ok=True)

    print(f"[INFO] Generating annual review for {year} from {len(roundup_paths)} monthly roundups")

    no_content_fallback = f"# {topic.upper()} Annual Review — {year}\n\n*No content produced.*\n"

    roundup_refs = "\n".join(f"@{p}" for p in roundup_paths)
    prompt = ANNUAL_REVIEW_PROMPT_TEMPLATE.format(
        year=year,
        roundup_refs=roundup_refs,
        output_file_path=str(output_path),
        topic_upper=topic.upper(),
    )

    try:
        run_agent_and_save_output(
            prompt,
            output_path,
            log_path,
            no_content_fallback,
            model=model,
        )
    except Exception as e:
        tqdm.write(f"[ERROR] Annual review generation failed: {e}")
        output_path.write_text(
            f"# {topic.upper()} Annual Review — {year}\n\n*Generation failed: {e}*\n",
            encoding="utf-8",
        )
        log_path.write_text(f"Annual review generation failed: {e}", encoding="utf-8")

    link_stats = _sanitize_output_links(output_path, allowed_source_url_index)
    print(
        "[INFO] Link hygiene: "
        f"kept={link_stats['kept']}, "
        f"rewritten={link_stats['rewritten']}, "
        f"delinked={link_stats['delinked']}, "
        f"invalid={link_stats['invalid']}, "
        f"unmatched={link_stats['unmatched']}"
    )

    _apply_annual_frontmatter(
        output_path,
        year=year,
        topic=topic,
        source_roundups=roundup_paths,
    )

    print(f"[DONE] Wrote annual review to {output_path} and log to {log_path}")


def cli() -> None:
    parser = argparse.ArgumentParser(description="Generate annual review from monthly roundups")
    parser.add_argument("--year", type=int, required=True, help="Year (e.g. 2025)")
    parser.add_argument("--model", type=str, default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--topic", type=str, default="bci")
    parser.add_argument("--vault", type=Path, default=None)
    args = parser.parse_args()
    main(
        year=args.year,
        topic=args.topic,
        output=args.output,
        model=args.model,
        vault_root=args.vault,
    )
