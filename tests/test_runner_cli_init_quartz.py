import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


def _load_cli_module():
    tocify_mod = types.ModuleType("tocify")
    runner_mod = types.ModuleType("tocify.runner")

    vault_mod = types.ModuleType("tocify.runner.vault")
    vault_mod.list_topics = lambda *args, **kwargs: []
    vault_mod.VAULT_ROOT = Path(".")

    weekly_mod = types.ModuleType("tocify.runner.weekly")
    weekly_mod.run_weekly = lambda *args, **kwargs: None
    weekly_mod.parse_week_spec = lambda *args, **kwargs: None

    monthly_mod = types.ModuleType("tocify.runner.monthly")
    monthly_mod.main = lambda *args, **kwargs: None

    annual_mod = types.ModuleType("tocify.runner.annual")
    annual_mod.main = lambda *args, **kwargs: None

    weeks_mod = types.ModuleType("tocify.runner.weeks")
    weeks_mod.get_month_metadata = lambda month: (Path(month), Path(month), 30)
    weeks_mod.calculate_week_ends = lambda _month: []

    clear_mod = types.ModuleType("tocify.runner.clear")
    clear_mod.main = lambda *args, **kwargs: None
    clear_mod.clean_action_json = lambda *args, **kwargs: 0
    clear_mod.find_stray_action_json = lambda *args, **kwargs: []

    quartz_mod = types.ModuleType("tocify.runner.quartz_init")
    quartz_mod.DEFAULT_QUARTZ_REF = "v4"
    quartz_mod.DEFAULT_QUARTZ_REPO = "https://example.com/quartz.git"
    quartz_mod.init_quartz = lambda *args, **kwargs: types.SimpleNamespace(
        target=Path("."),
        source=Path("."),
        created=[],
        skipped=[],
        overwritten=[],
        missing_source_paths=[],
        warnings=[],
        local_exclude_path=None,
        local_exclude_updated=False,
        local_exclude_would_update=False,
    )

    sys.modules["tocify"] = tocify_mod
    sys.modules["tocify.runner"] = runner_mod
    sys.modules["tocify.runner.vault"] = vault_mod
    sys.modules["tocify.runner.weekly"] = weekly_mod
    sys.modules["tocify.runner.monthly"] = monthly_mod
    sys.modules["tocify.runner.annual"] = annual_mod
    sys.modules["tocify.runner.weeks"] = weeks_mod
    sys.modules["tocify.runner.clear"] = clear_mod
    sys.modules["tocify.runner.quartz_init"] = quartz_mod

    path = Path(__file__).resolve().parents[1] / "tocify" / "runner" / "cli.py"
    spec = importlib.util.spec_from_file_location("runner_cli_under_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class RunnerCliQuartzInitTests(unittest.TestCase):
    def test_init_quartz_requires_target(self) -> None:
        cli = _load_cli_module()
        with patch.object(sys, "argv", ["tocify-runner", "init-quartz"]):
            with self.assertRaises(SystemExit) as ctx:
                cli.main()
        self.assertEqual(ctx.exception.code, 2)

    def test_init_quartz_flag_disables_local_exclude(self) -> None:
        cli = _load_cli_module()
        captured: dict[str, object] = {}

        def _fake_cmd(args):
            captured["write_local_exclude"] = args.write_local_exclude
            captured["target"] = args.target

        cli.cmd_init_quartz = _fake_cmd
        with patch.object(
            sys,
            "argv",
            ["tocify-runner", "init-quartz", "--target", ".", "--no-write-local-exclude"],
        ):
            cli.main()

        self.assertEqual(captured["target"], Path("."))
        self.assertFalse(captured["write_local_exclude"])

    def test_init_quartz_defaults_to_local_exclude_enabled(self) -> None:
        cli = _load_cli_module()
        captured: dict[str, object] = {}

        def _fake_cmd(args):
            captured["write_local_exclude"] = args.write_local_exclude

        cli.cmd_init_quartz = _fake_cmd
        with patch.object(sys, "argv", ["tocify-runner", "init-quartz", "--target", "."]):
            cli.main()

        self.assertTrue(captured["write_local_exclude"])


if __name__ == "__main__":
    unittest.main()

