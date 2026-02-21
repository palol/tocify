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

    sys.modules.setdefault("tocify", tocify_mod)
    sys.modules.setdefault("tocify.runner", runner_mod)
    sys.modules["tocify.runner.vault"] = vault_mod
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


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class TopicGardenerFootnoteTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
