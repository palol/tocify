import os
import tempfile
import types
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from tests.runner_test_utils import load_weekly_module_for_tests, write_runner_inputs


def _load_weekly_module(captured: dict):
    def get_topic_paths(topic: str, vault_root: Path | None = None):
        root = Path(vault_root or ".")
        return types.SimpleNamespace(
            feeds_path=root / "config" / f"feeds.{topic}.md",
            interests_path=root / "config" / f"interests.{topic}.md",
            prompt_path=root / "config" / "triage_prompt.md",
            gardener_prompt_path=root / "config" / "gardener_prompt.md",
            monthly_prompt_path=root / "config" / "monthly_roundup_prompt.md",
            annual_prompt_path=root / "config" / "annual_review_prompt.md",
            weekly_dir=root / "content" / "feeds" / "weekly",
            monthly_dir=root / "content" / "feeds" / "monthly",
            yearly_dir=root / "content" / "feeds" / "yearly",
            logs_dir=root / "logs",
            briefs_articles_csv=root / "content" / "briefs_articles.csv",
            edgar_ciks_path=root / "config" / f"edgar_ciks.{topic}.md",
            newsrooms_path=root / "config" / f"newsrooms.{topic}.md",
        )

    def fetch_historical_items(start_date, end_date, **kwargs):
        captured["start_date"] = start_date
        captured["end_date"] = end_date
        captured["kwargs"] = kwargs
        return []

    module, _ = load_weekly_module_for_tests(
        module_name="weekly_semantic_scholar_under_test",
        get_topic_paths=get_topic_paths,
        tocify_overrides={
            "parse_interests_md": lambda _text: {"keywords": ["bci"], "companies": []},
            "topic_search_string": lambda interests=None, max_keywords=5: "bci",
            "fetch_rss_items": lambda _feeds, end_date=None: [],
            "fetch_historical_items": fetch_historical_items,
        },
    )
    return module


class WeeklySemanticScholarTests(unittest.TestCase):
    def test_weekly_semantic_scholar_forwards_backend_and_query(self) -> None:
        captured: dict = {}
        weekly = _load_weekly_module(captured)
        weekly.TOPIC_REDUNDANCY_ENABLED = False
        weekly.TOPIC_GARDENER_ENABLED = False
        weekly.ENRICH_BULLETS = False

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            write_runner_inputs(root)
            with patch.dict(
                os.environ,
                {
                    "WEEKLY_OPENALEX": "0",
                    "WEEKLY_SEMANTIC_SCHOLAR": "1",
                    "NEWS_BACKEND": "",
                    "ADD_GOOGLE_NEWS": "0",
                    "ADD_CLINICAL_TRIALS": "0",
                    "ADD_EDGAR": "0",
                    "ADD_NEWSROOMS": "0",
                },
                clear=False,
            ):
                weekly.run_weekly(topic="bci", week_spec="2026 week 8", dry_run=0, vault_root=root)

        self.assertEqual(captured["start_date"], date.fromisocalendar(2026, 8, 1))
        self.assertEqual(captured["end_date"], date.fromisocalendar(2026, 8, 7))
        self.assertEqual(captured["kwargs"]["backends"], ["semanticscholar"])
        self.assertEqual(captured["kwargs"]["semanticscholar_query"], "bci")


if __name__ == "__main__":
    unittest.main()
