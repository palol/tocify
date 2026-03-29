import os
import tempfile
import types
import unittest
from pathlib import Path

from tests.runner_test_utils import load_weekly_module_for_tests, write_runner_inputs


def _get_topic_paths(topic: str, vault_root: Path | None = None):
    root = Path(vault_root or ".")
    return types.SimpleNamespace(
        feeds_path=root / "config" / f"feeds.{topic}.md",
        interests_path=root / "config" / f"interests.{topic}.md",
        prompt_path=root / "config" / "triage_prompt.md",
        news_prompt_path=root / "config" / "triage_prompt_news.md",
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


def _ranked_rows(items: list[dict], score: float = 0.9) -> list[dict]:
    ranked = []
    for item in items:
        ranked.append({
            "id": item["id"],
            "title": item["title"],
            "link": item["link"],
            "source": item["source"],
            "published_utc": item["published_utc"],
            "score": score,
            "why": f"why {item['id']}",
            "tags": ["test"],
        })
    return ranked


class WeeklyDualLaneTests(unittest.TestCase):
    def _load_weekly_module(self, triage_calls: list[dict], items: list[dict]):
        def triage(_interests, triage_items, _batch, _triage_fn):
            triage_calls.append({
                "prompt": os.environ.get("TOCIFY_PROMPT_PATH"),
                "ids": [item["id"] for item in triage_items],
            })
            return {"notes": "", "ranked": _ranked_rows(triage_items)}

        weekly, _ = load_weekly_module_for_tests(
            module_name=f"weekly_dual_lane_under_test_{len(triage_calls)}",
            get_topic_paths=_get_topic_paths,
            tocify_overrides={
                "fetch_rss_items": lambda _feeds, end_date=None: list(items),
                "keyword_prefilter": lambda triage_items, _keywords, keep_top=200, companies=None, **kwargs: triage_items,
                "triage_in_batches": triage,
            },
        )
        weekly.TOPIC_REDUNDANCY_ENABLED = False
        weekly.TOPIC_GARDENER_ENABLED = False
        weekly.ENRICH_BULLETS = False
        return weekly

    def test_runs_two_triage_passes_when_news_prompt_exists_and_news_items_present(self) -> None:
        triage_calls: list[dict] = []
        weekly = self._load_weekly_module(
            triage_calls,
            [
                {
                    "id": "research-1",
                    "title": "Research item",
                    "link": "https://example.com/research-1",
                    "source": "Journal",
                    "published_utc": "2026-02-18T00:00:00+00:00",
                    "summary": "Summary",
                    "triage_lane": "research",
                },
                {
                    "id": "news-1",
                    "title": "News item",
                    "link": "https://example.com/news-1",
                    "source": "Newsroom",
                    "published_utc": "2026-02-18T00:00:00+00:00",
                    "summary": "Summary",
                    "triage_lane": "news",
                },
            ],
        )

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            write_runner_inputs(root, news_prompt=True)
            weekly.run_weekly(topic="bci", week_spec="2026 week 8", dry_run=0, vault_root=root)

        self.assertEqual(len(triage_calls), 2)
        self.assertTrue(triage_calls[0]["prompt"].endswith("triage_prompt.md"))
        self.assertTrue(triage_calls[1]["prompt"].endswith("triage_prompt_news.md"))
        self.assertEqual(triage_calls[0]["ids"], ["research-1"])
        self.assertEqual(triage_calls[1]["ids"], ["news-1"])

    def test_falls_back_to_single_pass_when_news_prompt_is_missing(self) -> None:
        triage_calls: list[dict] = []
        weekly = self._load_weekly_module(
            triage_calls,
            [
                {
                    "id": "research-1",
                    "title": "Research item",
                    "link": "https://example.com/research-1",
                    "source": "Journal",
                    "published_utc": "2026-02-18T00:00:00+00:00",
                    "summary": "Summary",
                    "triage_lane": "research",
                },
                {
                    "id": "news-1",
                    "title": "News item",
                    "link": "https://example.com/news-1",
                    "source": "Newsroom",
                    "published_utc": "2026-02-18T00:00:00+00:00",
                    "summary": "Summary",
                    "triage_lane": "news",
                },
            ],
        )

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            write_runner_inputs(root, news_prompt=False)
            weekly.run_weekly(topic="bci", week_spec="2026 week 8", dry_run=0, vault_root=root)

        self.assertEqual(len(triage_calls), 1)
        self.assertTrue(triage_calls[0]["prompt"].endswith("triage_prompt.md"))
        self.assertEqual(triage_calls[0]["ids"], ["research-1", "news-1"])


if __name__ == "__main__":
    unittest.main()
