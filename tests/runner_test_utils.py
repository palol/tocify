"""Shared test helpers for runner tests."""

from pathlib import Path


def write_runner_inputs(root: Path, topic: str = "bci") -> None:
    config_dir = root / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / f"feeds.{topic}.txt").write_text(
        "Example | https://example.com/rss\n", encoding="utf-8"
    )
    (config_dir / f"interests.{topic}.md").write_text("keywords:\n- bci\n", encoding="utf-8")
    (config_dir / "triage_prompt.txt").write_text("Prompt", encoding="utf-8")
