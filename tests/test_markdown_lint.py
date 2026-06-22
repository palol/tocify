"""Tests for tocify.markdown_lint."""

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


def _load_markdown_lint():
    """Load markdown_lint from file so tests pass even when tocify is mocked elsewhere."""
    root = Path(__file__).resolve().parents[1]
    # Ensure tocify.frontmatter is loadable (real implementation)
    frontmatter_path = root / "tocify" / "frontmatter.py"
    fm_spec = importlib.util.spec_from_file_location("tocify.frontmatter", frontmatter_path)
    fm_mod = importlib.util.module_from_spec(fm_spec)
    assert fm_spec and fm_spec.loader
    fm_spec.loader.exec_module(fm_mod)
    sys.modules["tocify.frontmatter"] = fm_mod
    # So "from tocify.frontmatter import" in markdown_lint resolves
    if "tocify" in sys.modules:
        sys.modules["tocify"].frontmatter = fm_mod
    else:
        import types
        tocify_mod = types.ModuleType("tocify")
        tocify_mod.frontmatter = fm_mod
        sys.modules["tocify"] = tocify_mod
    path = root / "tocify" / "markdown_lint.py"
    spec = importlib.util.spec_from_file_location("tocify.markdown_lint", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sys.modules["tocify.markdown_lint"] = module
    return module


_markdown_lint = _load_markdown_lint()
_update_lastmod_in_content = _markdown_lint._update_lastmod_in_content
lint_file = _markdown_lint.lint_file


class TestUpdateLastmodInContent(unittest.TestCase):
    def test_sets_lastmod_and_updated_when_frontmatter_exists(self) -> None:
        content = "---\ntitle: Foo\ndate: 2020-01-01\n---\n\n# Body\n"
        out = _update_lastmod_in_content(content, "2026-02-21")
        self.assertIn("lastmod:", out)
        self.assertIn("updated:", out)
        self.assertIn("2026-02-21", out)
        self.assertIn("# Body", out)

    def test_unchanged_when_no_frontmatter(self) -> None:
        content = "# No frontmatter\n\nBody.\n"
        out = _update_lastmod_in_content(content, "2026-02-21")
        self.assertEqual(out, content)


class TestLintFile(unittest.TestCase):
    def test_missing_path_no_op(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nonexistent.md"
            self.assertFalse(path.exists())
            lint_file(path)
            self.assertFalse(path.exists())

    def test_sets_lastmod_on_file_with_frontmatter(self) -> None:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8"
        ) as f:
            f.write("---\ntitle: X\n---\n\n# Hi\n")
            path = Path(f.name)
        try:
            with patch("tocify.markdown_lint._run_mdformat", return_value=True):
                with patch("tocify.markdown_lint.dt") as mock_dt:
                    mock_dt.datetime.now.return_value.date.return_value.isoformat.return_value = (
                        "2026-02-21"
                    )
                    lint_file(path)
            content = path.read_text(encoding="utf-8")
            self.assertIn("lastmod:", content)
            self.assertIn("updated:", content)
            self.assertIn("2026-02-21", content)
        finally:
            path.unlink(missing_ok=True)

    def test_no_crash_on_file_without_frontmatter(self) -> None:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8"
        ) as f:
            f.write("# Only body\n")
            path = Path(f.name)
        try:
            with patch("tocify.markdown_lint._run_mdformat", return_value=True):
                lint_file(path)
            self.assertEqual(path.read_text(encoding="utf-8"), "# Only body\n")
        finally:
            path.unlink(missing_ok=True)
