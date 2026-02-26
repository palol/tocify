import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock

from tests.runner_test_utils import load_weekly_module_for_tests, write_runner_inputs


def _load_weekly_module_with_frontmatter():
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

    module, frontmatter_mod = load_weekly_module_for_tests(
        module_name="weekly_redundant_mentions_under_test",
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
                "ranked": [],
            },
        },
    )
    return module, frontmatter_mod


def _load_weekly_module():
    module, _ = _load_weekly_module_with_frontmatter()
    return module


WEEKLY, _FRONTMATTER = _load_weekly_module_with_frontmatter()
split_frontmatter_and_body = _FRONTMATTER.split_frontmatter_and_body


class TopicRedundantMentionsTests(unittest.TestCase):
    def test_call_topic_redundancy_parses_mentions_and_falls_back_to_item_link(self) -> None:
        original_call = WEEKLY.run_structured_prompt
        try:
            WEEKLY.run_structured_prompt = lambda *_args, **_kwargs: {
                "redundant_ids": ["item-1"],
                "redundant_mentions": [
                    {
                        "id": "item-1",
                        "topic_slug": "bci",
                        "matched_fact_bullet": "- Existing fact.",
                        "source_url": "",
                    }
                ],
            }
            redundant_ids, mentions = WEEKLY._call_cursor_topic_redundancy(
                [Path("topics/bci.md")],
                [
                    {
                        "id": "item-1",
                        "title": "Paper A",
                        "link": "https://example.com/a",
                        "source": "Journal A",
                        "summary": "Summary A",
                    }
                ],
            )
        finally:
            WEEKLY.run_structured_prompt = original_call

        self.assertEqual(redundant_ids, {"item-1"})
        self.assertEqual(len(mentions), 1)
        self.assertEqual(mentions[0]["source_url"], "https://example.com/a")

    def test_call_topic_redundancy_ignores_non_metadata_source_url(self) -> None:
        original_call = WEEKLY.run_structured_prompt
        try:
            WEEKLY.run_structured_prompt = lambda *_args, **_kwargs: {
                "redundant_ids": ["item-1"],
                "redundant_mentions": [
                    {
                        "id": "item-1",
                        "topic_slug": "bci",
                        "matched_fact_bullet": "- Existing fact.",
                        "source_url": "https://fake.example.com/not-in-metadata",
                    }
                ],
            }
            _redundant_ids, mentions = WEEKLY._call_cursor_topic_redundancy(
                [Path("topics/bci.md")],
                [
                    {
                        "id": "item-1",
                        "title": "Paper A",
                        "link": "https://example.com/a",
                        "source": "Journal A",
                        "summary": "Summary A",
                    }
                ],
            )
        finally:
            WEEKLY.run_structured_prompt = original_call

        self.assertEqual(len(mentions), 1)
        self.assertEqual(mentions[0]["source_url"], "https://example.com/a")

    def test_call_topic_redundancy_drops_mention_without_metadata_url(self) -> None:
        original_call = WEEKLY.run_structured_prompt
        try:
            WEEKLY.run_structured_prompt = lambda *_args, **_kwargs: {
                "redundant_ids": ["item-1"],
                "redundant_mentions": [
                    {
                        "id": "item-1",
                        "topic_slug": "bci",
                        "matched_fact_bullet": "- Existing fact.",
                        "source_url": "https://fake.example.com/not-in-metadata",
                    }
                ],
            }
            _redundant_ids, mentions = WEEKLY._call_cursor_topic_redundancy(
                [Path("topics/bci.md")],
                [
                    {
                        "id": "item-1",
                        "title": "Paper A",
                        "link": "",
                        "source": "Journal A",
                        "summary": "Summary A",
                    }
                ],
            )
        finally:
            WEEKLY.run_structured_prompt = original_call

        self.assertEqual(mentions, [])

    def test_apply_redundant_mention_to_body_adds_footnote_without_updating_existing_count_suffix(self) -> None:
        body = (
            "- Existing fact. [^1] _(mentions: 1 sources)_\n\n"
            "[^1]: https://example.com/old"
        )
        updated, status = WEEKLY._apply_redundant_mention_to_body(
            body,
            "- Existing fact.",
            "https://example.com/new",
        )
        self.assertEqual(status, "applied")
        self.assertIn("- Existing fact. [^1][^2] _(mentions: 1 sources)_", updated)
        self.assertIn("[^2]: https://example.com/new", updated)

    def test_apply_redundant_mention_to_body_adds_footnote_without_adding_count_suffix(self) -> None:
        body = "- Existing fact. [^1]\n\n[^1]: https://example.com/old"
        updated, status = WEEKLY._apply_redundant_mention_to_body(
            body,
            "- Existing fact.",
            "https://example.com/new",
        )
        self.assertEqual(status, "applied")
        self.assertIn("- Existing fact. [^1][^2]", updated)
        self.assertNotIn("_(mentions:", updated)
        self.assertIn("[^2]: https://example.com/new", updated)

    def test_apply_redundant_mention_to_body_noop_when_already_recorded(self) -> None:
        body = (
            "- Existing fact. [^1] _(mentions: 1 sources)_\n\n"
            "[^1]: https://example.com/old"
        )
        updated, status = WEEKLY._apply_redundant_mention_to_body(
            body,
            "- Existing fact.",
            "https://example.com/old",
        )
        self.assertEqual(status, "already_recorded")
        self.assertEqual(updated, body)

    def test_apply_redundant_mentions_updates_frontmatter_and_body(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            topics_dir = tmp_path / "topics"
            topics_dir.mkdir(parents=True, exist_ok=True)
            topic_file = topics_dir / "bci.md"
            topic_file.write_text(
                (
                    "---\n"
                    "title: \"BCI\"\n"
                    "lastmod: \"2026-01-01\"\n"
                    "sources:\n"
                    "  - \"https://example.com/old\"\n"
                    "---\n\n"
                    "- Existing fact. [^1] _(mentions: 1 sources)_\n\n"
                    "[^1]: https://example.com/old\n"
                ),
                encoding="utf-8",
            )
            stats = WEEKLY._apply_redundant_mentions(
                topics_dir,
                [
                    {
                        "topic_slug": "bci",
                        "matched_fact_bullet": "- Existing fact.",
                        "source_url": "https://example.com/new",
                    }
                ],
                "2026-02-21",
            )
            content = topic_file.read_text(encoding="utf-8")
            frontmatter, _ = split_frontmatter_and_body(content)

        self.assertEqual(stats["mentions_applied"], 1)
        self.assertEqual(frontmatter.get("lastmod"), "2026-02-21")
        self.assertEqual(frontmatter.get("updated"), "2026-02-21")
        self.assertIn("https://example.com/new", frontmatter.get("sources", []))
        self.assertIn("- Existing fact. [^1][^2] _(mentions: 1 sources)_", content)
        self.assertIn("[^2]: https://example.com/new", content)

    def test_call_topic_redundancy_prompt_excludes_frontmatter_and_footnote_definitions(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            topic_path = root / "content" / "topics" / "bci.md"
            topic_path.parent.mkdir(parents=True, exist_ok=True)
            topic_path.write_text(
                (
                    "---\n"
                    "title: \"BCI\"\n"
                    "sources:\n"
                    "  - \"https://example.com/old\"\n"
                    "---\n\n"
                    "- Existing fact. [^1]\n\n"
                    "[^1]: https://example.com/old\n"
                ),
                encoding="utf-8",
            )
            captured_prompt: dict[str, str] = {}

            def _fake_call(prompt, **_kwargs):
                captured_prompt["value"] = prompt
                return {"redundant_ids": [], "redundant_mentions": []}

            original_call = WEEKLY.run_structured_prompt
            try:
                WEEKLY.run_structured_prompt = _fake_call
                WEEKLY._call_cursor_topic_redundancy(
                    [topic_path],
                    [
                        {
                            "id": "item-1",
                            "title": "Paper A",
                            "link": "https://example.com/a",
                            "source": "Journal A",
                            "summary": "Summary A",
                        }
                    ],
                )
            finally:
                WEEKLY.run_structured_prompt = original_call

        prompt = captured_prompt.get("value", "")
        self.assertIn("- Existing fact. [^1]", prompt)
        self.assertNotIn("[^1]: https://example.com/old", prompt)
        self.assertNotIn("sources:\n", prompt)

    def test_run_weekly_skips_redundant_mention_application_when_not_dry_run(self) -> None:
        weekly = _load_weekly_module()
        weekly.TOPIC_REDUNDANCY_ENABLED = True
        weekly.TOPIC_GARDENER_ENABLED = False
        weekly._apply_redundant_mentions = Mock(
            return_value={
                "mentions_input": 1,
                "mentions_applied": 1,
                "mentions_already_recorded": 0,
                "mentions_missing_topic": 0,
                "mentions_missing_bullet": 0,
                "mentions_invalid": 0,
                "files_updated": 1,
            }
        )
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            write_runner_inputs(root)
            topics_dir = root / "content" / "topics"
            topics_dir.mkdir(parents=True, exist_ok=True)
            (topics_dir / "bci.md").write_text("---\ntitle: \"BCI\"\n---\n\n- Existing fact.\n", encoding="utf-8")
            weekly.load_recent_topic_files = lambda *_args, **_kwargs: [topics_dir / "bci.md"]
            weekly.filter_topic_redundant_items = lambda *_args, **_kwargs: (
                [],
                1,
                [
                    {
                        "id": "item-1",
                        "topic_slug": "bci",
                        "matched_fact_bullet": "- Existing fact.",
                        "source_url": "https://example.com/a",
                    }
                ],
            )
            weekly.run_weekly(topic="bci", week_spec="2026 week 8", dry_run=0, vault_root=root)
        weekly._apply_redundant_mentions.assert_not_called()

    def test_run_weekly_dry_run_skips_mention_application(self) -> None:
        weekly = _load_weekly_module()
        weekly.TOPIC_REDUNDANCY_ENABLED = True
        weekly.TOPIC_GARDENER_ENABLED = False
        weekly._apply_redundant_mentions = Mock(
            return_value={
                "mentions_input": 1,
                "mentions_applied": 1,
                "mentions_already_recorded": 0,
                "mentions_missing_topic": 0,
                "mentions_missing_bullet": 0,
                "mentions_invalid": 0,
                "files_updated": 1,
            }
        )
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            write_runner_inputs(root)
            topics_dir = root / "content" / "topics"
            topics_dir.mkdir(parents=True, exist_ok=True)
            (topics_dir / "bci.md").write_text("---\ntitle: \"BCI\"\n---\n\n- Existing fact.\n", encoding="utf-8")
            weekly.load_recent_topic_files = lambda *_args, **_kwargs: [topics_dir / "bci.md"]
            weekly.filter_topic_redundant_items = lambda *_args, **_kwargs: (
                [],
                1,
                [
                    {
                        "id": "item-1",
                        "topic_slug": "bci",
                        "matched_fact_bullet": "- Existing fact.",
                        "source_url": "https://example.com/a",
                    }
                ],
            )
            weekly.run_weekly(topic="bci", week_spec="2026 week 8", dry_run=1, vault_root=root)
        weekly._apply_redundant_mentions.assert_not_called()


if __name__ == "__main__":
    unittest.main()
