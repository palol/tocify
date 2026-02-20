"""Vault layout: per-topic feeds/interests, shared briefs/logs/csv. VAULT_ROOT from BCI_VAULT_ROOT."""

import datetime as dt
import os
import re
import subprocess
import time
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


def _resolve_reference_path(raw_path: str) -> Path:
    candidate = Path(raw_path.strip()).expanduser()
    if candidate.is_absolute():
        return candidate

    vault_candidate = (VAULT_ROOT / candidate).resolve()
    if vault_candidate.exists():
        return vault_candidate
    return candidate.resolve()


def _expand_prompt_references(prompt: str) -> tuple[str, list[Path], int]:
    """Expand lines like '@path/to/file.md' into inline source blocks."""
    max_files = int(os.environ.get("TOCIFY_PROMPT_REF_MAX_FILES", "200"))
    max_chars = int(os.environ.get("TOCIFY_PROMPT_REF_MAX_CHARS", "1000000"))

    out_lines: list[str] = []
    resolved_paths: list[Path] = []
    total_chars = 0

    for line in prompt.splitlines():
        stripped = line.strip()
        match = re.match(r"^@(.+)$", stripped)
        if not match:
            out_lines.append(line)
            continue

        raw_path = match.group(1).strip()
        path = _resolve_reference_path(raw_path)
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"Referenced source file not found: {raw_path} -> {path}")

        text = path.read_text(encoding="utf-8")
        resolved_paths.append(path)
        total_chars += len(text)

        if len(resolved_paths) > max_files:
            raise RuntimeError(
                f"Too many @file references in prompt: {len(resolved_paths)} > {max_files}"
            )
        if total_chars > max_chars:
            raise RuntimeError(
                f"Referenced prompt content too large: {total_chars} chars > {max_chars}"
            )

        out_lines.append(f"[BEGIN SOURCE: {path}]")
        out_lines.append(text)
        out_lines.append(f"[END SOURCE: {path}]")

    return "\n".join(out_lines), resolved_paths, total_chars


def _should_use_openai_backend() -> bool:
    backend = os.environ.get("TOCIFY_BACKEND", "").strip().lower()
    if backend == "openai":
        return True
    if backend:
        return False
    return bool(os.environ.get("OPENAI_API_KEY", "").strip())


def _run_openai_and_save_output(
    prompt: str,
    output_path: Path,
    log_path: Path,
    fallback_content: str,
    *,
    model: str | None = None,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    selected_model = model or os.environ.get("OPENAI_MODEL", "").strip() or "gpt-4o"
    attempts = 0
    response_id = ""
    output_text = ""
    refs: list[Path] = []
    ref_chars = 0
    terminal_error = ""

    try:
        expanded_prompt, refs, ref_chars = _expand_prompt_references(prompt)
    except Exception as e:
        expanded_prompt = ""
        terminal_error = f"{e.__class__.__name__}: {e}"
    else:
        try:
            from openai import APITimeoutError, APIConnectionError, RateLimitError

            from tocify.integrations.openai_triage import make_openai_client

            client = make_openai_client()
            for attempt in range(6):
                attempts = attempt + 1
                try:
                    resp = client.responses.create(model=selected_model, input=expanded_prompt)
                    response_id = getattr(resp, "id", "") or ""
                    output_text = (getattr(resp, "output_text", "") or "").strip()
                    if not output_text:
                        terminal_error = "RuntimeError: Empty output from OpenAI response."
                    break
                except (APITimeoutError, APIConnectionError, RateLimitError) as e:
                    terminal_error = f"{e.__class__.__name__}: {e}"
                    if attempt < 5:
                        time.sleep(min(60, 2**attempt))
                except Exception as e:
                    terminal_error = f"{e.__class__.__name__}: {e}"
                    break
        except Exception as e:
            terminal_error = f"{e.__class__.__name__}: {e}"

    used_fallback = not bool(output_text)
    final_output = output_text or fallback_content
    output_path.write_text(final_output, encoding="utf-8")

    log_lines = [
        "backend=openai",
        f"model={selected_model}",
        f"response_id={response_id or '(none)'}",
        f"attempts={attempts}",
        f"expanded_refs={len(refs)}",
        f"expanded_ref_chars={ref_chars}",
        f"used_fallback={used_fallback}",
        f"output_chars={len(final_output)}",
    ]
    if terminal_error:
        log_lines.append(f"terminal_error={terminal_error}")
    if refs:
        log_lines.append("ref_paths=")
        log_lines.extend(str(p) for p in refs)
    log_path.write_text("\n".join(log_lines) + "\n", encoding="utf-8")


def run_agent_and_save_output(
    prompt: str,
    output_path: Path,
    log_path: Path,
    fallback_content: str,
    *,
    model: str | None = None,
) -> None:
    """Run content generation and save output/log."""
    if _should_use_openai_backend():
        _run_openai_and_save_output(
            prompt,
            output_path,
            log_path,
            fallback_content,
            model=model,
        )
        return

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
