import importlib.util
import unittest
from pathlib import Path


def _load_link_hygiene_module():
    module_path = Path(__file__).resolve().parents[1] / "tocify" / "runner" / "link_hygiene.py"
    spec = importlib.util.spec_from_file_location("link_hygiene_under_test", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


LINK_HYGIENE = _load_link_hygiene_module()


class LinkHygieneTests(unittest.TestCase):
    def test_sanitize_rewrites_tracking_variant_to_canonical(self) -> None:
        md = "Read [paper](https://example.com/a?utm_source=foo).\n"
        allowed = LINK_HYGIENE.build_allowed_url_index(["https://example.com/a"])
        out, stats = LINK_HYGIENE.sanitize_markdown_links(md, allowed)
        self.assertIn("[paper](https://example.com/a)", out)
        self.assertEqual(stats["rewritten"], 1)

    def test_sanitize_delinks_untrusted_markdown_and_raw_urls(self) -> None:
        md = (
            "Bad markdown [paper](https://fake.example.com/a).\n"
            "Bad raw https://fake.example.com/raw.\n"
        )
        out, stats = LINK_HYGIENE.sanitize_markdown_links(md, {})
        self.assertIn("Bad markdown paper.", out)
        self.assertIn("Bad raw (link removed).", out)
        self.assertNotIn("fake.example.com", out)
        self.assertEqual(stats["delinked"], 2)

    def test_sanitize_converts_trusted_html_anchor_to_markdown(self) -> None:
        md = 'Read <a href="https://example.com/a">paper</a>.\n'
        allowed = LINK_HYGIENE.build_allowed_url_index(["https://example.com/a"])
        out, stats = LINK_HYGIENE.sanitize_markdown_links(md, allowed)
        self.assertIn("[paper](https://example.com/a)", out)
        self.assertNotIn("<a href=", out)
        self.assertEqual(stats["html_converted"], 1)

    def test_sanitize_rewrites_tracking_html_anchor_to_canonical(self) -> None:
        md = 'Read <a href="https://example.com/a?utm_source=foo">paper</a>.\n'
        allowed = LINK_HYGIENE.build_allowed_url_index(["https://example.com/a"])
        out, stats = LINK_HYGIENE.sanitize_markdown_links(md, allowed)
        self.assertIn("[paper](https://example.com/a)", out)
        self.assertEqual(stats["html_converted"], 1)
        self.assertEqual(stats["rewritten"], 1)

    def test_sanitize_delinks_untrusted_html_anchor(self) -> None:
        md = 'Bad html <a href="https://fake.example.com/a">Paper</a>.\n'
        out, stats = LINK_HYGIENE.sanitize_markdown_links(md, {})
        self.assertIn("Bad html Paper.", out)
        self.assertNotIn("fake.example.com", out)
        self.assertNotIn("<a href=", out)
        self.assertEqual(stats["delinked"], 1)
        self.assertEqual(stats["html_converted"], 0)

    def test_extract_urls_from_mixed_markdown(self) -> None:
        md = (
            "[one](https://example.com/1)\n"
            '<a href="https://example.com/4">four</a>\n'
            "<https://example.com/2>\n"
            "https://example.com/3.\n"
        )
        urls = LINK_HYGIENE.extract_urls_from_markdown(md)
        self.assertEqual(
            urls,
            [
                "https://example.com/1",
                "https://example.com/4",
                "https://example.com/2",
                "https://example.com/3",
            ],
        )


if __name__ == "__main__":
    unittest.main()
