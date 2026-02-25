import tempfile
import types
import unittest
from pathlib import Path
from typing import Any

from tests.runner_test_utils import load_weekly_module_for_tests, write_runner_inputs


def _get_topic_paths(topic: str, vault_root: Path | None = None):
    root = Path(vault_root or ".")
    return types.SimpleNamespace(
        feeds_path=root / "config" / f"feeds.{topic}.txt",
        interests_path=root / "config" / f"interests.{topic}.md",
        prompt_path=root / "config" / "triage_prompt.txt",
        briefs_dir=root / "content" / "briefs",
        roundups_dir=root / "content" / "roundups",
        annual_dir=root / "content" / "annual",
        logs_dir=root / "logs",
        briefs_articles_csv=root / "content" / "briefs_articles.csv",
        edgar_ciks_path=root / "config" / f"edgar_ciks.{topic}.txt",
        newsrooms_path=root / "config" / f"newsrooms.{topic}.txt",
    )


def _default_tocify_overrides() -> dict[str, Any]:
    return {
        "fetch_rss_items": lambda _feeds, end_date=None: [
            {
                "id": "item-1",
                "title": "Paper A",
                "link": "https://canonical.example.com/a",
                "source": "Journal A",
                "published_utc": "2026-02-16T00:00:00+00:00",
                "summary": "Summary A",
            }
        ],
        "triage_in_batches": lambda _interests, _items, _batch, _triage_fn: {
            "notes": "Weekly notes.",
            "ranked": [
                {
                    "id": "item-1",
                    "title": "Paper A",
                    "link": "https://fake.example.com/a",
                    "source": "Journal A",
                    "published_utc": "2026-02-16T00:00:00+00:00",
                    "score": 0.9,
                    "why": "Relevant.",
                    "tags": ["Neuro"],
                }
            ],
        },
    }


def _load_weekly_module_and_frontmatter(*, tocify_overrides: dict[str, Any] | None = None):
    merged_overrides = _default_tocify_overrides()
    if tocify_overrides:
        merged_overrides.update(tocify_overrides)
    return load_weekly_module_for_tests(
        module_name="weekly_link_resolution_under_test",
        get_topic_paths=_get_topic_paths,
        tocify_overrides=merged_overrides,
    )


def _load_weekly_module(*, tocify_overrides: dict[str, Any] | None = None):
    module, _ = _load_weekly_module_and_frontmatter(tocify_overrides=tocify_overrides)
    return module


def _read_frontmatter(frontmatter_module: Any, path: Path) -> dict[str, Any]:
    frontmatter, _ = frontmatter_module.split_frontmatter_and_body(path.read_text(encoding="utf-8"))
    return frontmatter


class WeeklyLinkResolutionTests(unittest.TestCase):
    def test_run_weekly_rewrites_heading_to_canonical_url(self) -> None:
        weekly = _load_weekly_module()
        weekly.TOPIC_REDUNDANCY_ENABLED = False
        weekly.TOPIC_GARDENER_ENABLED = False

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            write_runner_inputs(root)
            weekly.run_weekly(topic="bci", week_spec="2026 week 8", dry_run=0, vault_root=root)
            brief_path = root / "content" / "briefs" / "2026 week 08.md"
            content = brief_path.read_text(encoding="utf-8")

        self.assertIn("## [Paper A](https://canonical.example.com/a)", content)
        self.assertNotIn("## [Paper A](https://fake.example.com/a)", content)

    def test_run_weekly_delinks_untrusted_heading_when_resolver_errors(self) -> None:
        weekly = _load_weekly_module()
        weekly.TOPIC_REDUNDANCY_ENABLED = False
        weekly.TOPIC_GARDENER_ENABLED = False
        original_resolver = weekly._resolve_weekly_heading_links
        weekly._resolve_weekly_heading_links = lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("resolver boom")
        )
        try:
            with tempfile.TemporaryDirectory() as td:
                root = Path(td)
                write_runner_inputs(root)
                weekly.run_weekly(topic="bci", week_spec="2026 week 8", dry_run=0, vault_root=root)
                brief_path = root / "content" / "briefs" / "2026 week 08.md"
                content = brief_path.read_text(encoding="utf-8")
        finally:
            weekly._resolve_weekly_heading_links = original_resolver

        self.assertIn("## [Paper A](https://canonical.example.com/a)", content)
        self.assertNotIn("https://fake.example.com/a", content)

    def test_run_weekly_new_brief_frontmatter_omits_title(self) -> None:
        weekly, frontmatter_module = _load_weekly_module_and_frontmatter()
        weekly.TOPIC_REDUNDANCY_ENABLED = False
        weekly.TOPIC_GARDENER_ENABLED = False

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            write_runner_inputs(root)
            weekly.run_weekly(topic="bci", week_spec="2026 week 8", dry_run=0, vault_root=root)
            brief_path = root / "content" / "briefs" / "2026 week 08.md"
            frontmatter = _read_frontmatter(frontmatter_module, brief_path)

        self.assertNotIn("title", frontmatter)

    def test_run_weekly_no_items_frontmatter_omits_title(self) -> None:
        weekly, frontmatter_module = _load_weekly_module_and_frontmatter(
            tocify_overrides={"fetch_rss_items": lambda _feeds, end_date=None: []}
        )
        weekly.TOPIC_REDUNDANCY_ENABLED = False
        weekly.TOPIC_GARDENER_ENABLED = False

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            write_runner_inputs(root)
            weekly.run_weekly(topic="bci", week_spec="2026 week 8", dry_run=0, vault_root=root)
            brief_path = root / "content" / "briefs" / "2026 week 08.md"
            frontmatter = _read_frontmatter(frontmatter_module, brief_path)

        self.assertNotIn("title", frontmatter)
        self.assertEqual(frontmatter.get("included"), 0)
        self.assertEqual(frontmatter.get("scored"), 0)

    def test_run_weekly_merge_preserves_existing_title(self) -> None:
        weekly, frontmatter_module = _load_weekly_module_and_frontmatter()
        weekly.TOPIC_REDUNDANCY_ENABLED = False
        weekly.TOPIC_GARDENER_ENABLED = False

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            write_runner_inputs(root)
            briefs_dir = root / "content" / "briefs"
            briefs_dir.mkdir(parents=True, exist_ok=True)
            brief_path = briefs_dir / "2026 week 08.md"
            brief_path.write_text(
                (
                    "---\n"
                    "title: \"Legacy Weekly Title\"\n"
                    "date: \"2026-02-16\"\n"
                    "lastmod: \"2026-02-16\"\n"
                    "included: 0\n"
                    "scored: 0\n"
                    "---\n\n"
                    "# BCI Weekly Brief (week of 2026-02-16)\n\n"
                    "**Included:** 0 (score ≥ 0.55)  \n"
                    "**Scored:** 0 total items\n"
                ),
                encoding="utf-8",
            )
            weekly.run_weekly(topic="bci", week_spec="2026 week 8", dry_run=0, vault_root=root)
            frontmatter = _read_frontmatter(frontmatter_module, brief_path)

        self.assertEqual(frontmatter.get("title"), "Legacy Weekly Title")

    def test_run_weekly_merge_without_existing_title_keeps_title_absent(self) -> None:
        weekly, frontmatter_module = _load_weekly_module_and_frontmatter()
        weekly.TOPIC_REDUNDANCY_ENABLED = False
        weekly.TOPIC_GARDENER_ENABLED = False

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            write_runner_inputs(root)
            briefs_dir = root / "content" / "briefs"
            briefs_dir.mkdir(parents=True, exist_ok=True)
            brief_path = briefs_dir / "2026 week 08.md"
            brief_path.write_text(
                (
                    "---\n"
                    "date: \"2026-02-16\"\n"
                    "lastmod: \"2026-02-16\"\n"
                    "included: 0\n"
                    "scored: 0\n"
                    "---\n\n"
                    "# BCI Weekly Brief (week of 2026-02-16)\n\n"
                    "**Included:** 0 (score ≥ 0.55)  \n"
                    "**Scored:** 0 total items\n"
                ),
                encoding="utf-8",
            )
            weekly.run_weekly(topic="bci", week_spec="2026 week 8", dry_run=0, vault_root=root)
            frontmatter = _read_frontmatter(frontmatter_module, brief_path)

        self.assertNotIn("title", frontmatter)


if __name__ == "__main__":
    unittest.main()
