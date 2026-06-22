import importlib.util
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path


def _load_vault_module():
    path = Path(__file__).resolve().parents[1] / "tocify" / "runner" / "vault.py"
    spec = importlib.util.spec_from_file_location("vault_paths_under_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules["vault_paths_under_test"] = module
    spec.loader.exec_module(module)
    return module


VAULT = _load_vault_module()


def _write_topic_markdown(path: Path, topic: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\n"
        f'topic: "{topic}"\n'
        f"---\n\n"
        f"# {topic}\n",
        encoding="utf-8",
    )


class RunnerVaultPathsTests(unittest.TestCase):
    def test_get_topic_paths_scopes_feed_dirs_by_topic(self) -> None:
        root = Path("/tmp/example-vault")
        paths = VAULT.get_topic_paths("bci", vault_root=root)

        self.assertEqual(paths.weekly_dir, root / "content" / "feeds" / "weekly" / "bci")
        self.assertEqual(paths.monthly_dir, root / "content" / "feeds" / "monthly" / "bci")
        self.assertEqual(paths.yearly_dir, root / "content" / "feeds" / "yearly" / "bci")
        self.assertEqual(paths.logs_dir, root / "logs")
        self.assertEqual(paths.briefs_articles_csv, root / "content" / "briefs_articles.csv")

    def test_load_briefs_for_date_range_prefers_topic_dir_and_filters_legacy_shared_dir(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            paths = VAULT.get_topic_paths("bci", vault_root=root)
            scoped_week = paths.weekly_dir / "2026 week 08.md"
            legacy_same_week = root / "content" / "feeds" / "weekly" / "2026 week 08.md"
            legacy_bci_week = root / "content" / "feeds" / "weekly" / "2026 week 10.md"
            legacy_other_week = root / "content" / "feeds" / "weekly" / "2026 week 11.md"

            _write_topic_markdown(scoped_week, "bci")
            _write_topic_markdown(legacy_same_week, "bci")
            _write_topic_markdown(legacy_bci_week, "bci")
            _write_topic_markdown(legacy_other_week, "other")

            briefs = VAULT.load_briefs_for_date_range(
                start_date=date.fromisoformat("2026-02-01"),
                end_date=date.fromisoformat("2026-03-31"),
                topic="bci",
                vault_root=root,
            )

        self.assertEqual(briefs, [scoped_week, legacy_bci_week])

    def test_load_monthly_roundups_for_year_prefers_topic_dir_and_filters_legacy_shared_dir(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            paths = VAULT.get_topic_paths("bci", vault_root=root)
            scoped_month = paths.monthly_dir / "2026-02.md"
            legacy_same_month = root / "content" / "feeds" / "monthly" / "2026-02.md"
            legacy_bci_month = root / "content" / "feeds" / "monthly" / "2026-03.md"
            legacy_other_month = root / "content" / "feeds" / "monthly" / "2026-04.md"

            _write_topic_markdown(scoped_month, "bci")
            _write_topic_markdown(legacy_same_month, "bci")
            _write_topic_markdown(legacy_bci_month, "bci")
            _write_topic_markdown(legacy_other_month, "other")

            roundups = VAULT.load_monthly_roundups_for_year(2026, "bci", vault_root=root)

        self.assertEqual(roundups, [scoped_month, legacy_bci_month])


if __name__ == "__main__":
    unittest.main()
