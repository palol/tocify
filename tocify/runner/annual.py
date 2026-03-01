"""Generate annual review from monthly roundups."""

import datetime as dt
from pathlib import Path

from tqdm import tqdm

from tocify.frontmatter import default_note_frontmatter, split_frontmatter_and_body, with_frontmatter
from tocify.runner.prompt_templates import load_prompt_template
from tocify.runner.roundup_common import (
    build_allowed_url_index_from_sources,
    collect_source_metadata,
    sanitize_output_links,
)
from tocify.runner.vault import (
    get_topic_paths,
    load_monthly_roundups_for_year,
    run_agent_and_save_output,
    VAULT_ROOT,
)

def _apply_annual_frontmatter(
    output_path: Path,
    *,
    year: int,
    topic: str,
    source_roundups: list[Path],
) -> None:
    raw = output_path.read_text(encoding="utf-8") if output_path.exists() else ""
    _, body = split_frontmatter_and_body(raw)
    source_meta = collect_source_metadata(source_roundups)
    frontmatter = default_note_frontmatter()
    frontmatter.update({
        "title": output_path.stem,
        "date": f"{year}-12-31",
        "date created": f"{year}-12-31 00:00:00",
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
    })
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
    allowed_source_url_index = build_allowed_url_index_from_sources(roundup_paths)

    if len(roundup_paths) < 12:
        tqdm.write(f"[WARN] Only {len(roundup_paths)} monthly roundups for {year} (partial year)")

    output_path = output or paths.yearly_dir / f"{year} review.md"
    log_path = paths.logs_dir / f"{year}_{topic}_annual-review.log.md"

    paths.yearly_dir.mkdir(parents=True, exist_ok=True)
    paths.logs_dir.mkdir(parents=True, exist_ok=True)

    print(f"[INFO] Generating annual review for {year} from {len(roundup_paths)} monthly roundups")

    no_content_fallback = f"# {topic.upper()} Annual Review — {year}\n\n*No content produced.*\n"

    annual_template = load_prompt_template(
        "annual_review_prompt.txt", paths.annual_prompt_path
    )
    roundup_refs = "\n".join(f"@{p}" for p in roundup_paths)
    prompt = annual_template.format(
        year=year,
        roundup_refs=roundup_refs,
        topic_upper=topic.upper(),
        output_path=str(output_path.resolve()),
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

    link_stats = sanitize_output_links(output_path, allowed_source_url_index)
    print(
        "[INFO] Link hygiene: "
        f"kept={link_stats['kept']}, "
        f"rewritten={link_stats['rewritten']}, "
        f"html_converted={link_stats['html_converted']}, "
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

    from tocify.markdown_lint import lint_file

    lint_file(output_path)

    print(f"[DONE] Wrote annual review to {output_path} and log to {log_path}")
