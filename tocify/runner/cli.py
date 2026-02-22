"""CLI entrypoint: weekly, monthly, annual-review, list-topics, clear-topic, process-whole-year, calculate-weeks, init-quartz."""

import argparse
import datetime as dt
import sys
from pathlib import Path

from tqdm import tqdm

from tocify.runner.vault import list_topics, VAULT_ROOT
from tocify.runner.monthly import main as monthly_main
from tocify.runner.annual import main as annual_main
from tocify.runner.weeks import get_month_metadata, calculate_week_ends
from tocify.runner.clear import main as clear_main
from tocify.runner.quartz_init import (
    DEFAULT_QUARTZ_REF,
    DEFAULT_QUARTZ_REPO,
    init_quartz,
)
from tocify.runner.dashboard import build_dashboard


def cmd_weekly(args: argparse.Namespace) -> None:
    """Run weekly brief for args.topic and args.week_spec (fetch, triage, redundancy, gardener, brief + CSV)."""
    from tocify.runner.weekly import run_weekly

    vault = getattr(args, "vault", None)
    run_weekly(
        topic=args.topic,
        week_spec=args.week_spec,
        dry_run=args.dry_run or 0,
        vault_root=vault,
        limit=getattr(args, "limit", None),
    )


def cmd_monthly(args: argparse.Namespace) -> None:
    """Generate monthly roundup from weekly briefs for the topic."""
    monthly_main(
        topic=args.topic,
        month=getattr(args, "month", None),
        end=getattr(args, "end", None),
        days=getattr(args, "days", 31),
        model=getattr(args, "model", None),
        vault_root=getattr(args, "vault", None),
    )


def cmd_annual(args: argparse.Namespace) -> None:
    """Generate annual review from monthly roundups for the topic and year."""
    annual_main(
        year=args.year,
        topic=args.topic,
        output=getattr(args, "output", None),
        model=getattr(args, "model", None),
        vault_root=getattr(args, "vault", None),
    )


def cmd_list_topics(args: argparse.Namespace) -> None:
    """Print space-separated topic names discovered from vault config."""
    vault = getattr(args, "vault", None)
    topics = list_topics(vault_root=vault)
    print(" ".join(topics))


def cmd_clear_topic(args: argparse.Namespace) -> None:
    """Remove all briefs, logs, and CSV rows for the given topic (with optional confirmation skip)."""
    clear_main(
        args.topic,
        vault_root=getattr(args, "vault", None),
        confirm=getattr(args, "yes", False),
    )


def cmd_process_whole_year(args: argparse.Namespace) -> None:
    """Run weekly for every ISO week, then monthly for every month, then annual review."""
    from tocify.runner.weekly import run_weekly

    year = args.year
    topic = args.topic
    dry_run = getattr(args, "dry_run", False)
    vault = getattr(args, "vault", None)
    root = vault or VAULT_ROOT

    last_week = dt.date(year, 12, 28).isocalendar()[1]
    n_weeks = last_week
    n_months = 12
    total_steps = n_weeks + n_months + 1
    disable_progress = not sys.stderr.isatty()

    with tqdm(total=total_steps, desc="process-whole-year", unit="step", disable=disable_progress) as pbar:
        for week in range(1, last_week + 1):
            week_spec = f"{year} week {week}"
            pbar.set_description(f"Week {week}/{n_weeks}")
            if dry_run:
                tqdm.write(f"[DRY-RUN] weekly --topic {topic} {week_spec}")
            else:
                run_weekly(topic=topic, week_spec=week_spec, vault_root=root)
            pbar.update(1)

        for month in range(1, 13):
            month_id = f"{year}-{month:02d}"
            pbar.set_description(f"Month {month}/{n_months}")
            if dry_run:
                tqdm.write(f"[DRY-RUN] monthly --topic {topic} --month {month_id}")
            else:
                monthly_main(topic=topic, month=month_id, vault_root=root)
            pbar.update(1)

        pbar.set_description("Annual review")
        if dry_run:
            tqdm.write(f"[DRY-RUN] annual-review --topic {topic} --year {year}")
        else:
            annual_main(year=year, topic=topic, vault_root=root)
        pbar.update(1)

    if dry_run:
        tqdm.write("=== DRY-RUN complete ===")
    else:
        tqdm.write("=== Done: weekly briefs, monthly roundups, and annual review ===")


def cmd_calculate_weeks(args: argparse.Namespace) -> None:
    """Print week end dates (or first-day/last-day/days/info) for a month (YYYY-MM)."""
    import json as _json
    month = getattr(args, "month", None)
    if not month:
        print("Error: calculate-weeks requires MONTH (YYYY-MM)", file=sys.stderr)
        sys.exit(1)
    if getattr(args, "first_day", False):
        first_day, _, _ = get_month_metadata(month)
        print(first_day.isoformat())
        return
    if getattr(args, "last_day", False):
        _, last_day, _ = get_month_metadata(month)
        print(last_day.isoformat())
        return
    if getattr(args, "days", False):
        _, _, days_in_month = get_month_metadata(month)
        print(days_in_month)
        return
    if getattr(args, "info", False):
        first_day, last_day, days_in_month = get_month_metadata(month)
        print(f"FIRST_DAY={first_day.isoformat()}")
        print(f"LAST_DAY={last_day.isoformat()}")
        print(f"DAYS_IN_MONTH={days_in_month}")
        return
    week_ends = calculate_week_ends(month)
    if getattr(args, "json", False):
        print(_json.dumps(week_ends))
    else:
        print(" ".join(week_ends))


def cmd_dashboard(args: argparse.Namespace) -> None:
    """Generate articles dashboard Markdown and JSON from briefs_articles.csv."""
    vault = getattr(args, "vault", None)
    root = vault or VAULT_ROOT
    csv_path = root / "content" / "briefs_articles.csv"
    output_md = getattr(args, "output", None) or (root / "content" / "articles-dashboard.md")
    output_json = root / "public" / "articles.json"
    recent_n = getattr(args, "recent", 50)
    build_dashboard(
        csv_path,
        output_md,
        output_json,
        recent_n=recent_n,
    )
    print(f"Wrote {output_md}")
    print(f"Wrote {output_json}")


def cmd_init_quartz(args: argparse.Namespace) -> None:
    """Merge Quartz scaffold into target dir; optionally write .git/info/exclude rules."""
    try:
        result = init_quartz(
            target=args.target,
            repo_url=args.repo,
            quartz_ref=args.quartz_ref,
            overwrite=getattr(args, "overwrite", False),
            dry_run=getattr(args, "dry_run", False),
            write_local_exclude=getattr(args, "write_local_exclude", True),
        )
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    prefix = "[DRY-RUN] " if getattr(args, "dry_run", False) else ""
    print(f"{prefix}Quartz scaffold merge summary")
    print(f"target={result.target}")
    print(f"source={result.source}")
    print(f"created={len(result.created)}")
    print(f"skipped={len(result.skipped)}")
    print(f"overwritten={len(result.overwritten)}")
    if result.missing_source_paths:
        print(f"missing_source_paths={len(result.missing_source_paths)}")
    if getattr(args, "write_local_exclude", True):
        if result.local_exclude_updated:
            print(f"local_exclude=updated ({result.local_exclude_path})")
        elif result.local_exclude_would_update:
            print(f"local_exclude=would-update ({result.local_exclude_path})")
        elif result.local_exclude_path is not None:
            print(f"local_exclude=unchanged ({result.local_exclude_path})")
    for warning in result.warnings:
        print(f"warning={warning}")


def main() -> None:
    """Parse argv and dispatch to the selected subcommand (weekly, monthly, annual-review, etc.)."""
    parser = argparse.ArgumentParser(prog="tocify-runner", description="Vault/multi-topic runner for tocify")
    parser.add_argument("--vault", type=Path, default=None, help="Vault root (default: BCI_VAULT_ROOT or .)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # weekly
    p_weekly = subparsers.add_parser("weekly", help="Generate weekly brief for a topic")
    p_weekly.add_argument("--topic", type=str, default="bci")
    p_weekly.add_argument("week_spec", nargs="?", type=str, default=None, help="e.g. '2025 week 2'")
    p_weekly.add_argument("--dry-run", nargs="?", const=10, type=int, metavar="N", default=0, help="Cap to N items, no CSV append")
    p_weekly.add_argument("--limit", type=int, default=None, metavar="N", help="Cap items to N before triage (full pipeline: CSV append and gardener still run)")
    p_weekly.set_defaults(run=cmd_weekly)

    # monthly
    p_monthly = subparsers.add_parser("monthly", help="Generate monthly roundup from weekly briefs")
    p_monthly.add_argument("--topic", type=str, default="bci")
    p_monthly.add_argument("--month", type=str, default=None, help="YYYY-MM")
    p_monthly.add_argument("--end", type=str, default=None)
    p_monthly.add_argument("--days", type=int, default=31)
    p_monthly.add_argument("--model", type=str, default=None)
    p_monthly.set_defaults(run=cmd_monthly)

    # annual-review
    p_annual = subparsers.add_parser("annual-review", help="Generate annual review from monthly roundups")
    p_annual.add_argument("--year", type=int, required=True)
    p_annual.add_argument("--topic", type=str, default="bci")
    p_annual.add_argument("--output", type=Path, default=None)
    p_annual.add_argument("--model", type=str, default=None)
    p_annual.set_defaults(run=cmd_annual)

    # list-topics
    p_list = subparsers.add_parser("list-topics", help="Print space-separated topic names")
    p_list.set_defaults(run=cmd_list_topics)

    # clear-topic
    p_clear = subparsers.add_parser("clear-topic", help="Remove all data for a topic")
    p_clear.add_argument("topic", type=str)
    p_clear.add_argument("--yes", action="store_true", help="Skip confirmation")
    p_clear.set_defaults(run=cmd_clear_topic)

    # process-whole-year
    p_year = subparsers.add_parser("process-whole-year", help="Run weekly + monthly + annual for a year")
    p_year.add_argument("year", type=int, metavar="YEAR", help="e.g. 2025")
    p_year.add_argument("--topic", type=str, default="bci")
    p_year.add_argument("--dry-run", action="store_true")
    p_year.set_defaults(run=cmd_process_whole_year)

    # calculate-weeks
    p_weeks = subparsers.add_parser("calculate-weeks", help="Calculate week end dates for a month (YYYY-MM)")
    p_weeks.add_argument("month", type=str, help="YYYY-MM")
    p_weeks.add_argument("--json", action="store_true")
    p_weeks.add_argument("--first-day", action="store_true")
    p_weeks.add_argument("--last-day", action="store_true")
    p_weeks.add_argument("--days", action="store_true")
    p_weeks.add_argument("--info", action="store_true")
    p_weeks.set_defaults(run=cmd_calculate_weeks)

    # dashboard
    p_dash = subparsers.add_parser("dashboard", help="Generate articles dashboard (Markdown + JSON for Plotly graph)")
    p_dash.add_argument("--output", type=Path, help="Output Markdown path (default: content/articles-dashboard.md)")
    p_dash.add_argument("--recent", type=int, default=50, metavar="N", help="Number of recent articles in table (default 50)")
    p_dash.set_defaults(run=cmd_dashboard)

    # init-quartz
    p_quartz = subparsers.add_parser("init-quartz", help="Merge Quartz scaffold into a target directory")
    p_quartz.add_argument("--target", type=Path, required=True, help="Target directory to receive Quartz scaffold")
    p_quartz.add_argument("--repo", type=str, default=DEFAULT_QUARTZ_REPO, help="Quartz git repo URL")
    p_quartz.add_argument("--quartz-ref", type=str, default=DEFAULT_QUARTZ_REF, help="Quartz git ref/tag/branch")
    p_quartz.add_argument("--overwrite", action="store_true", help="Overwrite existing files")
    p_quartz.add_argument("--dry-run", action="store_true", help="Show actions without writing files")
    p_quartz.add_argument(
        "--write-local-exclude",
        dest="write_local_exclude",
        action="store_true",
        default=True,
        help="Write Quartz ignore rules into .git/info/exclude",
    )
    p_quartz.add_argument(
        "--no-write-local-exclude",
        dest="write_local_exclude",
        action="store_false",
        help="Skip writing .git/info/exclude rules",
    )
    p_quartz.set_defaults(run=cmd_init_quartz)

    args = parser.parse_args()
    args.run(args)


if __name__ == "__main__":
    main()
