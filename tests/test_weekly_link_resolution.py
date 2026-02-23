import tempfile
import types
import unittest
from pathlib import Path

from tests.runner_test_utils import load_weekly_module_for_tests, write_runner_inputs


def _load_weekly_module():
    def get_topic_paths(topic: str, vault_root: Path | None = None):
        root = Path(vault_root or ".")
        return types.SimpleNamespace(
            feeds_path=root / "config" / f"feeds.{topic}.txt",
            interests_path=root / "config" / f"interests.{topic}.md",
            prompt_path=root / "config" / "triage_prompt.txt",
            briefs_dir=root / "content" / "briefs",
            logs_dir=root / "content" / "logs",
            briefs_articles_csv=root / "content" / "briefs_articles.csv",
            edgar_ciks_path=root / "config" / f"edgar_ciks.{topic}.txt",
            newsrooms_path=root / "config" / f"newsrooms.{topic}.txt",
        )

    module, _ = load_weekly_module_for_tests(
        module_name="weekly_link_resolution_under_test",
        get_topic_paths=get_topic_paths,
        tocify_overrides={
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
        },
    )
    return module


class WeeklyLinkResolutionTests(unittest.TestCase):
    def test_run_weekly_rewrites_heading_to_canonical_url(self) -> None:
        weekly = _load_weekly_module()
        weekly.TOPIC_REDUNDANCY_ENABLED = False
        weekly.TOPIC_GARDENER_ENABLED = False

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            write_runner_inputs(root)
            weekly.run_weekly(topic="bci", week_spec="2026 week 8", dry_run=0, vault_root=root)
            brief_path = root / "content" / "briefs" / "2026-02-16_bci_weekly-brief.md"
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
                brief_path = root / "content" / "briefs" / "2026-02-16_bci_weekly-brief.md"
                content = brief_path.read_text(encoding="utf-8")
        finally:
            weekly._resolve_weekly_heading_links = original_resolver

        self.assertIn("## Paper A", content)
        self.assertNotIn("https://fake.example.com/a", content)


if __name__ == "__main__":
    unittest.main()
