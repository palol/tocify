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
            weekly_dir=root / "content" / "feeds" / "weekly",
            monthly_dir=root / "content" / "feeds" / "monthly",
            yearly_dir=root / "content" / "feeds" / "yearly",
            logs_dir=root / "logs",
            briefs_articles_csv=root / "content" / "briefs_articles.csv",
            edgar_ciks_path=root / "config" / f"edgar_ciks.{topic}.txt",
            newsrooms_path=root / "config" / f"newsrooms.{topic}.txt",
        )

    module, _ = load_weekly_module_for_tests(
        module_name="weekly_newspaper_guard_under_test",
        get_topic_paths=get_topic_paths,
        tocify_overrides={
            "fetch_rss_items": lambda _feeds, end_date=None: [
                {
                    "id": "item-1",
                    "title": "One item",
                    "link": "https://example.com/article-1",
                    "source": "Example",
                    "published_utc": "2026-02-16T00:00:00+00:00",
                    "summary": "Summary",
                }
            ],
            "keyword_prefilter": lambda items, _keywords, keep_top=200, companies=None, **kwargs: [],
            "triage_in_batches": lambda *_args, **_kwargs: {"notes": "", "ranked": []},
        },
    )
    return module


class WeeklyNewspaperGuardTests(unittest.TestCase):
    def test_use_newspaper_skips_executor_when_filtered_items_are_empty(self) -> None:
        weekly = _load_weekly_module()
        weekly.TOPIC_REDUNDANCY_ENABLED = False
        weekly.TOPIC_GARDENER_ENABLED = False
        weekly.USE_NEWSPAPER = True

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            write_runner_inputs(root)
            weekly.run_weekly(topic="bci", week_spec="2026 week 8", dry_run=0, vault_root=root)
            brief_path = root / "content" / "feeds" / "weekly" / "2026 week 08.md"
            self.assertTrue(brief_path.exists())


if __name__ == "__main__":
    unittest.main()
