import tempfile
import unittest
from pathlib import Path

from tocify.digest import load_feeds
from tocify.triage_lanes import (
    TRIAGE_LANE_NEWS,
    TRIAGE_LANE_RESEARCH,
    default_lane_for_backend,
    filter_ranked_items_by_lane_thresholds,
    merge_ranked_items,
)


class FeedLaneParsingTests(unittest.TestCase):
    def test_load_feeds_parses_optional_lane_suffix(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            feeds_path = Path(td) / "feeds.md"
            feeds_path.write_text(
                "\n".join([
                    "Example Research | https://example.com/research.xml",
                    "Example News | https://example.com/news.xml | news",
                ]),
                encoding="utf-8",
            )

            feeds = load_feeds(str(feeds_path))

        self.assertEqual(feeds[0]["triage_lane"], TRIAGE_LANE_RESEARCH)
        self.assertEqual(feeds[1]["triage_lane"], TRIAGE_LANE_NEWS)


class BackendLaneAssignmentTests(unittest.TestCase):
    def test_news_backends_default_to_news_lane(self) -> None:
        self.assertEqual(default_lane_for_backend("newsapi"), TRIAGE_LANE_NEWS)
        self.assertEqual(default_lane_for_backend("googlenews"), TRIAGE_LANE_NEWS)
        self.assertEqual(default_lane_for_backend("newsrooms"), TRIAGE_LANE_NEWS)

    def test_other_backends_default_to_research_lane(self) -> None:
        self.assertEqual(default_lane_for_backend("openalex"), TRIAGE_LANE_RESEARCH)
        self.assertEqual(default_lane_for_backend("clinicaltrials"), TRIAGE_LANE_RESEARCH)
        self.assertEqual(default_lane_for_backend("edgar"), TRIAGE_LANE_RESEARCH)


class RankedLaneFilteringTests(unittest.TestCase):
    def test_merge_ranked_items_keeps_higher_score_duplicate(self) -> None:
        merged = merge_ranked_items(
            [{"id": "shared", "score": 0.4, "why": "lower"}],
            [{"id": "shared", "score": 0.8, "why": "higher"}],
        )
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["score"], 0.8)
        self.assertEqual(merged[0]["why"], "higher")

    def test_news_threshold_can_keep_item_that_research_threshold_rejects(self) -> None:
        ranked = [
            {"id": "news-1", "score": 0.55},
            {"id": "research-1", "score": 0.55},
        ]
        items_by_id = {
            "news-1": {"triage_lane": TRIAGE_LANE_NEWS},
            "research-1": {"triage_lane": TRIAGE_LANE_RESEARCH},
        }

        kept = filter_ranked_items_by_lane_thresholds(
            ranked,
            items_by_id,
            min_score_read=0.65,
            min_score_read_news=0.5,
            max_returned=10,
        )

        self.assertEqual([row["id"] for row in kept], ["news-1"])


if __name__ == "__main__":
    unittest.main()
