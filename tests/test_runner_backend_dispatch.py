import importlib.util
import os
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from tocify.integrations import resolve_backend_name


def _load_vault_module():
    path = Path(__file__).resolve().parents[1] / "tocify" / "runner" / "vault.py"
    spec = importlib.util.spec_from_file_location("vault_backend_dispatch_under_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


VAULT = _load_vault_module()


class RunnerBackendDispatchTests(unittest.TestCase):
    def test_backend_resolution_defaults_and_override(self) -> None:
        with patch.dict(os.environ, {"TOCIFY_BACKEND": "", "CURSOR_API_KEY": ""}, clear=False):
            self.assertEqual(resolve_backend_name(), "openai")

        with patch.dict(os.environ, {"TOCIFY_BACKEND": "", "CURSOR_API_KEY": "x"}, clear=False):
            self.assertEqual(resolve_backend_name(), "cursor")

        with patch.dict(os.environ, {"TOCIFY_BACKEND": "gemini"}, clear=False):
            self.assertEqual(resolve_backend_name(), "gemini")

    def test_cursor_backend_raises_actionable_error_when_agent_missing(self) -> None:
        with patch.dict(os.environ, {"TOCIFY_BACKEND": "cursor", "CURSOR_API_KEY": "x"}, clear=False):
            with patch.object(VAULT.subprocess, "run", side_effect=FileNotFoundError("agent")):
                with self.assertRaisesRegex(RuntimeError, "agent` command was not found"):
                    VAULT.run_backend_prompt("hello", purpose="test", trust=True)

    def test_structured_prompt_extracts_json_from_cursor_output(self) -> None:
        completed = types.SimpleNamespace(returncode=0, stdout="prefix {\"ok\": true} suffix", stderr="")
        with patch.dict(os.environ, {"TOCIFY_BACKEND": "cursor", "CURSOR_API_KEY": "x"}, clear=False):
            with patch.object(VAULT.subprocess, "run", return_value=completed):
                parsed = VAULT.run_structured_prompt("prompt", schema={"type": "object"})
        self.assertEqual(parsed, {"ok": True})

    def test_run_agent_and_save_output_uses_fallback_when_cursor_command_fails(self) -> None:
        completed = types.SimpleNamespace(returncode=2, stdout="", stderr="boom")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            output = root / "out.md"
            log = root / "out.log"
            with patch.dict(os.environ, {"TOCIFY_BACKEND": "cursor", "CURSOR_API_KEY": "x"}, clear=False):
                with patch.object(VAULT.subprocess, "run", return_value=completed):
                    VAULT.run_agent_and_save_output("prompt", output, log, "fallback")

            self.assertEqual(output.read_text(encoding="utf-8"), "fallback\n")
            log_text = log.read_text(encoding="utf-8")
            self.assertIn("backend=cursor", log_text)
            self.assertIn("returncode=2", log_text)

    def test_run_agent_and_save_output_preserves_file_written_by_agent_on_empty_stdout(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            output = root / "out.md"
            log = root / "out.log"

            def _run_and_write(*_args, **_kwargs):
                output.write_text("agent wrote file content", encoding="utf-8")
                return types.SimpleNamespace(returncode=0, stdout="", stderr="")

            with patch.dict(os.environ, {"TOCIFY_BACKEND": "cursor", "CURSOR_API_KEY": "x"}, clear=False):
                with patch.object(VAULT.subprocess, "run", side_effect=_run_and_write):
                    VAULT.run_agent_and_save_output("prompt", output, log, "fallback")

            self.assertEqual(output.read_text(encoding="utf-8"), "agent wrote file content\n")
            log_text = log.read_text(encoding="utf-8")
            self.assertIn("used_fallback=False", log_text)
            self.assertIn("preserved_agent_file=True", log_text)

    def test_run_agent_and_save_output_writes_fallback_when_file_unchanged(self) -> None:
        completed = types.SimpleNamespace(returncode=0, stdout="", stderr="")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            output = root / "out.md"
            output.write_text("stale content", encoding="utf-8")
            log = root / "out.log"
            with patch.dict(os.environ, {"TOCIFY_BACKEND": "cursor", "CURSOR_API_KEY": "x"}, clear=False):
                with patch.object(VAULT.subprocess, "run", return_value=completed):
                    VAULT.run_agent_and_save_output("prompt", output, log, "fallback")

            self.assertEqual(output.read_text(encoding="utf-8"), "fallback\n")
            log_text = log.read_text(encoding="utf-8")
            self.assertIn("used_fallback=True", log_text)
            self.assertIn("preserved_agent_file=False", log_text)


if __name__ == "__main__":
    unittest.main()
