import tempfile
import unittest
from pathlib import Path

from tests.runner_test_utils import load_weekly_module_for_tests

def _load_weekly_module():
    class DummyArticle:
        def __init__(self, url: str):
            self.url = url
            self.text = ""

        def download(self) -> None:
            return None

        def parse(self) -> None:
            return None

    module, frontmatter_mod = load_weekly_module_for_tests(
        module_name="weekly_under_test",
        newspaper_article_class=DummyArticle,
    )
    return module, frontmatter_mod


WEEKLY, _FRONTMATTER = _load_weekly_module()
_apply_topic_action = WEEKLY._apply_topic_action
_split_frontmatter_and_body = _FRONTMATTER.split_frontmatter_and_body


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class TopicGardenerFootnoteTests(unittest.TestCase):
    def test_create_normalizes_paragraphs_to_fact_bullets(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            _apply_topic_action(
                tmp_path,
                {
                    "action": "create",
                    "slug": "signals",
                    "title": "Signals",
                    "body_markdown": (
                        "A new EEG benchmark was released at https://example.com/eeg. "
                        "Replication score improved in follow-up analysis."
                    ),
                    "sources": [],
                    "links_to": [],
                },
                "2026-02-20",
            )
            content = _read(tmp_path / "signals.md")
            self.assertIn("- A new EEG benchmark was released at https://example.com/eeg.", content)
            self.assertIn("- Replication score improved in follow-up analysis.", content)

    def test_update_normalizes_paragraphs_to_fact_bullets(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            topic_file = tmp_path / "bci.md"
            topic_file.write_text("---\ntitle: \"BCI\"\n---\n\nBase content.", encoding="utf-8")
            _apply_topic_action(
                tmp_path,
                {
                    "action": "update",
                    "slug": "bci",
                    "summary_addendum": (
                        "A decoding challenge posted new data at https://example.com/challenge. "
                        "A second lab reported reproducibility gains."
                    ),
                    "append_sources": [],
                },
                "2026-02-20",
            )
            content = _read(topic_file)
            self.assertIn("## Gardner updates", content)
            self.assertIn("- A decoding challenge posted new data at https://example.com/challenge.", content)
            self.assertIn("- A second lab reported reproducibility gains.", content)

    def test_create_preserves_existing_bulleted_input(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            _apply_topic_action(
                tmp_path,
                {
                    "action": "create",
                    "slug": "policy",
                    "title": "Policy",
                    "body_markdown": "- First fact.\n- Second fact at https://example.com/policy.",
                    "sources": [],
                    "links_to": [],
                },
                "2026-02-20",
            )
            content = _read(tmp_path / "policy.md")
            self.assertIn("- First fact.", content)
            self.assertIn("- Second fact at https://example.com/policy.", content)

    def test_normalize_to_fact_bullets_skips_footnote_definition_lines(self) -> None:
        normalized = WEEKLY._normalize_to_fact_bullets(
            "A new benchmark was released.[^1]\n[^1]: https://example.com/benchmark"
        )
        self.assertIn("- A new benchmark was released.[^1]", normalized)
        self.assertNotIn("- [^1]: https://example.com/benchmark", normalized)

    def test_create_does_not_convert_footnote_definitions_into_bullets(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            _apply_topic_action(
                tmp_path,
                {
                    "action": "create",
                    "slug": "benchmarks",
                    "title": "Benchmarks",
                    "body_markdown": "Primary finding.[^1]\n[^1]: https://example.com/source",
                    "sources": ["https://example.com/source"],
                    "links_to": [],
                },
                "2026-02-20",
            )
            content = _read(tmp_path / "benchmarks.md")
            self.assertNotIn("- [^1]: https://example.com/source", content)

    def test_create_adds_footnotes_from_sources(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            _apply_topic_action(
                tmp_path,
                {
                    "action": "create",
                    "slug": "brain-interface",
                    "title": "Brain Interface",
                    "body_markdown": "A concise summary of this week's development.",
                    "sources": ["https://example.com/a", "https://example.com/b"],
                    "links_to": [],
                },
                "2026-02-20",
            )
            content = _read(tmp_path / "brain-interface.md")
            self.assertIn("A concise summary of this week's development. [^1][^2]", content)
            self.assertIn("[^1]: https://example.com/a", content)
            self.assertIn("[^2]: https://example.com/b", content)

    def test_create_dedupes_duplicate_sources(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            _apply_topic_action(
                tmp_path,
                {
                    "action": "create",
                    "slug": "bci",
                    "title": "BCI",
                    "body_markdown": "Update text.",
                    "sources": ["https://example.com/a", "https://example.com/a"],
                    "links_to": [],
                },
                "2026-02-20",
            )
            content = _read(tmp_path / "bci.md")
            self.assertEqual(content.count("[^1]: https://example.com/a"), 1)
            self.assertNotIn("[^2]:", content)

    def test_create_filters_sources_to_allowed_metadata_urls(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            allowed = WEEKLY._build_allowed_source_url_index([{"link": "https://example.com/a"}])
            _apply_topic_action(
                tmp_path,
                {
                    "action": "create",
                    "slug": "bci",
                    "title": "BCI",
                    "body_markdown": "Update text.",
                    "sources": ["https://example.com/a", "https://fake.example.com/bad"],
                    "links_to": [],
                },
                "2026-02-20",
                allowed_source_url_index=allowed,
            )
            content = _read(tmp_path / "bci.md")
            self.assertIn("[^1]: https://example.com/a", content)
            self.assertNotIn("fake.example.com/bad", content)

    def test_create_delinks_untrusted_inline_urls_when_allowlist_is_provided(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            allowed = WEEKLY._build_allowed_source_url_index([{"link": "https://example.com/a"}])
            _apply_topic_action(
                tmp_path,
                {
                    "action": "create",
                    "slug": "links",
                    "title": "Links",
                    "body_markdown": (
                        "- Trusted source: https://example.com/a\n"
                        "- Untrusted source: https://fake.example.com/b"
                    ),
                    "sources": [],
                    "links_to": [],
                },
                "2026-02-20",
                allowed_source_url_index=allowed,
            )
            content = _read(tmp_path / "links.md")

        self.assertIn("https://example.com/a", content)
        self.assertNotIn("https://fake.example.com/b", content)
        self.assertIn("(link removed)", content)

    def test_update_with_non_allowed_summary_url_raises(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            topic_file = tmp_path / "bci.md"
            topic_file.write_text("---\ntitle: \"BCI\"\n---\n\nBase content.", encoding="utf-8")
            allowed = WEEKLY._build_allowed_source_url_index([{"link": "https://example.com/a"}])
            with self.assertRaisesRegex(ValueError, "no source URLs"):
                _apply_topic_action(
                    tmp_path,
                    {
                        "action": "update",
                        "slug": "bci",
                        "summary_addendum": "Details are in https://fake.example.com/report.",
                        "append_sources": [],
                    },
                    "2026-02-20",
                    allowed_source_url_index=allowed,
                )

    def test_update_addendum_with_append_sources_gets_footnotes(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            topic_file = tmp_path / "bci.md"
            topic_file.write_text("---\ntitle: \"BCI\"\n---\n\nBase content.", encoding="utf-8")
            _apply_topic_action(
                tmp_path,
                {
                    "action": "update",
                    "slug": "bci",
                    "summary_addendum": "New milestone announced.",
                    "append_sources": ["https://example.com/milestone"],
                },
                "2026-02-20",
            )
            content = _read(topic_file)
            self.assertIn("## Gardner updates", content)
            self.assertIn("- New milestone announced. [^1]", content)
            self.assertIn("[^1]: https://example.com/milestone", content)
            self.assertNotIn("## Recent update", content)
            self.assertNotIn("### New sources", content)

    def test_update_extracts_source_url_from_summary_when_append_sources_empty(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            topic_file = tmp_path / "bci.md"
            topic_file.write_text("---\ntitle: \"BCI\"\n---\n\nBase content.", encoding="utf-8")
            _apply_topic_action(
                tmp_path,
                {
                    "action": "update",
                    "slug": "bci",
                    "summary_addendum": "Details are in https://example.com/report.",
                    "append_sources": [],
                },
                "2026-02-20",
            )
            content = _read(topic_file)
            self.assertIn("Details are in https://example.com/report. [^1]", content)
            self.assertIn("[^1]: https://example.com/report", content)

    def test_update_delinks_untrusted_inline_urls_when_allowlist_is_provided(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            topic_file = tmp_path / "bci.md"
            topic_file.write_text("---\ntitle: \"BCI\"\n---\n\nBase content.", encoding="utf-8")
            allowed = WEEKLY._build_allowed_source_url_index([{"link": "https://example.com/allowed"}])
            _apply_topic_action(
                tmp_path,
                {
                    "action": "update",
                    "slug": "bci",
                    "summary_addendum": (
                        "Trusted note at https://example.com/allowed. "
                        "Ignore https://fake.example.com/untrusted."
                    ),
                    "append_sources": ["https://example.com/allowed"],
                },
                "2026-02-20",
                allowed_source_url_index=allowed,
            )
            content = _read(topic_file)

        self.assertIn("https://example.com/allowed", content)
        self.assertNotIn("https://fake.example.com/untrusted", content)
        self.assertIn("(link removed)", content)

    def test_update_with_sources_only_does_not_append_source_refresh(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            topic_file = tmp_path / "bci.md"
            topic_file.write_text("---\ntitle: \"BCI\"\n---\n\nBase content.", encoding="utf-8")
            _apply_topic_action(
                tmp_path,
                {
                    "action": "update",
                    "slug": "bci",
                    "append_sources": ["https://example.com/source-only"],
                },
                "2026-02-20",
            )
            content = _read(topic_file)
            self.assertEqual(content, "---\ntitle: \"BCI\"\n---\n\nBase content.")

    def test_create_with_body_and_no_source_urls_raises(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            with self.assertRaisesRegex(ValueError, "no source URLs"):
                _apply_topic_action(
                    tmp_path,
                    {
                        "action": "create",
                        "slug": "bci",
                        "title": "BCI",
                        "body_markdown": "Unsourced text.",
                        "sources": [],
                        "links_to": [],
                    },
                    "2026-02-20",
                )

    def test_create_writes_frontmatter_tags_and_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            _apply_topic_action(
                tmp_path,
                {
                    "action": "create",
                    "slug": "neurorights",
                    "title": "Neurorights",
                    "body_markdown": "Policy developments this week.",
                    "sources": ["https://example.com/policy"],
                    "links_to": ["ethics"],
                    "tags": ["Neuro Rights", "Policy"],
                },
                "2026-02-20",
                default_tags=["BCI", "Policy"],
                topic="bci",
                triage_backend="openai",
                triage_model="gpt-4o",
            )
            content = _read(tmp_path / "neurorights.md")
            frontmatter, _ = _split_frontmatter_and_body(content)
            self.assertEqual(frontmatter.get("generator"), "tocify-gardener")
            self.assertEqual(frontmatter.get("period"), "evergreen")
            self.assertEqual(frontmatter.get("topic"), "bci")
            self.assertEqual(frontmatter.get("triage_backend"), "openai")
            self.assertEqual(frontmatter.get("triage_model"), "gpt-4o")
            self.assertEqual(frontmatter.get("tags"), ["neuro-rights", "policy", "bci"])

    def test_update_refreshes_frontmatter_and_merges_sources(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            topic_file = tmp_path / "bci.md"
            topic_file.write_text(
                (
                    "---\n"
                    "title: \"BCI\"\n"
                    "date: \"2026-01-01\"\n"
                    "lastmod: \"2026-01-01\"\n"
                    "tags:\n"
                    "  - \"legacy\"\n"
                    "sources:\n"
                    "  - \"https://example.com/old\"\n"
                    "---\n\n"
                    "Base content."
                ),
                encoding="utf-8",
            )
            _apply_topic_action(
                tmp_path,
                {
                    "action": "update",
                    "slug": "bci",
                    "summary_addendum": "New report details.",
                    "append_sources": ["https://example.com/new"],
                    "tags": ["Neuro"],
                },
                "2026-02-20",
                default_tags=["BCI"],
                topic="bci",
                triage_backend="gemini",
                triage_model="gemini-2.0-flash",
            )
            content = _read(topic_file)
            frontmatter, _ = _split_frontmatter_and_body(content)
            self.assertEqual(frontmatter.get("lastmod"), "2026-02-20")
            self.assertEqual(frontmatter.get("triage_backend"), "gemini")
            self.assertEqual(frontmatter.get("triage_model"), "gemini-2.0-flash")
            self.assertIn("https://example.com/old", frontmatter.get("sources", []))
            self.assertIn("https://example.com/new", frontmatter.get("sources", []))
            self.assertEqual(frontmatter.get("tags"), ["legacy", "neuro", "bci"])

    def test_update_creates_single_gardner_updates_section(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            topic_file = tmp_path / "bci.md"
            topic_file.write_text("---\ntitle: \"BCI\"\n---\n\nHuman paragraph.", encoding="utf-8")
            _apply_topic_action(
                tmp_path,
                {
                    "action": "update",
                    "slug": "bci",
                    "summary_addendum": "- New fact one.\n- New fact two.",
                    "summary_addendum_sources": ["https://example.com/a", "https://example.com/b"],
                    "append_sources": [],
                },
                "2026-02-20",
            )
            content = _read(topic_file)
            self.assertEqual(content.count("## Gardner updates"), 1)
            self.assertIn("Human paragraph.\n\n## Gardner updates", content)
            self.assertIn("- New fact one. [^1]", content)
            self.assertIn("- New fact two. [^2]", content)
            self.assertIn("[^1]: https://example.com/a", content)
            self.assertIn("[^2]: https://example.com/b", content)

    def test_update_appends_to_existing_gardner_updates_section(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            topic_file = tmp_path / "bci.md"
            topic_file.write_text(
                (
                    "---\n"
                    "title: \"BCI\"\n"
                    "---\n\n"
                    "Human paragraph.\n\n"
                    "## Gardner updates\n\n"
                    "- Existing fact. [^1]\n\n"
                    "[^1]: https://example.com/old\n"
                ),
                encoding="utf-8",
            )
            _apply_topic_action(
                tmp_path,
                {
                    "action": "update",
                    "slug": "bci",
                    "summary_addendum": "- New fact.",
                    "append_sources": ["https://example.com/new"],
                },
                "2026-02-20",
            )
            content = _read(topic_file)
            self.assertEqual(content.count("## Gardner updates"), 1)
            self.assertIn("- Existing fact. [^1]", content)
            self.assertIn("- New fact. [^2]", content)
            self.assertIn("[^1]: https://example.com/old", content)
            self.assertIn("[^2]: https://example.com/new", content)


if __name__ == "__main__":
    unittest.main()
