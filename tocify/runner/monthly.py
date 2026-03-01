"""Generate monthly roundup from weekly briefs (no inbox)."""

import datetime as dt
from pathlib import Path

from tqdm import tqdm

from tocify.frontmatter import default_note_frontmatter, split_frontmatter_and_body, with_frontmatter
from tocify.runner.roundup_common import (
    build_allowed_url_index_from_sources,
    collect_source_metadata,
    sanitize_output_links,
)
from tocify.runner.nav_wikilinks import ensure_trailing_monthly_nav
from tocify.runner.prompt_templates import load_prompt_template
from tocify.runner.vault import (
    get_topic_paths,
    load_briefs_for_date_range,
    run_agent_and_save_output,
    VAULT_ROOT,
)
from tocify.runner.weeks import get_month_metadata

def _apply_monthly_frontmatter(
    output_path: Path,
    *,
    topic: str,
    month_name: str,
    month_iso: str,
    end_date: dt.date,
    source_briefs: list[Path],
) -> None:
    raw = output_path.read_text(encoding="utf-8") if output_path.exists() else ""
    _, body = split_frontmatter_and_body(raw)
    body = ensure_trailing_monthly_nav(body, month_iso)
    source_meta = collect_source_metadata(source_briefs)
    frontmatter = default_note_frontmatter()
    frontmatter.update({
        "title": output_path.stem,
        "date": end_date.isoformat(),
        "date created": f"{end_date.isoformat()} 00:00:00",
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
    })
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
    allowed_source_url_index = build_allowed_url_index_from_sources(brief_paths)

    paths.monthly_dir.mkdir(parents=True, exist_ok=True)
    paths.logs_dir.mkdir(parents=True, exist_ok=True)
    month_name = end_date.strftime("%B %Y")
    month_iso = end_date.strftime("%Y-%m")
    roundup_filename = paths.monthly_dir / f"{month_iso}.md"
    log_filename = paths.logs_dir / f"{end_date.isoformat()}_{topic}_monthly-roundup.log.md"
    fallback_content = f"# {topic.upper()} Monthly Roundup — {month_name}\n\n*No briefs found for this period.*\n"

    if not brief_paths:
        roundup_filename.write_text(fallback_content, encoding="utf-8")
        log_filename.write_text("No briefs to process.", encoding="utf-8")
    else:
        roundup_template = load_prompt_template(
            "monthly_roundup_prompt.txt", paths.monthly_prompt_path
        )
        brief_refs = "\n".join(f"@{p}" for p in brief_paths)
        prompt = roundup_template.format(
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
            month_name=month_name,
            brief_refs=brief_refs,
            topic_upper=topic.upper(),
            output_path=str(roundup_filename.resolve()),
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

    link_stats = sanitize_output_links(roundup_filename, allowed_source_url_index)
    print(
        "[INFO] Link hygiene: "
        f"kept={link_stats['kept']}, "
        f"rewritten={link_stats['rewritten']}, "
        f"html_converted={link_stats['html_converted']}, "
        f"delinked={link_stats['delinked']}, "
        f"invalid={link_stats['invalid']}, "
        f"unmatched={link_stats['unmatched']}"
    )

    _apply_monthly_frontmatter(
        roundup_filename,
        topic=topic,
        month_name=month_name,
        month_iso=month_iso,
        end_date=end_date,
        source_briefs=brief_paths,
    )

    from tocify.markdown_lint import lint_file

    lint_file(roundup_filename)

    print(f"[DONE] Wrote monthly roundup to {roundup_filename} and log to {log_filename}")
