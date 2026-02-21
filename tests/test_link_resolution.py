import importlib.util
import unittest
from pathlib import Path


def _load_link_resolution_module():
    module_path = Path(__file__).resolve().parents[1] / "tocify" / "runner" / "link_resolution.py"
    spec = importlib.util.spec_from_file_location("link_resolution_under_test", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


LINK_RESOLUTION = _load_link_resolution_module()


class LinkResolutionTests(unittest.TestCase):
    def test_exact_match_replaces_heading_url(self) -> None:
        md = "## [Paper A](https://fake.example.com/a)\n"
        rows = [{"brief_filename": "brief.md", "title": "Paper A", "url": "https://canonical.example.com/a"}]
        out, stats = LINK_RESOLUTION.resolve_weekly_heading_links(md, "brief.md", rows)
        self.assertIn("## [Paper A](https://canonical.example.com/a)", out)
        self.assertEqual(stats["exact_matches"], 1)

    def test_normalized_unique_match_replaces_heading_url(self) -> None:
        md = "## [Paper  A](https://fake.example.com/a)\n"
        rows = [{"brief_filename": "brief.md", "title": "paper a", "url": "https://canonical.example.com/a"}]
        out, stats = LINK_RESOLUTION.resolve_weekly_heading_links(md, "brief.md", rows)
        self.assertIn("## [Paper  A](https://canonical.example.com/a)", out)
        self.assertEqual(stats["normalized_matches"], 1)

    def test_ambiguous_normalized_match_keeps_existing_url(self) -> None:
        md = "## [Paper A](https://fake.example.com/a)\n"
        rows = [
            {"brief_filename": "brief.md", "title": "paper a", "url": "https://canonical.example.com/a1"},
            {"brief_filename": "brief.md", "title": "paper   a", "url": "https://canonical.example.com/a2"},
        ]
        out, stats = LINK_RESOLUTION.resolve_weekly_heading_links(md, "brief.md", rows)
        self.assertEqual(out, md)
        self.assertEqual(stats["ambiguous"], 1)

    def test_missing_row_keeps_existing_url(self) -> None:
        md = "## [Paper A](https://fake.example.com/a)\n"
        rows = [{"brief_filename": "brief.md", "title": "Paper B", "url": "https://canonical.example.com/b"}]
        out, stats = LINK_RESOLUTION.resolve_weekly_heading_links(md, "brief.md", rows)
        self.assertEqual(out, md)
        self.assertEqual(stats["missing"], 1)

    def test_invalid_metadata_url_keeps_existing_url(self) -> None:
        md = "## [Paper A](https://fake.example.com/a)\n"
        rows = [{"brief_filename": "brief.md", "title": "Paper A", "url": "www.example.com/a"}]
        out, stats = LINK_RESOLUTION.resolve_weekly_heading_links(md, "brief.md", rows)
        self.assertEqual(out, md)
        self.assertEqual(stats["invalid_url"], 1)

    def test_non_heading_links_are_unchanged(self) -> None:
        md = "[inline](https://fake.example.com/a)\n### [Paper A](https://fake.example.com/a)\n"
        rows = [{"brief_filename": "brief.md", "title": "Paper A", "url": "https://canonical.example.com/a"}]
        out, stats = LINK_RESOLUTION.resolve_weekly_heading_links(md, "brief.md", rows)
        self.assertEqual(out, md)
        self.assertEqual(stats["exact_matches"], 0)


if __name__ == "__main__":
    unittest.main()
