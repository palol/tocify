"""Calculate week end dates and month metadata."""

import datetime as dt


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
