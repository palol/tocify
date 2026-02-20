"""Vault layout: per-topic feeds/interests, shared briefs/logs/csv. VAULT_ROOT from BCI_VAULT_ROOT."""

import datetime as dt
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

VAULT_ROOT = Path(os.environ.get("BCI_VAULT_ROOT", ".")).resolve()
CONFIG_DIR = VAULT_ROOT / "config"
AGENT_DIR = VAULT_ROOT / "agent"
BRIEFS_DIR = AGENT_DIR / "briefs"
LOGS_DIR = AGENT_DIR / "logs"
TOPICS_DIR = VAULT_ROOT / "topics"


@dataclass(frozen=True)
class TopicPaths:
    """Paths for a single topic (unified briefs/logs/csv dirs; per-topic feeds/interests)."""

    feeds_path: Path
    interests_path: Path
    briefs_dir: Path
    logs_dir: Path
    briefs_articles_csv: Path
    prompt_path: Path


def get_topic_paths(topic: str, vault_root: Path | None = None) -> TopicPaths:
    """Return paths for the given topic. Same briefs_dir, logs_dir, csv for all topics."""
    root = vault_root or VAULT_ROOT
    config = root / "config"
    agent = root / "agent"
    return TopicPaths(
        feeds_path=config / f"feeds.{topic}.txt",
        interests_path=config / f"interests.{topic}.md",
        briefs_dir=agent / "briefs",
        logs_dir=agent / "logs",
        briefs_articles_csv=config / "briefs_articles.csv",
        prompt_path=config / "triage_prompt.txt",
    )


def list_topics(vault_root: Path | None = None) -> list[str]:
    """Discover topics from config: glob feeds.*.txt; require interests.<topic>.md to exist."""
    root = vault_root or VAULT_ROOT
    config = root / "config"
    topics = []
    if not config.exists():
        return topics
    for path in config.glob("feeds.*.txt"):
        stem = path.stem
        if stem.startswith("feeds."):
            topic = stem[6:].strip()
            if topic and (config / f"interests.{topic}.md").exists():
                topics.append(topic)
    return sorted(topics)


def load_briefs_for_date_range(
    start_date: dt.date, end_date: dt.date, topic: str, vault_root: Path | None = None
) -> list[Path]:
    """Load weekly briefs for the topic that fall within the date range."""
    root = vault_root or VAULT_ROOT
    briefs_dir = root / "agent" / "briefs"
    briefs = []
    if not briefs_dir.exists():
        return briefs
    pattern = f"*_{topic}_weekly-brief.md"
    for path in briefs_dir.glob(pattern):
        try:
            stem = path.stem
            suffix = f"_{topic}_weekly-brief"
            if not stem.endswith(suffix):
                continue
            date_str = stem[: -len(suffix)]
            brief_end_date = dt.date.fromisoformat(date_str)
            if start_date <= brief_end_date <= end_date:
                briefs.append(path)
        except (ValueError, TypeError):
            continue
    return sorted(briefs)


def load_monthly_roundups_for_year(
    year: int, topic: str, vault_root: Path | None = None
) -> list[Path]:
    """Load monthly roundups for the topic and year, sorted chronologically."""
    root = vault_root or VAULT_ROOT
    briefs_dir = root / "agent" / "briefs"
    roundups: list[tuple[dt.date, Path]] = []
    if not briefs_dir.exists():
        return []
    suffix = f"_{topic}_monthly-roundup"
    for path in briefs_dir.glob(f"*{suffix}.md"):
        stem = path.stem
        if not stem.endswith(suffix):
            continue
        prefix = stem[: -len(suffix)]
        try:
            if len(prefix) == 10:
                sort_date = dt.date.fromisoformat(prefix)
            elif len(prefix) == 7:
                y, m = int(prefix[:4]), int(prefix[5:7])
                if m == 12:
                    sort_date = dt.date(y, 12, 31)
                else:
                    sort_date = dt.date(y, m + 1, 1) - dt.timedelta(days=1)
            else:
                continue
            if sort_date.year == year:
                roundups.append((sort_date, path))
        except (ValueError, TypeError):
            continue
    roundups.sort(key=lambda x: x[0])
    return [p for _, p in roundups]


def run_agent_and_save_output(
    prompt: str,
    output_path: Path,
    log_path: Path,
    fallback_content: str,
    *,
    model: str | None = None,
) -> None:
    """Run agent with prompt; save output and log."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    mtime_before = output_path.stat().st_mtime if output_path.exists() else 0

    cmd = ["agent", "-p", "--output-format", "text"]
    if model:
        cmd.extend(["--model", model])
    cmd.append(prompt)

    result = subprocess.run(cmd, capture_output=True, text=True, env=os.environ)

    log_parts = []
    if result.stdout:
        log_parts.append(result.stdout)
    if result.stderr:
        log_parts.append(f"\n--- stderr ---\n{result.stderr}")
    if result.returncode != 0:
        log_parts.append(f"\n--- exit code: {result.returncode} ---")
    log_message = "\n".join(log_parts) if log_parts else "No output from agent command"

    stdout_content = (result.stdout or "").strip()
    agent_wrote = False
    if output_path.exists() and output_path.stat().st_mtime > mtime_before:
        agent_wrote = True

    if agent_wrote:
        try:
            content = output_path.read_text(encoding="utf-8")
        except Exception:
            agent_wrote = False
            content = stdout_content or fallback_content
    else:
        content = stdout_content or fallback_content

    log_path.write_text(log_message, encoding="utf-8")
    if not agent_wrote and content:
        output_path.write_text(content, encoding="utf-8")
