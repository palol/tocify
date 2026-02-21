import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path


def _load_weekly_module():
    tocify_mod = types.ModuleType("tocify")
    runner_mod = types.ModuleType("tocify.runner")
    vault_mod = types.ModuleType("tocify.runner.vault")
    vault_mod.get_topic_paths = lambda *args, **kwargs: None
    vault_mod.VAULT_ROOT = Path(".")
    vault_mod.run_structured_prompt = lambda *_args, **_kwargs: {}
    dotenv_mod = types.ModuleType("dotenv")
    dotenv_mod.load_dotenv = lambda *args, **kwargs: None
    newspaper_mod = types.ModuleType("newspaper")

    class DummyArticle:
        def __init__(self, url: str):
            self.url = url
            self.text = ""

        def download(self) -> None:
            return None

        def parse(self) -> None:
            return None

    newspaper_mod.Article = DummyArticle

    frontmatter_path = Path(__file__).resolve().parents[1] / "tocify" / "frontmatter.py"
    fm_spec = importlib.util.spec_from_file_location("tocify.frontmatter", frontmatter_path)
    frontmatter_mod = importlib.util.module_from_spec(fm_spec)
    assert fm_spec and fm_spec.loader
    fm_spec.loader.exec_module(frontmatter_mod)

    sys.modules.setdefault("tocify", tocify_mod)
    sys.modules.setdefault("tocify.runner", runner_mod)
    sys.modules["tocify.runner.vault"] = vault_mod
    sys.modules["tocify.frontmatter"] = frontmatter_mod
    sys.modules.setdefault("dotenv", dotenv_mod)
    sys.modules.setdefault("newspaper", newspaper_mod)

    weekly_path = Path(__file__).resolve().parents[1] / "tocify" / "runner" / "weekly.py"
    spec = importlib.util.spec_from_file_location("weekly_under_test", weekly_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


WEEKLY = _load_weekly_module()
_apply_topic_action = WEEKLY._apply_topic_action
_split_frontmatter_and_body = sys.modules["tocify.frontmatter"].split_frontmatter_and_body


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
            self.assertIn("## Recent update (2026-02-20)", content)
            self.assertIn("New milestone announced. [^1]", content)
            self.assertIn("[^1]: https://example.com/milestone", content)
            self.assertIn("### New sources", content)

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

    def test_update_with_sources_only_appends_source_refresh_with_footnotes(self) -> None:
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
            self.assertIn("Source refresh. [^1]", content)
            self.assertIn("[^1]: https://example.com/source-only", content)
            self.assertIn("### New sources", content)

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


if __name__ == "__main__":
    unittest.main()
