import tempfile
import types
import unittest
from pathlib import Path

from tests.runner_test_utils import load_weekly_module_for_tests, write_runner_inputs


def _load_weekly_module():
    wrapped = (
        "https://news.google.com/rss/articles/CBMiQ2h0dHBzOi8vbmV3cy5nb29nbGUuY29tL2FydGljbGU"
        "?url=https%3A%2F%2Fexample.com%2Farticle-1&hl=en-US&gl=US&ceid=US:en"
    )

    def get_topic_paths(topic: str, vault_root: Path | None = None):
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

    def triage(_interests, items, _batch, _triage_fn):
        ranked = []
        for item in items:
            ranked.append({
                "id": item["id"],
                "title": item["title"],
                "link": item["link"],
                "source": item["source"],
                "published_utc": item["published_utc"],
                "score": 0.9,
                "why": "Relevant.",
                "tags": ["Neuro"],
            })
        return {"notes": "", "ranked": ranked}

    module, _ = load_weekly_module_for_tests(
        module_name="weekly_google_news_resolution_under_test",
        get_topic_paths=get_topic_paths,
        tocify_overrides={
            "fetch_rss_items": lambda _feeds, end_date=None: [
                {
                    "id": "item-1",
                    "title": "Wrapped",
                    "link": wrapped,
                    "source": "Google News",
                    "published_utc": "2026-02-16T00:00:00+00:00",
                    "summary": "Wrapped summary",
                },
                {
                    "id": "item-2",
                    "title": "Canonical",
                    "link": "https://example.com/article-1",
                    "source": "Publisher",
                    "published_utc": "2026-02-16T00:00:00+00:00",
                    "summary": "Canonical summary",
                },
            ],
            "triage_in_batches": triage,
        },
    )
    return module


class WeeklyGoogleNewsResolutionTests(unittest.TestCase):
    def test_google_news_wrapper_resolves_before_weekly_url_dedupe(self) -> None:
        weekly = _load_weekly_module()
        weekly.TOPIC_REDUNDANCY_ENABLED = False
        weekly.TOPIC_GARDENER_ENABLED = False
        weekly.GOOGLE_NEWS_RESOLVE_LINKS = True

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            write_runner_inputs(root)
            weekly.run_weekly(topic="bci", week_spec="2026 week 8", dry_run=0, vault_root=root)
            brief_path = root / "content" / "briefs" / "2026 week 08.md"
            content = brief_path.read_text(encoding="utf-8")
            csv_text = (root / "content" / "briefs_articles.csv").read_text(encoding="utf-8")

        self.assertNotIn("news.google.com/rss/articles", content)
        self.assertIn("https://example.com/article-1", content)
        self.assertEqual(content.count("## ["), 1)
        self.assertEqual(len([line for line in csv_text.splitlines() if line.strip()]), 2)


if __name__ == "__main__":
    unittest.main()
