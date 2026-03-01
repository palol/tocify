"""Convert briefs_articles.csv to markdown table with YAML frontmatter. Used after weekly brief generation."""

import csv
import re
import sys
from datetime import date
from pathlib import Path


def _link_cell(row: dict) -> str:
    """Format url column as markdown link [title](url), or title only if url is empty."""
    url = (row.get("url") or "").strip()
    title = (row.get("title") or "").strip()
    if not url:
        return title
    # Escape ] in link text so the markdown link is valid
    label = title.replace("\\", "\\\\").replace("]", "\\]")
    return f"[{label}]({url})"


def _frontmatter_created(path: Path) -> str | None:
    """Read existing output file and return 'created' value if present (YYYY-MM-DD)."""
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    if not text.strip().startswith("---"):
        return None
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None
    block = parts[1]
    m = re.search(r"created:\s*(\d{4}-\d{2}-\d{2})", block)
    return m.group(1) if m else None


def _build_frontmatter(created: str, modified: str) -> str:
    """Canonical order per scripts/standardize-headers.mjs."""
    return f"""---
title: "Articles Database"
publish: true
created: {created}
modified: {modified}
description: "Markdown table of briefs articles derived from briefs_articles.csv"
enableToc: true
tags: []
generator: "csv2md-briefs"
period: "database"
topic: "bci"
---

"""


def run_csv2md(input_path: Path, output_path: Path) -> int:
    """Convert CSV at input_path to markdown table with frontmatter at output_path. Returns 0 on success, 1 on error."""
    if not input_path.exists():
        print(f"Error: input file not found: {input_path}", file=sys.stderr)
        return 1

    from csv2md.table import Table

    today = date.today().isoformat()
    created = _frontmatter_created(output_path) or today
    frontmatter = _build_frontmatter(created=created, modified=today)

    with open(input_path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        export_columns = [c for c in fieldnames if c != "topic"]
        if not export_columns:
            cells = []
        else:
            header_row = list(export_columns)
            data_rows = []
            for row in reader:
                cells_row = []
                for col in export_columns:
                    if col == "url":
                        cells_row.append(_link_cell(row))
                    else:
                        cells_row.append((row.get(col) or "").strip())
                data_rows.append(cells_row)
            cells = [header_row] + data_rows

    table = Table(cells)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(frontmatter + table.markdown(), encoding="utf-8")
    return 0
