"""Tests for changelog pipeline: dedupe, add_dates, filter, extract_body, fallback fixes."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

from tocify.runner.changelog import (
    _apply_fallback_fixes,
    _dedupe_changelog,
    _extract_body,
    _filter_changelog,
    find_repo_root,
    run_changelog_pipeline,
)


class TestExtractBody:
    def test_extract_body_starts_with_frontmatter(self) -> None:
        text = """---
title: Changelog
---

## Section
- item
"""
        assert _extract_body(text) == text.strip()

    def test_extract_body_code_fence(self) -> None:
        text = """```markdown
---
title: Changelog
---

## Section
- item
```"""
        got = _extract_body(text)
        assert got is not None
        assert got.startswith("---")
        assert "## Section" in got

    def test_extract_body_returns_none_for_summary_only(self) -> None:
        text = "I fixed a few typos and made quartz bold."
        assert _extract_body(text) is None

    def test_extract_body_finds_dash_title_in_chunk(self) -> None:
        text = """Some preamble.
---
title: Changelog
publish: true
---

## Backend
- fix
"""
        got = _extract_body(text)
        assert got is not None
        assert got.startswith("---")
        assert "## Backend" in got


class TestApplyFallbackFixes:
    def test_fixes_known_typos(self) -> None:
        content = "explicitely left aligh refresh briefs. to-do- fix hn fetch range"
        got = _apply_fallback_fixes(content)
        assert "explicitly" in got
        assert "left align " in got
        assert "to-do:" in got

    def test_quartz_and_darkmode(self) -> None:
        content = "Darkmode/ and repairing graph"
        got = _apply_fallback_fixes(content)
        assert "DarkMode/" in got
        assert "repair graph" in got


class TestDedupeChangelog:
    def test_dedupes_list_items_per_section(self) -> None:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8"
        ) as f:
            f.write("""## A
- one
- two
- one
## B
- one
""")
            path = Path(f.name)
        try:
            _dedupe_changelog(path)
            text = path.read_text()
            assert text.count("- one") == 2  # one per section
            assert "## A" in text and "## B" in text
        finally:
            path.unlink()


class TestFilterChangelog:
    def test_keeps_scoped_lines_and_normalizes_quartz(self) -> None:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8"
        ) as f:
            f.write("""## Backend
- 2026-01-01 — **quartz** — fix
- short
- 2026-01-02 — long enough line here
""")
            path = Path(f.name)
        try:
            _filter_changelog(path)
            text = path.read_text()
            assert "**quartz**" in text
            assert "- short" not in text
            assert "long enough line here" in text
        finally:
            path.unlink()


class TestFindRepoRoot:
    def test_finds_git_dir(self) -> None:
        # Run from tocify worktree; repo root is tocify-plan or parent
        cwd = Path(__file__).resolve().parent
        root = find_repo_root(cwd)
        assert root is not None
        assert (root / ".git").exists()

    def test_returns_none_for_non_git_dir(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            assert find_repo_root(Path(td)) is None


class TestRunChangelogPipelineNoCliffNoPolish:
    """Run pipeline with --no-cliff and --no-polish (no git-cliff, no agent)."""

    def test_dedupe_add_dates_filter_only(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "content").mkdir()
            changelog = root / "content" / "changelog.md"
            changelog.write_text("""## Backend
- **quartz** — fix
- **quartz** — fix
- too short
""", encoding="utf-8")
            run_changelog_pipeline(
                changelog,
                root,
                run_cliff=False,
                skip_polish=True,
            )
            text = changelog.read_text()
            # Dedupe: one "- **quartz** — fix" per section
            assert text.count("- **quartz** — fix") == 1
            # Filter: "too short" dropped
            assert "too short" not in text
