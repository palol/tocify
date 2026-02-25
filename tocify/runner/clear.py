"""Remove all data for a topic: weekly briefs, monthly roundups, annual reviews, and topic logs; and that topic's rows from briefs_articles.csv."""

import csv
import sys
from pathlib import Path

from tocify.runner.vault import get_topic_paths, VAULT_ROOT


def main(topic: str, vault_root: Path | None = None, confirm: bool = False) -> None:
    root = vault_root or VAULT_ROOT
    paths = get_topic_paths(topic, vault_root=root)

    if not confirm:
        print("⚠️  WARNING: This will delete all data for topic '{}'!".format(topic), file=sys.stderr)
        print("   - Weekly briefs (content/briefs/* week *.md), monthly roundups (content/roundups/), annual (content/annual/), logs matching *_{}_*".format(topic), file=sys.stderr)
        print("   - Rows for {} in content/briefs_articles.csv".format(topic), file=sys.stderr)
        print("", file=sys.stderr)
        print('Type "yes" to confirm: ', end="", file=sys.stderr)
        try:
            c = input()
        except EOFError:
            c = ""
        if c.strip().lower() != "yes":
            print("Aborted.", file=sys.stderr)
            sys.exit(1)

    removed = 0
    if paths.briefs_dir.exists():
        for p in paths.briefs_dir.glob("* week *.md"):
            if p.is_file():
                p.unlink()
                removed += 1
    if paths.roundups_dir.exists():
        for p in paths.roundups_dir.glob("*.md"):
            if p.is_file():
                p.unlink()
                removed += 1
    if paths.annual_dir.exists():
        for p in paths.annual_dir.glob("* review.md"):
            if p.is_file():
                p.unlink()
                removed += 1
    if paths.logs_dir.exists():
        for p in paths.logs_dir.glob(f"*_{topic}_*"):
            if p.is_file():
                p.unlink()
                removed += 1
    print(f"Removed {removed} files for topic {topic} (weekly briefs, roundups, annual, logs)")

    csv_path = paths.briefs_articles_csv
    if csv_path.exists():
        with open(csv_path, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames or []
            rows = [r for r in reader if (r.get("topic") or "").strip() != topic]
        if "topic" not in fieldnames:
            fieldnames = list(fieldnames) + ["topic"]
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        print(f"Filtered content/briefs_articles.csv to remove topic {topic}")
