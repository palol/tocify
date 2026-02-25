"""Remove all data for a topic: briefs/logs matching *_<topic>_*, and that topic's rows from briefs_articles.csv.
Also provides cleanup of stray Cursor-produced action JSON files."""

import csv
import sys
from pathlib import Path

from tocify.runner.vault import get_topic_paths, VAULT_ROOT


def _is_canonical_topic_actions(path: Path, vault_root: Path) -> bool:
    """True if path is logs/topic_actions_*.json at vault root (or content/logs/ for backward compatibility)."""
    try:
        path = path.resolve()
        root = vault_root.resolve()
        name = path.name
        if not name.startswith("topic_actions_") or not name.endswith(".json"):
            return False
        path_str = str(path)
        logs_at_root = str(root / "logs")
        logs_under_content = str(root / "content" / "logs")
        return path_str.startswith(logs_at_root) or path_str.startswith(logs_under_content)
    except (ValueError, OSError):
        return False


def find_stray_action_json(vault_root: Path | None = None) -> list[Path]:
    """Find *.json files with 'action' in the filename under the vault, excluding canonical topic_actions_*.json in logs/ (or content/logs/)."""
    root = (vault_root or VAULT_ROOT).resolve()
    stray: list[Path] = []
    # Scan root (files only), content/, and config/ (recursive)
    for p in root.glob("*.json"):
        if p.is_file() and "action" in p.name.lower():
            stray.append(p)
    for d in (root / "content", root / "config"):
        if not d.exists() or not d.is_dir():
            continue
        for p in d.rglob("*.json"):
            if not p.is_file():
                continue
            if "action" not in p.name.lower():
                continue
            if _is_canonical_topic_actions(p, root):
                continue
            stray.append(p)
    return sorted(set(stray))


def clean_action_json(
    vault_root: Path | None = None,
    dry_run: bool = True,
    stray: list[Path] | None = None,
) -> int:
    """Remove stray action JSON files (preserves logs/topic_actions_*.json at vault root, or content/logs/). Returns number removed."""
    if stray is None:
        stray = find_stray_action_json(vault_root=vault_root)
    removed = 0
    for p in stray:
        try:
            if not dry_run:
                p.unlink()
            removed += 1
        except OSError:
            pass
    return removed


def clean_stray_action_json_in_logs(logs_dir: Path, keep_filename: str) -> int:
    """Remove from logs_dir any *action*.json whose name is not keep_filename. Returns number removed."""
    if not logs_dir.exists() or not logs_dir.is_dir():
        return 0
    removed = 0
    for p in logs_dir.glob("*action*.json"):
        if not p.is_file():
            continue
        if p.name != keep_filename:
            try:
                p.unlink()
                removed += 1
            except OSError:
                pass
    return removed


def main(topic: str, vault_root: Path | None = None, confirm: bool = False) -> None:
    root = vault_root or VAULT_ROOT
    paths = get_topic_paths(topic, vault_root=root)

    if not confirm:
        print(f"⚠️  WARNING: This will delete all data for topic '{topic}'!", file=sys.stderr)
        print(f"   - Briefs and logs matching *_{topic}_*", file=sys.stderr)
        print(f"   - Rows for {topic} in content/briefs_articles.csv", file=sys.stderr)
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
        with open(csv_path, newline="", encoding="utf-8") as f:
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
