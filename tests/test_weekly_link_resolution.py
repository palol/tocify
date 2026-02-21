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

    def get_topic_paths(topic: str, vault_root: Path | None = None):
        root = Path(vault_root or ".")
        return types.SimpleNamespace(
            feeds_path=root / "config" / f"feeds.{topic}.txt",
            interests_path=root / "config" / f"interests.{topic}.md",
            prompt_path=root / "config" / "triage_prompt.txt",
            briefs_dir=root / "agent" / "briefs",
            logs_dir=root / "agent" / "logs",
            briefs_articles_csv=root / "config" / "briefs_articles.csv",
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
            "link": "https://canonical.example.com/a",
            "source": "Journal A",
            "published_utc": "2026-02-16T00:00:00+00:00",
            "summary": "Summary A",
        }
    ]
    tocify_mod.keyword_prefilter = lambda items, _keywords, keep_top=200: items
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
                "link": "https://fake.example.com/a",
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

    sys.modules["tocify"] = tocify_mod
    sys.modules["tocify.runner"] = runner_mod
    sys.modules["tocify.runner.vault"] = vault_mod
    sys.modules["tocify.runner.link_hygiene"] = link_hygiene_mod
    sys.modules["tocify.frontmatter"] = frontmatter_mod
    sys.modules["dotenv"] = dotenv_mod
    sys.modules["newspaper"] = newspaper_mod

    weekly_path = Path(__file__).resolve().parents[1] / "tocify" / "runner" / "weekly.py"
    spec = importlib.util.spec_from_file_location("weekly_link_resolution_under_test", weekly_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _write_runner_inputs(root: Path, topic: str = "bci") -> None:
    config_dir = root / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / f"feeds.{topic}.txt").write_text("Example | https://example.com/rss\n", encoding="utf-8")
    (config_dir / f"interests.{topic}.md").write_text("keywords:\n- bci\n", encoding="utf-8")
    (config_dir / "triage_prompt.txt").write_text("Prompt", encoding="utf-8")


class WeeklyLinkResolutionTests(unittest.TestCase):
    def test_run_weekly_rewrites_heading_to_canonical_url(self) -> None:
        weekly = _load_weekly_module()
        weekly.TOPIC_REDUNDANCY_ENABLED = False
        weekly.TOPIC_GARDENER_ENABLED = False

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write_runner_inputs(root)
            weekly.run_weekly(topic="bci", week_spec="2026 week 8", dry_run=0, vault_root=root)
            brief_path = root / "agent" / "briefs" / "2026-02-16_bci_weekly-brief.md"
            content = brief_path.read_text(encoding="utf-8")

        self.assertIn("## [Paper A](https://canonical.example.com/a)", content)
        self.assertNotIn("## [Paper A](https://fake.example.com/a)", content)

    def test_run_weekly_delinks_untrusted_heading_when_resolver_errors(self) -> None:
        weekly = _load_weekly_module()
        weekly.TOPIC_REDUNDANCY_ENABLED = False
        weekly.TOPIC_GARDENER_ENABLED = False
        original_resolver = weekly._resolve_weekly_heading_links
        weekly._resolve_weekly_heading_links = lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("resolver boom")
        )
        try:
            with tempfile.TemporaryDirectory() as td:
                root = Path(td)
                _write_runner_inputs(root)
                weekly.run_weekly(topic="bci", week_spec="2026 week 8", dry_run=0, vault_root=root)
                brief_path = root / "agent" / "briefs" / "2026-02-16_bci_weekly-brief.md"
                content = brief_path.read_text(encoding="utf-8")
        finally:
            weekly._resolve_weekly_heading_links = original_resolver

        self.assertIn("## Paper A", content)
        self.assertNotIn("https://fake.example.com/a", content)


if __name__ == "__main__":
    unittest.main()
