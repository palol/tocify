import importlib.util
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock

from tests.runner_test_utils import write_runner_inputs


def _load_weekly_module():
    tocify_mod = types.ModuleType("tocify")
    runner_mod = types.ModuleType("tocify.runner")
    vault_mod = types.ModuleType("tocify.runner.vault")

    def get_topic_paths(topic: str, vault_root: Path | None = None):
        root = Path(vault_root or ".")
        return types.SimpleNamespace(
            feeds_path=root / "config" / f"feeds.{topic}.txt",
            interests_path=root / "config" / f"interests.{topic}.md",
            prompt_path=root / "config" / "triage_prompt.txt",
            briefs_dir=root / "content" / "briefs",
            logs_dir=root / "content" / "logs",
            briefs_articles_csv=root / "content" / "briefs_articles.csv",
            edgar_ciks_path=root / "config" / f"edgar_ciks.{topic}.txt",
            newsrooms_path=root / "config" / f"newsrooms.{topic}.txt",
        )

    vault_mod.get_topic_paths = get_topic_paths
    vault_mod.VAULT_ROOT = Path(".")
    vault_mod.run_structured_prompt = lambda *_args, **_kwargs: {}

    tocify_mod.parse_interests_md = lambda _text: {"keywords": []}
    tocify_mod.load_feeds = lambda _path: []
    tocify_mod.get_triage_runtime_metadata = lambda: {"triage_backend": "openai", "triage_model": "gpt-4o"}
    tocify_mod.fetch_rss_items = lambda _feeds, end_date=None: [
        {
            "id": "item-1",
            "title": "Paper A",
            "link": "https://example.com/a",
            "source": "Journal A",
            "published_utc": "2026-02-16T00:00:00+00:00",
            "summary": "Summary A",
        }
    ]
    tocify_mod.keyword_prefilter = lambda items, _keywords, keep_top=200, companies=None, **kwargs: items
    tocify_mod.topic_search_string = lambda interests=None, max_keywords=5: ""
    tocify_mod.get_triage_backend_with_metadata = lambda: (
        lambda *_args, **_kwargs: None,
        {"triage_backend": "openai", "triage_model": "gpt-4o"},
    )
    tocify_mod.triage_in_batches = lambda _interests, _items, _batch, _triage_fn: {
        "notes": "Weekly notes.",
        "ranked": [
            {
                "id": "item-1",
                "title": "Paper A",
                "link": "https://example.com/a",
                "source": "Journal A",
                "published_utc": "2026-02-16T00:00:00+00:00",
                "score": 0.9,
                "why": "Relevant.",
                "tags": ["Neuro"],
            }
        ],
    }

    dotenv_mod = types.ModuleType("dotenv")
    dotenv_mod.load_dotenv = lambda *args, **kwargs: None
    newspaper_mod = types.ModuleType("newspaper")
    newspaper_mod.Article = object

    frontmatter_path = Path(__file__).resolve().parents[1] / "tocify" / "frontmatter.py"
    fm_spec = importlib.util.spec_from_file_location("tocify.frontmatter", frontmatter_path)
    frontmatter_mod = importlib.util.module_from_spec(fm_spec)
    assert fm_spec and fm_spec.loader
    fm_spec.loader.exec_module(frontmatter_mod)
    link_hygiene_path = Path(__file__).resolve().parents[1] / "tocify" / "runner" / "link_hygiene.py"
    lh_spec = importlib.util.spec_from_file_location("tocify.runner.link_hygiene", link_hygiene_path)
    link_hygiene_mod = importlib.util.module_from_spec(lh_spec)
    assert lh_spec and lh_spec.loader
    lh_spec.loader.exec_module(link_hygiene_mod)

    clear_mod = types.ModuleType("tocify.runner.clear")
    clear_mod.clean_stray_action_json_in_logs = lambda *args, **kwargs: 0

    sys.modules["tocify"] = tocify_mod
    sys.modules["tocify.runner"] = runner_mod
    sys.modules["tocify.runner.vault"] = vault_mod
    sys.modules["tocify.runner.clear"] = clear_mod
    sys.modules["tocify.runner.link_hygiene"] = link_hygiene_mod
    sys.modules["tocify.frontmatter"] = frontmatter_mod
    sys.modules["dotenv"] = dotenv_mod
    sys.modules["newspaper"] = newspaper_mod

    weekly_path = Path(__file__).resolve().parents[1] / "tocify" / "runner" / "weekly.py"
    spec = importlib.util.spec_from_file_location("weekly_default_behavior_under_test", weekly_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class TopicGardenerDefaultBehaviorTests(unittest.TestCase):
    def test_default_env_enables_topic_gardener(self) -> None:
        previous = os.environ.pop("TOPIC_GARDENER", None)
        try:
            weekly = _load_weekly_module()
            self.assertTrue(weekly.TOPIC_GARDENER_ENABLED)
        finally:
            if previous is not None:
                os.environ["TOPIC_GARDENER"] = previous
            else:
                os.environ.pop("TOPIC_GARDENER", None)

    def test_env_zero_disables_topic_gardener(self) -> None:
        previous = os.environ.get("TOPIC_GARDENER")
        try:
            os.environ["TOPIC_GARDENER"] = "0"
            weekly = _load_weekly_module()
            self.assertFalse(weekly.TOPIC_GARDENER_ENABLED)
        finally:
            if previous is not None:
                os.environ["TOPIC_GARDENER"] = previous
            else:
                os.environ.pop("TOPIC_GARDENER", None)

    def test_run_weekly_calls_gardener_when_enabled(self) -> None:
        weekly = _load_weekly_module()
        weekly.TOPIC_REDUNDANCY_ENABLED = False
        weekly.TOPIC_GARDENER_ENABLED = True
        weekly.run_topic_gardener = Mock()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            write_runner_inputs(root)
            weekly.run_weekly(topic="bci", week_spec="2026 week 8", dry_run=0, vault_root=root)
        weekly.run_topic_gardener.assert_called_once()

    def test_run_weekly_skips_gardener_on_dry_run(self) -> None:
        weekly = _load_weekly_module()
        weekly.TOPIC_REDUNDANCY_ENABLED = False
        weekly.TOPIC_GARDENER_ENABLED = True
        weekly.run_topic_gardener = Mock()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            write_runner_inputs(root)
            weekly.run_weekly(topic="bci", week_spec="2026 week 8", dry_run=1, vault_root=root)
        weekly.run_topic_gardener.assert_not_called()

    def test_run_weekly_skips_gardener_when_disabled(self) -> None:
        weekly = _load_weekly_module()
        weekly.TOPIC_REDUNDANCY_ENABLED = False
        weekly.TOPIC_GARDENER_ENABLED = False
        weekly.run_topic_gardener = Mock()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            write_runner_inputs(root)
            weekly.run_weekly(topic="bci", week_spec="2026 week 8", dry_run=0, vault_root=root)
        weekly.run_topic_gardener.assert_not_called()


if __name__ == "__main__":
    unittest.main()
