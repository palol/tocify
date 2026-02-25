import unittest

from tests.runner_test_utils import load_weekly_module_for_tests


def _load_weekly_module():
    module, _ = load_weekly_module_for_tests(module_name="weekly_normalization_under_test")
    return module


WEEKLY = _load_weekly_module()


class WeeklyNormalizationTests(unittest.TestCase):
    def test_normalize_ranked_items_converts_legacy_score_and_canonicalizes_fields(self) -> None:
        items_by_id = {
            "item-1": {
                "id": "item-1",
                "title": "Canonical Title",
                "link": "https://canonical.example.com/a",
                "source": "Canonical Journal",
                "published_utc": "2026-02-16T00:00:00+00:00",
            }
        }
        ranked = [
            {
                "id": "item-1",
                "title": "Model Title",
                "link": "https://fake.example.com/a",
                "source": "Fake Journal",
                "published_utc": "2020-01-01T00:00:00+00:00",
                "score": 95,
                "why": "Line one\nline two " * 30,
                "tags": [
                    "Neuro  ",
                    "neuro",
                    "Very long tag that should definitely be truncated at forty chars",
                    "Methods",
                    "Timescales",
                    "Signal",
                    "BCI",
                    "EEG",
                    "Extra",
                ],
            }
        ]

        normalized, counters = WEEKLY.normalize_ranked_items(ranked, items_by_id)

        self.assertEqual(len(normalized), 1)
        row = normalized[0]
        self.assertEqual(row["id"], "item-1")
        self.assertEqual(row["title"], "Canonical Title")
        self.assertEqual(row["link"], "https://canonical.example.com/a")
        self.assertEqual(row["source"], "Canonical Journal")
        self.assertEqual(row["published_utc"], "2026-02-16T00:00:00+00:00")
        self.assertEqual(row["score"], 0.95)
        self.assertNotIn("\n", row["why"])
        self.assertLessEqual(len(row["why"]), 320)
        self.assertLessEqual(len(row["tags"]), 8)
        self.assertTrue(all(len(tag) <= 40 for tag in row["tags"]))
        self.assertEqual(counters["score_legacy_percent_converted"], 1)
        self.assertGreaterEqual(counters["tags_trimmed"], 1)
        self.assertEqual(counters["why_trimmed"], 1)

    def test_normalize_ranked_items_drops_unknown_ids_and_invalid_scores(self) -> None:
        items_by_id = {
            "item-1": {"id": "item-1", "title": "A", "link": "https://a.example.com", "source": "J", "published_utc": None}
        }
        ranked = [
            {"id": "missing", "score": 0.9, "why": "x", "tags": ["a"]},
            {"id": "item-1", "score": 150, "why": "x", "tags": ["a"]},
            "not-a-dict",
        ]

        normalized, counters = WEEKLY.normalize_ranked_items(ranked, items_by_id)

        self.assertEqual(normalized, [])
        self.assertEqual(counters["dropped_invalid_id"], 2)
        self.assertEqual(counters["dropped_invalid_score"], 1)

    def test_normalize_ranked_items_duplicate_id_keeps_highest_score_even_if_later(self) -> None:
        items_by_id = {
            "item-1": {"id": "item-1", "title": "A", "link": "https://a.example.com", "source": "J", "published_utc": None}
        }
        ranked = [
            {"id": "item-1", "score": 0.2, "why": "lower", "tags": ["a"]},
            {"id": "item-1", "score": 0.9, "why": "higher", "tags": ["b"]},
        ]

        normalized, counters = WEEKLY.normalize_ranked_items(ranked, items_by_id)

        self.assertEqual(len(normalized), 1)
        self.assertEqual(normalized[0]["score"], 0.9)
        self.assertEqual(normalized[0]["why"], "higher")
        self.assertEqual(counters["duplicate_id_resolved"], 1)

    def test_normalize_ranked_items_duplicate_id_tie_keeps_later_entry(self) -> None:
        items_by_id = {
            "item-1": {"id": "item-1", "title": "A", "link": "https://a.example.com", "source": "J", "published_utc": None}
        }
        ranked = [
            {"id": "item-1", "score": 0.5, "why": "first", "tags": ["a"]},
            {"id": "item-1", "score": 0.5, "why": "second", "tags": ["b"]},
        ]

        normalized, _counters = WEEKLY.normalize_ranked_items(ranked, items_by_id)

        self.assertEqual(len(normalized), 1)
        self.assertEqual(normalized[0]["why"], "second")
        self.assertEqual(normalized[0]["tags"], ["b"])


if __name__ == "__main__":
    unittest.main()
