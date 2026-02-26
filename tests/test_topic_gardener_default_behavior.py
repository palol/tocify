import os
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock

from tests.runner_test_utils import load_weekly_module_for_tests, write_runner_inputs


def _load_weekly_module():
    def get_topic_paths(topic: str, vault_root: Path | None = None):
        root = Path(vault_root or ".")
        return types.SimpleNamespace(
            feeds_path=root / "config" / f"feeds.{topic}.txt",
            interests_path=root / "config" / f"interests.{topic}.md",
            prompt_path=root / "config" / "triage_prompt.txt",
            weekly_dir=root / "content" / "feeds" / "weekly",
            monthly_dir=root / "content" / "feeds" / "monthly",
            yearly_dir=root / "content" / "feeds" / "yearly",
            logs_dir=root / "logs",
            briefs_articles_csv=root / "content" / "briefs_articles.csv",
            edgar_ciks_path=root / "config" / f"edgar_ciks.{topic}.txt",
            newsrooms_path=root / "config" / f"newsrooms.{topic}.txt",
        )

    module, _ = load_weekly_module_for_tests(
        module_name="weekly_default_behavior_under_test",
        get_topic_paths=get_topic_paths,
        tocify_overrides={
            "fetch_rss_items": lambda _feeds, end_date=None: [
                {
                    "id": "item-1",
                    "title": "Paper A",
                    "link": "https://example.com/a",
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
                        "link": "https://example.com/a",
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


class TopicGardenerDefaultBehaviorTests(unittest.TestCase):
    def test_default_env_enables_topic_gardener(self) -> None:
        previous = os.environ.pop("TOPIC_GARDENER", None)
        try:
            weekly = _load_weekly_module()
            self.assertTrue(weekly.TOPIC_GARDENER_ENABLED)
        finally:
            if previous is not None:
                os.environ["TOPIC_GARDENER"] = previous
            else:
                os.environ.pop("TOPIC_GARDENER", None)

    def test_env_zero_disables_topic_gardener(self) -> None:
        previous = os.environ.get("TOPIC_GARDENER")
        try:
            os.environ["TOPIC_GARDENER"] = "0"
            weekly = _load_weekly_module()
            self.assertFalse(weekly.TOPIC_GARDENER_ENABLED)
        finally:
            if previous is not None:
                os.environ["TOPIC_GARDENER"] = previous
            else:
                os.environ.pop("TOPIC_GARDENER", None)

    def test_run_weekly_calls_gardener_when_enabled(self) -> None:
        weekly = _load_weekly_module()
        weekly.TOPIC_REDUNDANCY_ENABLED = False
        weekly.TOPIC_GARDENER_ENABLED = True
        weekly.run_topic_gardener = Mock()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            write_runner_inputs(root)
            weekly.run_weekly(topic="bci", week_spec="2026 week 8", dry_run=0, vault_root=root)
        weekly.run_topic_gardener.assert_called_once()

    def test_run_weekly_skips_gardener_on_dry_run(self) -> None:
        weekly = _load_weekly_module()
        weekly.TOPIC_REDUNDANCY_ENABLED = False
        weekly.TOPIC_GARDENER_ENABLED = True
        weekly.run_topic_gardener = Mock()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            write_runner_inputs(root)
            weekly.run_weekly(topic="bci", week_spec="2026 week 8", dry_run=1, vault_root=root)
        weekly.run_topic_gardener.assert_not_called()

    def test_run_weekly_skips_gardener_when_disabled(self) -> None:
        weekly = _load_weekly_module()
        weekly.TOPIC_REDUNDANCY_ENABLED = False
        weekly.TOPIC_GARDENER_ENABLED = False
        weekly.run_topic_gardener = Mock()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            write_runner_inputs(root)
            weekly.run_weekly(topic="bci", week_spec="2026 week 8", dry_run=0, vault_root=root)
        weekly.run_topic_gardener.assert_not_called()

    def test_run_weekly_gardener_allowlist_matches_new_link_rows(self) -> None:
        weekly = _load_weekly_module()
        weekly.TOPIC_REDUNDANCY_ENABLED = False
        weekly.TOPIC_GARDENER_ENABLED = True
        weekly.run_topic_gardener = Mock()

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            write_runner_inputs(root)
            weekly.run_weekly(topic="bci", week_spec="2026 week 8", dry_run=0, vault_root=root)

        kwargs = weekly.run_topic_gardener.call_args.kwargs
        allowed_source_url_index = kwargs["allowed_source_url_index"]
        self.assertEqual(allowed_source_url_index, {"https://example.com/a": "https://example.com/a"})

    def test_run_weekly_merge_gardener_allowlist_includes_existing_and_new_rows(self) -> None:
        weekly = _load_weekly_module()
        weekly.TOPIC_REDUNDANCY_ENABLED = False
        weekly.TOPIC_GARDENER_ENABLED = True
        weekly.run_topic_gardener = Mock()

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            write_runner_inputs(root)
            weekly_dir = root / "content" / "feeds" / "weekly"
            weekly_dir.mkdir(parents=True, exist_ok=True)
            brief_path = weekly_dir / "2026 week 08.md"
            brief_path.write_text(
                (
                    "---\n"
                    "title: \"BCI Weekly Brief (week of 2026-02-16)\"\n"
                    "date: \"2026-02-16\"\n"
                    "lastmod: \"2026-02-16\"\n"
                    "included: 1\n"
                    "scored: 1\n"
                    "---\n"
                    "# BCI Weekly Brief (week of 2026-02-16)\n\n"
                    "**Included:** 1 (score ≥ 0.55)  \n"
                    "**Scored:** 1 total items\n\n"
                    "---\n\n"
                    "## [Existing item](https://example.com/old)\n\n"
                    "---\n"
                ),
                encoding="utf-8",
            )
            csv_path = root / "content" / "briefs_articles.csv"
            csv_path.parent.mkdir(parents=True, exist_ok=True)
            csv_path.write_text(
                (
                    "topic,week_of,url,title,source,published_utc,score,brief_filename,why,tags\n"
                    "bci,2026-02-16,https://example.com/old,Existing item,Journal,2026-02-16T00:00:00+00:00,0.80,"
                    "2026 week 08.md,Relevant,old\n"
                ),
                encoding="utf-8",
            )

            weekly.run_weekly(topic="bci", week_spec="2026 week 8", dry_run=0, vault_root=root)

        kwargs = weekly.run_topic_gardener.call_args.kwargs
        allowed_source_url_index = kwargs["allowed_source_url_index"]
        self.assertEqual(
            set(allowed_source_url_index.values()),
            {"https://example.com/old", "https://example.com/a"},
        )


if __name__ == "__main__":
    unittest.main()
