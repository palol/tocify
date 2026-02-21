import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


def _load_quartz_init_module():
    path = Path(__file__).resolve().parents[1] / "tocify" / "runner" / "quartz_init.py"
    spec = importlib.util.spec_from_file_location("quartz_init_under_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules["quartz_init_under_test"] = module
    spec.loader.exec_module(module)
    return module


QUARTZ = _load_quartz_init_module()


def _write_fake_quartz_source(root: Path) -> None:
    for rel in QUARTZ.QUARTZ_SCAFFOLD_PATHS:
        path = root / rel
        if rel == "quartz":
            path.mkdir(parents=True, exist_ok=True)
            (path / "_seed.txt").write_text("quartz seed", encoding="utf-8")
            continue
        if rel == "content":
            path.mkdir(parents=True, exist_ok=True)
            (path / "_seed.txt").write_text("content seed", encoding="utf-8")
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"source:{rel}", encoding="utf-8")


class RunnerQuartzInitTests(unittest.TestCase):
    def test_init_quartz_creates_files_in_empty_target(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "source"
            target = root / "target"
            source.mkdir(parents=True, exist_ok=True)
            target.mkdir(parents=True, exist_ok=True)
            _write_fake_quartz_source(source)

            result = QUARTZ.init_quartz(target=target, source_dir=source, write_local_exclude=False)

            self.assertTrue((target / "package.json").exists())
            self.assertTrue((target / "quartz" / "_seed.txt").exists())
            self.assertTrue((target / "content" / "_seed.txt").exists())
            self.assertEqual(result.skipped, [])
            self.assertEqual(result.overwritten, [])
            self.assertEqual(result.missing_source_paths, [])
            self.assertEqual(result.warnings, [])

    def test_init_quartz_skips_existing_files_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "source"
            target = root / "target"
            source.mkdir(parents=True, exist_ok=True)
            target.mkdir(parents=True, exist_ok=True)
            _write_fake_quartz_source(source)
            package_path = target / "package.json"
            package_path.write_text("local-value", encoding="utf-8")

            result = QUARTZ.init_quartz(target=target, source_dir=source, write_local_exclude=False)

            self.assertEqual(package_path.read_text(encoding="utf-8"), "local-value")
            self.assertIn(package_path.resolve(), [p.resolve() for p in result.skipped])
            self.assertTrue((target / "quartz" / "_seed.txt").exists())

    def test_init_quartz_overwrites_existing_files_when_requested(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "source"
            target = root / "target"
            source.mkdir(parents=True, exist_ok=True)
            target.mkdir(parents=True, exist_ok=True)
            _write_fake_quartz_source(source)
            package_path = target / "package.json"
            package_path.write_text("local-value", encoding="utf-8")

            result = QUARTZ.init_quartz(
                target=target,
                source_dir=source,
                overwrite=True,
                write_local_exclude=False,
            )

            self.assertEqual(package_path.read_text(encoding="utf-8"), "source:package.json")
            self.assertIn(package_path.resolve(), [p.resolve() for p in result.overwritten])

    def test_init_quartz_dry_run_does_not_mutate_files(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "source"
            target = root / "target"
            source.mkdir(parents=True, exist_ok=True)
            target.mkdir(parents=True, exist_ok=True)
            _write_fake_quartz_source(source)
            (target / ".git" / "info").mkdir(parents=True, exist_ok=True)

            result = QUARTZ.init_quartz(
                target=target,
                source_dir=source,
                dry_run=True,
                write_local_exclude=True,
            )

            self.assertFalse((target / "package.json").exists())
            self.assertFalse((target / ".git" / "info" / "exclude").exists())
            self.assertGreater(len(result.created), 0)
            self.assertTrue(result.local_exclude_would_update)
            self.assertFalse(result.local_exclude_updated)

    def test_append_local_excludes_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / ".git" / "info").mkdir(parents=True, exist_ok=True)

            exclude_path, first_updated, _ = QUARTZ.append_local_excludes(root)
            _, second_updated, _ = QUARTZ.append_local_excludes(root)
            text = exclude_path.read_text(encoding="utf-8")

            self.assertTrue(first_updated)
            self.assertFalse(second_updated)
            self.assertEqual(text.count(QUARTZ.LOCAL_EXCLUDE_MARKER_START), 1)
            self.assertEqual(text.count(QUARTZ.LOCAL_EXCLUDE_MARKER_END), 1)

    def test_init_quartz_warns_when_target_is_not_git_repo(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "source"
            target = root / "target"
            source.mkdir(parents=True, exist_ok=True)
            target.mkdir(parents=True, exist_ok=True)
            _write_fake_quartz_source(source)

            result = QUARTZ.init_quartz(target=target, source_dir=source, write_local_exclude=True)

            self.assertTrue((target / "package.json").exists())
            self.assertGreater(len(result.warnings), 0)
            self.assertIn("No .git directory found", result.warnings[0])


if __name__ == "__main__":
    unittest.main()
