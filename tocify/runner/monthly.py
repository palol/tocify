"""Generate monthly roundup from weekly briefs (no inbox)."""

import argparse
import datetime as dt
from collections import Counter
from pathlib import Path

from tqdm import tqdm

from tocify.frontmatter import aggregate_ai_tags, normalize_ai_tags, split_frontmatter_and_body, with_frontmatter
from tocify.runner.vault import (
    get_topic_paths,
    load_briefs_for_date_range,
    run_agent_and_save_output,
    VAULT_ROOT,
)
from tocify.runner.weeks import get_month_metadata

ROUNDUP_PROMPT_TEMPLATE = """You are helping an expert analyst prepare a monthly roundup for their newsletter.

**Use the Minto Pyramid Principle: structure the roundup to lead with the main conclusions and storylines, then organize supporting information hierarchically.**

Generate a monthly roundup from the following weekly briefs. Use only these briefs as your source.

Date range: {start_date} to {end_date}
Month: {month_name}

Weekly briefs:
{brief_refs}

**IMPORTANT: Write the roundup to the following file path: {roundup_file_path}**

Format the roundup as follows:
1. Title: "# {topic_upper} Monthly Roundup — {month_name}"
2. Date range subtitle
3. "## Introduction" - 1-2 paragraphs summarizing the month's key storylines.
4. "## Suggested Titles" - 3-5 possible newsletter titles
5. Sections by theme (Papers and Prototypes, Clinical and Regulatory, Companies and Funding, Emerging Themes). Each section: summary statement then items with title, source/date, link, summary.

Keep content comprehensive but polished."""


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


def _apply_monthly_frontmatter(
    output_path: Path,
    *,
    topic: str,
    month_name: str,
    month_iso: str,
    end_date: dt.date,
    source_briefs: list[Path],
) -> None:
    body = output_path.read_text(encoding="utf-8") if output_path.exists() else ""
    source_meta = _collect_source_metadata(source_briefs)
    frontmatter = {
        "title": f"{topic.upper()} Monthly Roundup — {month_name}",
        "date": end_date.isoformat(),
        "lastmod": dt.datetime.now(dt.timezone.utc).date().isoformat(),
        "tags": source_meta["tags"],
        "generator": "tocify-monthly",
        "period": "monthly",
        "topic": topic,
        "month": month_iso,
        "triage_backend": source_meta["triage_backend"],
        "triage_model": source_meta["triage_model"],
        "triage_backends": source_meta.get("triage_backends"),
        "triage_models": source_meta.get("triage_models"),
    }
    output_path.write_text(with_frontmatter(body, frontmatter), encoding="utf-8")


def main(
    topic: str = "bci",
    month: str | None = None,
    end: str | None = None,
    days: int = 31,
    model: str | None = None,
    vault_root: Path | None = None,
) -> None:
    root = vault_root or VAULT_ROOT
    paths = get_topic_paths(topic, vault_root=root)

    if month:
        start_date, end_date, _ = get_month_metadata(month)
    else:
        end_date = dt.date.fromisoformat(end) if end else dt.date.today()
        end_date -= dt.timedelta(days=1)
        start_date = end_date - dt.timedelta(days=days - 1)

    print(f"[INFO] Generating monthly roundup for {start_date} to {end_date} [topic={topic}]")

    brief_paths = load_briefs_for_date_range(start_date, end_date, topic, vault_root=root)

    paths.briefs_dir.mkdir(parents=True, exist_ok=True)
    paths.logs_dir.mkdir(parents=True, exist_ok=True)
    month_name = end_date.strftime("%B %Y")
    month_iso = end_date.strftime("%Y-%m")
    roundup_filename = paths.briefs_dir / f"{end_date.isoformat()}_{topic}_monthly-roundup.md"
    log_filename = paths.logs_dir / f"{end_date.isoformat()}_{topic}_monthly-roundup.log.md"
    fallback_content = f"# {topic.upper()} Monthly Roundup — {month_name}\n\n*No briefs found for this period.*\n"

    if not brief_paths:
        roundup_filename.write_text(fallback_content, encoding="utf-8")
        log_filename.write_text("No briefs to process.", encoding="utf-8")
    else:
        brief_refs = "\n".join(f"@{p}" for p in brief_paths)
        prompt = ROUNDUP_PROMPT_TEMPLATE.format(
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
            month_name=month_name,
            brief_refs=brief_refs,
            roundup_file_path=str(roundup_filename),
            topic_upper=topic.upper(),
        )

        no_content_fallback = f"# {topic.upper()} Monthly Roundup — {month_name}\n\n*No content produced.*\n"
        try:
            run_agent_and_save_output(
                prompt,
                roundup_filename,
                log_filename,
                no_content_fallback,
                model=model,
            )
        except Exception as e:
            tqdm.write(f"[ERROR] Roundup generation failed: {e}")
            roundup_filename.write_text(
                f"# {topic.upper()} Monthly Roundup — {month_name}\n\n*Generation failed: {e}*\n",
                encoding="utf-8",
            )
            log_filename.write_text(f"Roundup generation failed: {e}", encoding="utf-8")

    _apply_monthly_frontmatter(
        roundup_filename,
        topic=topic,
        month_name=month_name,
        month_iso=month_iso,
        end_date=end_date,
        source_briefs=brief_paths,
    )

    print(f"[DONE] Wrote monthly roundup to {roundup_filename} and log to {log_filename}")


def cli() -> None:
    parser = argparse.ArgumentParser(description="Generate monthly roundup from weekly briefs")
    parser.add_argument("--month", type=str, help="Month YYYY-MM", default=None)
    parser.add_argument("--end", type=str, help="End date (ISO)", default=None)
    parser.add_argument("--days", type=int, default=31, help="Days to include (with --end)")
    parser.add_argument("--model", type=str, default=None)
    parser.add_argument("--topic", type=str, default="bci")
    parser.add_argument("--vault", type=Path, default=None, help="Vault root (default: BCI_VAULT_ROOT or .)")
    args = parser.parse_args()
    main(
        topic=args.topic,
        month=args.month,
        end=args.end,
        days=args.days,
        model=args.model,
        vault_root=args.vault,
    )
