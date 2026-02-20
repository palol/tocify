"""Calculate week end dates and month metadata."""

import argparse
import datetime as dt
import sys


def get_month_metadata(year_month: str) -> tuple[dt.date, dt.date, int]:
    """Return (first_day, last_day, days_in_month) for YYYY-MM."""
    try:
        year, month = map(int, year_month.split("-"))
        first_day = dt.date(year, month, 1)
        if month == 12:
            next_month = dt.date(year + 1, 1, 1)
        else:
            next_month = dt.date(year, month + 1, 1)
        last_day = next_month - dt.timedelta(days=1)
        days_in_month = (last_day - first_day).days + 1
        return first_day, last_day, days_in_month
    except (ValueError, TypeError) as e:
        raise ValueError(f"Invalid month format: {year_month}. Expected YYYY-MM.") from e


def calculate_week_ends(year_month: str) -> list[str]:
    """Return list of week end dates (YYYY-MM-DD) for the given month."""
    first_day, last_day, _ = get_month_metadata(year_month)
    week_ends = []
    current_week_end = first_day + dt.timedelta(days=6)
    if current_week_end > last_day:
        current_week_end = last_day
    week_ends.append(current_week_end.isoformat())
    for _ in range(4):
        next_week_start = current_week_end + dt.timedelta(days=1)
        if next_week_start > last_day:
            break
        next_week_end = next_week_start + dt.timedelta(days=6)
        if next_week_end > last_day:
            next_week_end = last_day
        week_ends.append(next_week_end.isoformat())
        current_week_end = next_week_end
        if current_week_end >= last_day:
            break
    return week_ends


def cli() -> None:
    parser = argparse.ArgumentParser(description="Calculate week end dates for a month (YYYY-MM)")
    parser.add_argument("month", type=str, help="Month in YYYY-MM format")
    parser.add_argument("--json", action="store_true", help="Output as JSON array")
    parser.add_argument("--first-day", action="store_true")
    parser.add_argument("--last-day", action="store_true")
    parser.add_argument("--days", action="store_true")
    parser.add_argument("--info", action="store_true")
    args = parser.parse_args()
    try:
        if args.first_day:
            first_day, _, _ = get_month_metadata(args.month)
            print(first_day.isoformat())
            return
        if args.last_day:
            _, last_day, _ = get_month_metadata(args.month)
            print(last_day.isoformat())
            return
        if args.days:
            _, _, days_in_month = get_month_metadata(args.month)
            print(days_in_month)
            return
        if args.info:
            first_day, last_day, days_in_month = get_month_metadata(args.month)
            print(f"FIRST_DAY={first_day.isoformat()}")
            print(f"LAST_DAY={last_day.isoformat()}")
            print(f"DAYS_IN_MONTH={days_in_month}")
            return
        week_ends = calculate_week_ends(args.month)
        if args.json:
            import json
            print(json.dumps(week_ends))
        else:
            print(" ".join(week_ends))
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
