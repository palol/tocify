"""CLI entrypoint: weekly, monthly, annual-review, list-topics, clear-topic, process-whole-year, calculate-weeks."""

import argparse
import datetime as dt
import os
import subprocess
import sys
from pathlib import Path

from tqdm import tqdm

from tocify.runner.vault import list_topics, VAULT_ROOT
from tocify.runner.weekly import run_weekly, parse_week_spec
from tocify.runner.monthly import main as monthly_main
from tocify.runner.annual import main as annual_main
from tocify.runner.weeks import get_month_metadata, calculate_week_ends
from tocify.runner.clear import main as clear_main


def _vault_root(args: argparse.Namespace) -> Path | None:
    return getattr(args, "vault", None) or (Path(os.environ.get("BCI_VAULT_ROOT", ".")).resolve() if hasattr(args, "vault") else None)


def cmd_weekly(args: argparse.Namespace) -> None:
    vault = getattr(args, "vault", None)
    run_weekly(
        topic=args.topic,
        week_spec=args.week_spec,
        dry_run=args.dry_run or 0,
        vault_root=vault,
    )


def cmd_monthly(args: argparse.Namespace) -> None:
    monthly_main(
        topic=args.topic,
        month=getattr(args, "month", None),
        end=getattr(args, "end", None),
        days=getattr(args, "days", 31),
        model=getattr(args, "model", None),
        vault_root=getattr(args, "vault", None),
    )


def cmd_annual(args: argparse.Namespace) -> None:
    annual_main(
        year=args.year,
        topic=args.topic,
        output=getattr(args, "output", None),
        model=getattr(args, "model", None),
        vault_root=getattr(args, "vault", None),
    )


def cmd_list_topics(args: argparse.Namespace) -> None:
    vault = getattr(args, "vault", None)
    topics = list_topics(vault_root=vault)
    print(" ".join(topics))


def cmd_clear_topic(args: argparse.Namespace) -> None:
    clear_main(
        args.topic,
        vault_root=getattr(args, "vault", None),
        confirm=getattr(args, "yes", False),
    )


def cmd_process_whole_year(args: argparse.Namespace) -> None:
    """Run weekly for every ISO week, then monthly for every month, then annual review."""
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


def main() -> None:
    parser = argparse.ArgumentParser(prog="tocify-runner", description="Vault/multi-topic runner for tocify")
    parser.add_argument("--vault", type=Path, default=None, help="Vault root (default: BCI_VAULT_ROOT or .)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # weekly
    p_weekly = subparsers.add_parser("weekly", help="Generate weekly brief for a topic")
    p_weekly.add_argument("--topic", type=str, default="bci")
    p_weekly.add_argument("week_spec", nargs="?", type=str, default=None, help="e.g. '2025 week 2'")
    p_weekly.add_argument("--dry-run", nargs="?", const=10, type=int, metavar="N", default=0, help="Cap to N items, no CSV append")
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

    args = parser.parse_args()
    args.run(args)


if __name__ == "__main__":
    main()
