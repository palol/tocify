#!/usr/bin/env python3
"""One-time cleanup utility for content/briefs_articles.csv."""

from __future__ import annotations

import argparse
import csv
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

MAX_TAGS = 8
MAX_TAG_CHARS = 40
MAX_WHY_CHARS = 320


def _normalize_text(value: object) -> str:
    return " ".join(str(value or "").strip().split())


def _normalize_score(raw_score: object) -> tuple[str, bool]:
    """Normalize score to string in 0..1, return (normalized, converted_legacy_percent)."""
    try:
        score = float(str(raw_score or "").strip())
    except (TypeError, ValueError):
        return "", False
    converted = False
    if 1 < score <= 100:
        score = score / 100.0
        converted = True
    if score < 0 or score > 1:
        return "", converted
    return f"{score:.4f}".rstrip("0").rstrip("."), converted


def _sanitize_tags(raw_tags: object) -> tuple[str, int]:
    text = str(raw_tags or "")
    values = text.split("|") if text else []
    out: list[str] = []
    seen: set[str] = set()
    trimmed = 0
    for idx, raw in enumerate(values):
        tag = _normalize_text(raw)
        if not tag:
            if raw.strip():
                trimmed += 1
            continue
        if len(tag) > MAX_TAG_CHARS:
            tag = tag[:MAX_TAG_CHARS].rstrip()
            trimmed += 1
        if not tag:
            trimmed += 1
            continue
        key = tag.casefold()
        if key in seen:
            trimmed += 1
            continue
        seen.add(key)
        out.append(tag)
        if len(out) >= MAX_TAGS:
            trimmed += max(0, len(values) - idx - 1)
            break
    return "|".join(out), trimmed


def normalize_row(row: dict[str, str], counters: dict[str, int]) -> tuple[dict[str, str], bool]:
    updated = dict(row)
    changed = False

    score_before = str(updated.get("score", ""))
    score_after, converted = _normalize_score(score_before)
    if converted:
        counters["score_legacy_percent_converted"] += 1
    if score_after == "" and score_before.strip():
        counters["score_invalid_cleared"] += 1
    if score_after != score_before:
        changed = True
        updated["score"] = score_after

    why_before = str(updated.get("why", ""))
    why_after = _normalize_text(why_before)
    if len(why_after) > MAX_WHY_CHARS:
        why_after = why_after[:MAX_WHY_CHARS].rstrip()
        counters["why_trimmed"] += 1
    if why_after != why_before:
        changed = True
        updated["why"] = why_after

    tags_before = str(updated.get("tags", ""))
    tags_after, trimmed = _sanitize_tags(tags_before)
    counters["tags_trimmed"] += trimmed
    if tags_after != tags_before:
        changed = True
        updated["tags"] = tags_after

    return updated, changed


def clean_csv(csv_path: Path, *, apply: bool) -> dict[str, int]:
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    counters = {
        "rows_total": 0,
        "rows_changed": 0,
        "score_legacy_percent_converted": 0,
        "score_invalid_cleared": 0,
        "why_trimmed": 0,
        "tags_trimmed": 0,
    }

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        rows_out: list[dict[str, str]] = []
        for row in reader:
            counters["rows_total"] += 1
            normalized, changed = normalize_row(row, counters)
            if changed:
                counters["rows_changed"] += 1
            rows_out.append(normalized)

    if not apply:
        return counters

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = csv_path.with_suffix(f"{csv_path.suffix}.bak-{stamp}")
    shutil.copy2(csv_path, backup_path)

    fd, temp_name = tempfile.mkstemp(
        prefix=f"{csv_path.name}.tmp.",
        suffix=".csv",
        dir=str(csv_path.parent),
    )
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as tf:
            writer = csv.DictWriter(tf, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows_out)
        os.replace(temp_name, csv_path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)

    print(f"Backup written: {backup_path}")
    return counters


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--csv",
        type=Path,
        default=Path("content") / "briefs_articles.csv",
        help="Path to briefs_articles.csv (default: content/briefs_articles.csv)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write cleaned CSV in place (default: dry-run report only)",
    )
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    counters = clean_csv(args.csv, apply=args.apply)
    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"Mode: {mode}")
    print(f"CSV: {args.csv}")
    print(
        "Summary: "
        f"rows_total={counters['rows_total']}, "
        f"rows_changed={counters['rows_changed']}, "
        f"score_legacy_percent_converted={counters['score_legacy_percent_converted']}, "
        f"score_invalid_cleared={counters['score_invalid_cleared']}, "
        f"why_trimmed={counters['why_trimmed']}, "
        f"tags_trimmed={counters['tags_trimmed']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
