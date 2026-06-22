import csv
import importlib.util
import tempfile
import unittest
from pathlib import Path


def _load_script_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "clean_briefs_articles.py"
    spec = importlib.util.spec_from_file_location("clean_briefs_articles_under_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


CLEAN = _load_script_module()


class CleanBriefsArticlesTests(unittest.TestCase):
    def test_clean_csv_dry_run_reports_changes_without_mutating_file(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            csv_path = root / "briefs_articles.csv"
            csv_path.write_text(
                (
                    "topic,week_of,url,title,source,published_utc,score,brief_filename,why,tags\n"
                    "bci,2026-02-16,https://example.com/a,Paper A,Journal,2026-02-16,95,brief.md,"
                    "\"why with\\nline break\",Neuro|neuro|Very long tag that should definitely be truncated at forty chars\n"
                ),
                encoding="utf-8",
            )
            before = csv_path.read_text(encoding="utf-8")

            counters = CLEAN.clean_csv(csv_path, apply=False)

            after = csv_path.read_text(encoding="utf-8")

        self.assertEqual(before, after)
        self.assertEqual(counters["rows_total"], 1)
        self.assertEqual(counters["rows_changed"], 1)
        self.assertEqual(counters["score_legacy_percent_converted"], 1)
        self.assertGreaterEqual(counters["tags_trimmed"], 1)

    def test_clean_csv_apply_mutates_file_and_creates_backup(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            csv_path = root / "briefs_articles.csv"
            csv_path.write_text(
                (
                    "topic,week_of,url,title,source,published_utc,score,brief_filename,why,tags\n"
                    "bci,2026-02-16,https://example.com/a,Paper A,Journal,2026-02-16,150,brief.md,"
                    "\"why\",A|A|B|C|D|E|F|G|H\n"
                ),
                encoding="utf-8",
            )

            counters = CLEAN.clean_csv(csv_path, apply=True)

            backups = list(root.glob("briefs_articles.csv.bak-*"))
            with open(csv_path, newline="", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))

        self.assertEqual(counters["rows_total"], 1)
        self.assertEqual(counters["rows_changed"], 1)
        self.assertEqual(counters["score_invalid_cleared"], 1)
        self.assertEqual(len(backups), 1)
        self.assertEqual(rows[0]["score"], "")
        self.assertEqual(rows[0]["tags"], "A|B|C|D|E|F|G|H")


if __name__ == "__main__":
    unittest.main()
