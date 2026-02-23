"""Shared test helpers for runner tests."""

from __future__ import annotations

import importlib
import importlib.util
import sys
import types
from pathlib import Path
from typing import Any, Callable


def write_runner_inputs(root: Path, topic: str = "bci") -> None:
    config_dir = root / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / f"feeds.{topic}.txt").write_text(
        "Example | https://example.com/rss\n", encoding="utf-8"
    )
    (config_dir / f"interests.{topic}.md").write_text("keywords:\n- bci\n", encoding="utf-8")
    (config_dir / "triage_prompt.txt").write_text("Prompt", encoding="utf-8")


def load_weekly_module_for_tests(
    *,
    module_name: str,
    get_topic_paths: Callable[..., Any] | None = None,
    run_structured_prompt: Callable[..., Any] | None = None,
    tocify_overrides: dict[str, Any] | None = None,
    newspaper_article_class: type = object,
) -> tuple[types.ModuleType, types.ModuleType]:
    """Load runner/weekly.py with package-aware stubs for deterministic unit tests."""
    project_root = Path(__file__).resolve().parents[1]

    tocify_mod = types.ModuleType("tocify")
    tocify_mod.__path__ = [str(project_root / "tocify")]
    runner_mod = types.ModuleType("tocify.runner")
    runner_mod.__path__ = [str(project_root / "tocify" / "runner")]

    vault_mod = types.ModuleType("tocify.runner.vault")
    vault_mod.get_topic_paths = get_topic_paths or (lambda *_args, **_kwargs: None)
    vault_mod.VAULT_ROOT = Path(".")
    vault_mod.run_structured_prompt = run_structured_prompt or (lambda *_args, **_kwargs: {})

    clear_mod = types.ModuleType("tocify.runner.clear")
    clear_mod.clean_stray_action_json_in_logs = lambda *args, **kwargs: 0

    dotenv_mod = types.ModuleType("dotenv")
    dotenv_mod.load_dotenv = lambda *args, **kwargs: None
    newspaper_mod = types.ModuleType("newspaper")
    newspaper_mod.Article = newspaper_article_class

    default_tocify_stubs: dict[str, Any] = {
        "parse_interests_md": lambda _text: {"keywords": []},
        "load_feeds": lambda _path: [],
        "topic_search_string": lambda interests=None, max_keywords=5: "",
        "topic_search_queries": lambda interests=None, max_keywords=5: [],
        "get_triage_runtime_metadata": lambda: {"triage_backend": "openai", "triage_model": "gpt-4o"},
        "fetch_rss_items": lambda _feeds, end_date=None: [],
        "fetch_historical_items": lambda *_args, **_kwargs: [],
        "merge_feed_items": (
            lambda items, extra, max_items=400: (items + extra)[:max_items] if max_items else (items + extra)
        ),
        "keyword_prefilter": lambda items, _keywords, keep_top=200, companies=None, **kwargs: items,
        "get_triage_backend_with_metadata": lambda: (
            lambda *_args, **_kwargs: None,
            {"triage_backend": "openai", "triage_model": "gpt-4o"},
        ),
        "triage_in_batches": lambda _interests, _items, _batch, _triage_fn: {"notes": "", "ranked": []},
    }
    if tocify_overrides:
        default_tocify_stubs.update(tocify_overrides)
    for name, value in default_tocify_stubs.items():
        setattr(tocify_mod, name, value)

    sys.modules["tocify"] = tocify_mod
    sys.modules["tocify.runner"] = runner_mod
    sys.modules["tocify.runner.vault"] = vault_mod
    sys.modules["tocify.runner.clear"] = clear_mod
    sys.modules["dotenv"] = dotenv_mod
    sys.modules["newspaper"] = newspaper_mod

    # Re-import from the local source tree under the package-aware stubs.
    for module_key in (
        "tocify.config",
        "tocify.frontmatter",
        "tocify.runner._utils",
        "tocify.runner.brief_writer",
        "tocify.runner.link_hygiene",
    ):
        sys.modules.pop(module_key, None)

    frontmatter_mod = importlib.import_module("tocify.frontmatter")
    importlib.import_module("tocify.runner.link_hygiene")

    weekly_path = project_root / "tocify" / "runner" / "weekly.py"
    spec = importlib.util.spec_from_file_location(module_name, weekly_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to create module spec for weekly.py as {module_name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, frontmatter_mod
