"""Tests for tocify.runner.csv2md (CSV to markdown table with frontmatter)."""

import pytest
from pathlib import Path

from tocify.runner.csv2md import (
    _build_frontmatter,
    _frontmatter_created,
    run_csv2md,
)


def test_frontmatter_created_missing_file(tmp_path: Path) -> None:
    assert _frontmatter_created(tmp_path / "nonexistent.md") is None


def test_frontmatter_created_no_frontmatter(tmp_path: Path) -> None:
    (tmp_path / "out.md").write_text("no frontmatter\n")
    assert _frontmatter_created(tmp_path / "out.md") is None


def test_frontmatter_created_extracts_date(tmp_path: Path) -> None:
    (tmp_path / "out.md").write_text("""---
title: "Test"
created: 2024-01-15
modified: 2024-02-20
---

| a | b |
""")
    assert _frontmatter_created(tmp_path / "out.md") == "2024-01-15"


def test_build_frontmatter() -> None:
    out = _build_frontmatter(created="2024-01-15", modified="2024-02-20")
    assert "created: 2024-01-15" in out
    assert "modified: 2024-02-20" in out
    assert 'generator: "csv2md-briefs"' in out
    assert "---" in out


def test_run_csv2md_success(tmp_path: Path) -> None:
    csv_path = tmp_path / "briefs.csv"
    csv_path.write_text("topic,title,url\nbci,Example,https://example.com\n", encoding="utf-8")
    out_path = tmp_path / "content" / "briefs.md"

    code = run_csv2md(csv_path, out_path)
    assert code == 0
    assert out_path.exists()
    text = out_path.read_text(encoding="utf-8")
    assert text.strip().startswith("---")
    assert "created:" in text
    assert "modified:" in text
    assert "| topic | title | url |" in text or "topic" in text
    assert "Example" in text


def test_run_csv2md_preserves_created(tmp_path: Path) -> None:
    csv_path = tmp_path / "briefs.csv"
    csv_path.write_text("a,b\n1,2\n", encoding="utf-8")
    out_path = tmp_path / "briefs.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("""---
title: "Briefs articles database"
created: 2023-06-10
modified: 2023-06-10
---

| x | y |
""", encoding="utf-8")

    code = run_csv2md(csv_path, out_path)
    assert code == 0
    text = out_path.read_text(encoding="utf-8")
    assert "created: 2023-06-10" in text
    assert "modified:" in text


def test_run_csv2md_missing_input(tmp_path: Path) -> None:
    code = run_csv2md(tmp_path / "missing.csv", tmp_path / "out.md")
    assert code == 1
