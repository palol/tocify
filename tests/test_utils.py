"""Tests for tocify.utils (html_to_plain_text, normalize_summary)."""

import sys
import types
import unittest
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
_root_str = str(_root)
if _root_str not in sys.path:
    sys.path.insert(0, _root_str)

tocify_mod = sys.modules.get("tocify")
if tocify_mod is None or not hasattr(tocify_mod, "__path__"):
    pkg = types.ModuleType("tocify")
    pkg.__path__ = [str(_root / "tocify")]
    sys.modules["tocify"] = pkg

from tocify.utils import html_to_plain_text, normalize_summary, sha1


class HtmlToPlainTextTests(unittest.TestCase):
    def test_strips_tags_and_returns_text(self) -> None:
        self.assertEqual(html_to_plain_text("<p>hello</p>"), "hello")

    def test_unescapes_entities(self) -> None:
        self.assertEqual(html_to_plain_text("a &amp; b"), "a & b")
        self.assertEqual(html_to_plain_text("&lt;tag&gt;"), "<tag>")

    def test_nested_tags(self) -> None:
        self.assertEqual(
            html_to_plain_text("<div><p>one</p><p>two</p></div>"),
            "onetwo",
        )

    def test_empty_or_whitespace_returns_empty(self) -> None:
        self.assertEqual(html_to_plain_text(""), "")
        self.assertEqual(html_to_plain_text("   "), "")

    def test_plain_text_unchanged(self) -> None:
        self.assertEqual(html_to_plain_text("No tags here."), "No tags here.")


class NormalizeSummaryTests(unittest.TestCase):
    def test_html_stripped_by_default(self) -> None:
        out = normalize_summary("<p>Summary text</p>", max_chars=500)
        self.assertEqual(out, "Summary text")
        self.assertNotIn("<", out)
        self.assertNotIn(">", out)

    def test_truncation_never_leaves_partial_tags(self) -> None:
        # Long HTML truncated would previously cut mid-tag; output must be plain text
        html_input = "<p>a</p><p>" + "x" * 600 + "</p>"
        out = normalize_summary(html_input, max_chars=10)
        self.assertNotIn("<", out)
        self.assertNotIn(">", out)
        self.assertTrue(out.endswith("…") or len(out) <= 11)

    def test_entities_unescaped_before_truncate(self) -> None:
        out = normalize_summary("a &amp; b &amp; c", max_chars=20)
        self.assertIn("&", out)
        self.assertNotIn("&amp;", out)

    def test_strip_html_false_preserves_content(self) -> None:
        raw = "  plain  text  "
        out = normalize_summary(raw, max_chars=500, strip_html=False)
        self.assertEqual(out, "plain text")

    def test_sha1_unchanged(self) -> None:
        self.assertEqual(sha1(""), "da39a3ee5e6b4b0d3255bfef95601890afd80709")
