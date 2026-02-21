import importlib.util
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


def _load_frontmatter_module():
    path = Path(__file__).resolve().parents[1] / "tocify" / "frontmatter.py"
    spec = importlib.util.spec_from_file_location("tocify.frontmatter", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    sys.modules["tocify.frontmatter"] = module
    return module


def _load_digest_module(frontmatter_module):
    feedparser_mod = types.ModuleType("feedparser")
    feedparser_mod.parse = lambda *_args, **_kwargs: None

    dateutil_mod = types.ModuleType("dateutil")
    dateutil_parser_mod = types.ModuleType("dateutil.parser")
    dateutil_parser_mod.parse = lambda *_args, **_kwargs: None
    dateutil_mod.parser = dateutil_parser_mod

    dotenv_mod = types.ModuleType("dotenv")
    dotenv_mod.load_dotenv = lambda *_args, **_kwargs: None

    sys.modules["feedparser"] = feedparser_mod
    sys.modules["dateutil"] = dateutil_mod
    sys.modules["dateutil.parser"] = dateutil_parser_mod
    sys.modules["dotenv"] = dotenv_mod
    sys.modules["tocify.frontmatter"] = frontmatter_module

    digest_path = Path(__file__).resolve().parents[1] / "tocify" / "digest.py"
    spec = importlib.util.spec_from_file_location("digest_under_test", digest_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _load_monthly_module(frontmatter_module):
    tocify_mod = types.ModuleType("tocify")
    runner_mod = types.ModuleType("tocify.runner")
    vault_mod = types.ModuleType("tocify.runner.vault")
    vault_mod.get_topic_paths = lambda *args, **kwargs: None
    vault_mod.load_briefs_for_date_range = lambda *args, **kwargs: []
    vault_mod.run_agent_and_save_output = lambda *args, **kwargs: None
    vault_mod.VAULT_ROOT = Path(".")
    weeks_mod = types.ModuleType("tocify.runner.weeks")
    weeks_mod.get_month_metadata = lambda month: (Path(month), Path(month), month)
    tqdm_mod = types.ModuleType("tqdm")
    tqdm_mod.tqdm = types.SimpleNamespace(write=lambda *_args, **_kwargs: None)
    link_hygiene_path = Path(__file__).resolve().parents[1] / "tocify" / "runner" / "link_hygiene.py"
    lh_spec = importlib.util.spec_from_file_location("tocify.runner.link_hygiene", link_hygiene_path)
    link_hygiene_mod = importlib.util.module_from_spec(lh_spec)
    assert lh_spec and lh_spec.loader
    lh_spec.loader.exec_module(link_hygiene_mod)

    _utils_path = Path(__file__).resolve().parents[1] / "tocify" / "runner" / "_utils.py"
    _utils_spec = importlib.util.spec_from_file_location("tocify.runner._utils", _utils_path)
    _utils_mod = importlib.util.module_from_spec(_utils_spec)
    assert _utils_spec and _utils_spec.loader
    _utils_spec.loader.exec_module(_utils_mod)

    roundup_common_path = Path(__file__).resolve().parents[1] / "tocify" / "runner" / "roundup_common.py"
    roundup_spec = importlib.util.spec_from_file_location("tocify.runner.roundup_common", roundup_common_path)
    roundup_mod = importlib.util.module_from_spec(roundup_spec)
    assert roundup_spec and roundup_spec.loader
    roundup_spec.loader.exec_module(roundup_mod)

    sys.modules["tocify"] = tocify_mod
    sys.modules["tocify.runner"] = runner_mod
    sys.modules["tocify.runner.vault"] = vault_mod
    sys.modules["tocify.runner.weeks"] = weeks_mod
    sys.modules["tocify.runner.link_hygiene"] = link_hygiene_mod
    sys.modules["tocify.runner._utils"] = _utils_mod
    sys.modules["tocify.runner.roundup_common"] = roundup_mod
    sys.modules["tocify.frontmatter"] = frontmatter_module
    sys.modules["tqdm"] = tqdm_mod

    monthly_path = Path(__file__).resolve().parents[1] / "tocify" / "runner" / "monthly.py"
    spec = importlib.util.spec_from_file_location("monthly_under_test", monthly_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _load_annual_module(frontmatter_module):
    tocify_mod = types.ModuleType("tocify")
    runner_mod = types.ModuleType("tocify.runner")
    vault_mod = types.ModuleType("tocify.runner.vault")
    vault_mod.get_topic_paths = lambda *args, **kwargs: None
    vault_mod.load_monthly_roundups_for_year = lambda *args, **kwargs: []
    vault_mod.run_agent_and_save_output = lambda *args, **kwargs: None
    vault_mod.VAULT_ROOT = Path(".")
    tqdm_mod = types.ModuleType("tqdm")
    tqdm_mod.tqdm = types.SimpleNamespace(write=lambda *_args, **_kwargs: None)
    link_hygiene_path = Path(__file__).resolve().parents[1] / "tocify" / "runner" / "link_hygiene.py"
    lh_spec = importlib.util.spec_from_file_location("tocify.runner.link_hygiene", link_hygiene_path)
    link_hygiene_mod = importlib.util.module_from_spec(lh_spec)
    assert lh_spec and lh_spec.loader
    lh_spec.loader.exec_module(link_hygiene_mod)

    _utils_path = Path(__file__).resolve().parents[1] / "tocify" / "runner" / "_utils.py"
    _utils_spec = importlib.util.spec_from_file_location("tocify.runner._utils", _utils_path)
    _utils_mod = importlib.util.module_from_spec(_utils_spec)
    assert _utils_spec and _utils_spec.loader
    _utils_spec.loader.exec_module(_utils_mod)

    roundup_common_path = Path(__file__).resolve().parents[1] / "tocify" / "runner" / "roundup_common.py"
    roundup_spec = importlib.util.spec_from_file_location("tocify.runner.roundup_common", roundup_common_path)
    roundup_mod = importlib.util.module_from_spec(roundup_spec)
    assert roundup_spec and roundup_spec.loader
    roundup_spec.loader.exec_module(roundup_mod)

    sys.modules["tocify"] = tocify_mod
    sys.modules["tocify.runner"] = runner_mod
    sys.modules["tocify.runner.vault"] = vault_mod
    sys.modules["tocify.runner.link_hygiene"] = link_hygiene_mod
    sys.modules["tocify.runner._utils"] = _utils_mod
    sys.modules["tocify.runner.roundup_common"] = roundup_mod
    sys.modules["tocify.frontmatter"] = frontmatter_module
    sys.modules["tqdm"] = tqdm_mod

    annual_path = Path(__file__).resolve().parents[1] / "tocify" / "runner" / "annual.py"
    spec = importlib.util.spec_from_file_location("annual_under_test", annual_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _load_integrations_module():
    path = Path(__file__).resolve().parents[1] / "tocify" / "integrations" / "__init__.py"
    spec = importlib.util.spec_from_file_location("integrations_under_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


FRONTMATTER = _load_frontmatter_module()
DIGEST = _load_digest_module(FRONTMATTER)
MONTHLY = _load_monthly_module(FRONTMATTER)
ANNUAL = _load_annual_module(FRONTMATTER)
ROUNDUP_COMMON = sys.modules["tocify.runner.roundup_common"]
INTEGRATIONS = _load_integrations_module()


class FrontmatterGenerationTests(unittest.TestCase):
    def test_digest_render_includes_provenance_and_ai_tags(self) -> None:
        result = {
            "week_of": "2026-02-16",
            "notes": "Weekly highlights.",
            "triage_backend": "openai",
            "triage_model": "gpt-4o",
            "ranked": [
                {
                    "id": "1",
                    "title": "Paper A",
                    "link": "https://example.com/a",
                    "source": "Journal A",
                    "published_utc": "2026-02-15T00:00:00+00:00",
                    "score": 0.9,
                    "why": "Important.",
                    "tags": ["Neuro", "Brain Interface"],
                },
                {
                    "id": "2",
                    "title": "Paper B",
                    "link": "https://example.com/b",
                    "source": "Journal B",
                    "published_utc": "2026-02-14T00:00:00+00:00",
                    "score": 0.8,
                    "why": "Also relevant.",
                    "tags": ["Neuro", "Clinical Trials"],
                },
            ],
        }
        items_by_id = {"1": {"summary": "Summary A"}, "2": {"summary": "Summary B"}}

        content = DIGEST.render_digest_md(result, items_by_id)
        frontmatter, body = FRONTMATTER.split_frontmatter_and_body(content)

        self.assertEqual(frontmatter.get("generator"), "tocify-digest")
        self.assertEqual(frontmatter.get("triage_backend"), "openai")
        self.assertEqual(frontmatter.get("triage_model"), "gpt-4o")
        self.assertEqual(frontmatter.get("tags"), ["neuro", "brain-interface", "clinical-trials"])
        self.assertIn("# Weekly ToC Digest", body)

    def test_monthly_source_metadata_mixed_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            p1 = root / "2026-02-16_bci_weekly-brief.md"
            p2 = root / "2026-02-23_bci_weekly-brief.md"
            p1.write_text(
                """---
triage_backend: \"openai\"
triage_model: \"gpt-4o\"
tags:
  - \"neuro\"
  - \"policy\"
---

# Week 1
""",
                encoding="utf-8",
            )
            p2.write_text(
                """---
triage_backend: \"gemini\"
triage_model: \"gemini-2.0-flash\"
tags:
  - \"neuro\"
  - \"clinical\"
---

# Week 2
""",
                encoding="utf-8",
            )
            metadata = ROUNDUP_COMMON.collect_source_metadata([p1, p2])

        self.assertEqual(metadata["triage_backend"], "mixed")
        self.assertEqual(metadata["triage_model"], "mixed")
        self.assertEqual(metadata["triage_backends"], ["gemini", "openai"])
        self.assertEqual(metadata["triage_models"], ["gemini-2.0-flash", "gpt-4o"])
        self.assertEqual(metadata["tags"], ["neuro", "clinical", "policy"])

    def test_frontmatter_replacement_is_idempotent(self) -> None:
        initial = """---
title: \"Old\"
---

# Body
"""
        updated = FRONTMATTER.with_frontmatter(
            initial,
            {
                "title": "New",
                "date": "2026-02-21",
                "lastmod": "2026-02-21",
                "tags": ["neuro"],
            },
        )
        updated_again = FRONTMATTER.with_frontmatter(
            updated,
            {
                "title": "New",
                "date": "2026-02-21",
                "lastmod": "2026-02-21",
                "tags": ["neuro"],
            },
        )
        self.assertEqual(updated, updated_again)
        frontmatter, body = FRONTMATTER.split_frontmatter_and_body(updated)
        self.assertEqual(frontmatter["title"], "New")
        self.assertEqual(frontmatter["tags"], ["neuro"])
        self.assertIn("# Body", body)

    def test_monthly_link_hygiene_keeps_trusted_and_delinks_untrusted(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "weekly.md"
            source.write_text("## [Paper A](https://example.com/a)\n", encoding="utf-8")
            output = root / "monthly.md"
            output.write_text(
                (
                    "Trusted: [Paper A](https://example.com/a)\n"
                    "Untrusted: [Paper B](https://fake.example.com/b)\n"
                    "Raw fake: https://fake.example.com/raw.\n"
                ),
                encoding="utf-8",
            )
            allowed = ROUNDUP_COMMON.build_allowed_url_index_from_sources([source])
            stats = ROUNDUP_COMMON.sanitize_output_links(output, allowed)
            sanitized = output.read_text(encoding="utf-8")

        self.assertIn("[Paper A](https://example.com/a)", sanitized)
        self.assertIn("Untrusted: Paper B", sanitized)
        self.assertNotIn("https://fake.example.com/b", sanitized)
        self.assertNotIn("https://fake.example.com/raw", sanitized)
        self.assertGreaterEqual(stats["delinked"], 2)

    def test_annual_link_hygiene_keeps_trusted_and_delinks_untrusted(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "roundup.md"
            source.write_text("Reference: https://example.com/allowed\n", encoding="utf-8")
            output = root / "annual.md"
            output.write_text(
                (
                    "Allowed raw: https://example.com/allowed\n"
                    "Untrusted raw: https://fake.example.com/blocked\n"
                    "Untrusted md: [Blocked](https://fake.example.com/blocked-md)\n"
                ),
                encoding="utf-8",
            )
            allowed = ROUNDUP_COMMON.build_allowed_url_index_from_sources([source])
            stats = ROUNDUP_COMMON.sanitize_output_links(output, allowed)
            sanitized = output.read_text(encoding="utf-8")

        self.assertIn("https://example.com/allowed", sanitized)
        self.assertNotIn("https://fake.example.com/blocked", sanitized)
        self.assertNotIn("https://fake.example.com/blocked-md", sanitized)
        self.assertIn("Untrusted md: Blocked", sanitized)
        self.assertGreaterEqual(stats["delinked"], 2)

    def test_runtime_metadata_resolves_backend_and_model(self) -> None:
        env = {
            "TOCIFY_BACKEND": "",
            "CURSOR_API_KEY": "",
            "OPENAI_MODEL": "",
            "GEMINI_MODEL": "",
            "CURSOR_MODEL": "",
        }
        with patch.dict(os.environ, env, clear=False):
            self.assertEqual(
                INTEGRATIONS.get_triage_runtime_metadata(),
                {"triage_backend": "openai", "triage_model": "gpt-4o"},
            )

        with patch.dict(os.environ, {"TOCIFY_BACKEND": "gemini", "GEMINI_MODEL": "gemini-2.5-pro"}, clear=False):
            self.assertEqual(
                INTEGRATIONS.get_triage_runtime_metadata(),
                {"triage_backend": "gemini", "triage_model": "gemini-2.5-pro"},
            )

        with patch.dict(os.environ, {"TOCIFY_BACKEND": "", "CURSOR_API_KEY": "x", "CURSOR_MODEL": ""}, clear=False):
            self.assertEqual(
                INTEGRATIONS.get_triage_runtime_metadata(),
                {"triage_backend": "cursor", "triage_model": "unknown"},
            )


if __name__ == "__main__":
    unittest.main()
