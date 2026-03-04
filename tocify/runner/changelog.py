"""Changelog pipeline: git-cliff (optional) + dedupe + add_dates + filter + optional Cursor polish.

Run from vault/repo root. Requires git-cliff binary (e.g. brew install git-cliff) when
run_cliff is True. Polish step requires CURSOR_API_KEY and `agent` on PATH when skip_polish
is False.
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from pathlib import Path

from tocify.runner.prompt_templates import load_prompt_template

# Lines containing any of these (substring, case-insensitive) are dropped.
MINOR_PHRASES = [
    "workflow debug",
    "workflow improvements",
    "weekly flow now works",
    "weekly generation",
    "weekly action just install",
    "monthly action just install",
    "derive email subject dates",
    "derive email dates from brief",
    "install playwright",
    "cursor cli works",
    "quartz build from root",
    "check for dead code",
    "tocify refactor",
    "import tocify",
    "obsidian vault settings",
    "try obsidian-git",
    "archive ready",
    "about files",
    "empty headers",
    "ignore logs and duplicates",
    "rss feeds",
    "manual gardening",
    "map html",
    "feeds folder no file count",
    "hide folder count for feeds",
    "fixed downloads and briefs",
    "colophone",
    "colophon footer url",
    "no latex and broken html",
    "lessen load of articles",
    "homepage update, readme",
    "2026-01",
    "2025 with companies and news",
]

MIN_CONTENT_LENGTH = 14
_DATE_PREFIX = re.compile(r"^- (\d{4}-\d{2}-\d{2}) — ")

_CONSISTENCY_REPLACEMENTS: list[tuple[str, str]] = [
    ("explicitely", "explicitly"),
    ("left aligh ", "left align "),
    ("refresh briefs. to-do- fix hn fetch range", "refresh briefs; to-do: fix hn fetch range"),
    ("Darkmode/", "DarkMode/"),
    ("repairing graph", "repair graph"),
]


def _load_dotenv(repo_root: Path) -> None:
    """Load .env from repo root into os.environ so CURSOR_API_KEY is set if present."""
    env_file = repo_root / ".env"
    if not env_file.is_file():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            key = key.strip()
            if key and key not in os.environ:
                value = value.strip().strip("'\"").strip()
                os.environ[key] = value


def find_repo_root(start: Path) -> Path | None:
    """Return first directory containing .git above or at start, or None."""
    root = start.resolve()
    while True:
        if (root / ".git").exists():
            return root
        parent = root.parent
        if parent == root:
            return None
        root = parent


def _dedupe_changelog(path: Path) -> None:
    """Deduplicate list items (- ...) within each ## section."""
    text = path.read_text()
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    in_section = False
    seen: set[str] = set()
    section_buffer: list[str] = []

    def flush_section() -> None:
        nonlocal section_buffer, seen
        for line in section_buffer:
            stripped = line.strip()
            if stripped.startswith("- "):
                if stripped not in seen:
                    seen.add(stripped)
                    out.append(line)
            else:
                out.append(line)
        section_buffer = []

    for line in lines:
        if line.startswith("## "):
            flush_section()
            seen.clear()
            in_section = True
            out.append(line)
            continue
        if in_section:
            section_buffer.append(line)
        else:
            out.append(line)
    flush_section()
    path.write_text("".join(out))


def _normalize_subject(subject: str) -> str:
    """Strip conventional prefix and normalize for matching."""
    s = re.sub(
        r"^(feat|fix|chg|doc|content|new)(\([^)]+\))?:\s*",
        "",
        subject,
        flags=re.IGNORECASE,
    )
    return s.strip().lower()


def _normalize_changelog_content(content: str) -> str:
    """Remove scope prefix and normalize for lookup."""
    s = re.sub(r"\*\*[^*]+\*\* — ", "", content).strip().lower()
    return s


def _build_message_to_date(repo_root: Path) -> dict[str, str]:
    """Run git log --reverse, return map normalized_message -> YYYY-MM-DD (oldest)."""
    result = subprocess.run(
        ["git", "log", "--all", "--reverse", "--format=%ad\t%s", "--date=short"],
        capture_output=True,
        text=True,
        cwd=repo_root,
    )
    if result.returncode != 0:
        return {}
    message_to_date: dict[str, str] = {}
    for line in result.stdout.splitlines():
        line = line.strip()
        if "\t" not in line:
            continue
        date, subject = line.split("\t", 1)
        key = _normalize_subject(subject)
        if key and key not in message_to_date:
            message_to_date[key] = date
    return message_to_date


def _add_changelog_dates(path: Path, repo_root: Path) -> None:
    """Prepend YYYY-MM-DD from git log to each list line."""
    message_to_date = _build_message_to_date(repo_root)
    lines = path.read_text().splitlines(keepends=True)
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("- "):
            content = stripped[2:].strip()
            key = _normalize_changelog_content(content)
            date = message_to_date.get(key)
            if not date and " — " in content:
                key2 = content.split(" — ", 1)[-1].strip().lower()
                date = message_to_date.get(key2)
            if not date:
                key3 = content.split("—")[-1].strip().lower()
                date = message_to_date.get(key3)
            if date:
                out.append(f"- {date} — {content}\n")
            else:
                out.append(line)
        else:
            out.append(line)
    path.write_text("".join(out))


def _strip_date_prefix(stripped: str) -> tuple[str | None, str]:
    """If line has date prefix, return (date, rest); else (None, stripped)."""
    m = _DATE_PREFIX.match(stripped)
    if m:
        return m.group(1), stripped[m.end() :]
    return None, stripped


def _has_scope(line: str) -> bool:
    """True if list item has scope e.g. '- **quartz** — ...' (maybe with date prefix)."""
    stripped = line.strip()
    if not stripped.startswith("- "):
        return False
    date, rest = _strip_date_prefix(stripped)
    logical = f"- {rest}" if date is not None else stripped
    return bool(re.match(r"^- \*\*[^*]+\*\* —", logical))


def _is_minor(line: str) -> bool:
    """True if line should be dropped as minor/tooling."""
    stripped = line.strip()
    if not stripped.startswith("- "):
        return False
    _, rest = _strip_date_prefix(stripped)
    content = (rest if rest else stripped[2:]).strip().lower()
    if len(content) < MIN_CONTENT_LENGTH:
        return True
    for phrase in MINOR_PHRASES:
        if phrase.lower() in content:
            return True
    return False


def _keep_line(line: str) -> bool:
    """True if this list line should be kept."""
    stripped = line.strip()
    if not stripped.startswith("- "):
        return True
    date, rest = _strip_date_prefix(stripped)
    logical = f"- {rest}" if date is not None else stripped
    if _has_scope(logical):
        return True
    if _is_minor(logical):
        return False
    return True


def _normalize_quartz(line: str) -> str:
    """Make 'quartz' consistently bold in list lines (preserve date prefix if present)."""
    stripped = line.strip()
    if not stripped.startswith("- "):
        return line
    date, rest = _strip_date_prefix(stripped)
    logical = f"- {rest}" if date is not None else stripped
    normalized = re.sub(
        r"(?<!\*)\bquartz\b(?!\*)",
        "**quartz**",
        logical,
        flags=re.IGNORECASE,
    )
    if date:
        normalized = f"- {date} — {normalized[2:]}"
    if line.endswith("\n"):
        normalized = normalized + "\n"
    return normalized


def _filter_changelog(path: Path) -> None:
    """Keep only important entries; normalize **quartz**."""
    lines = path.read_text().splitlines(keepends=True)
    out: list[str] = []
    for line in lines:
        if _keep_line(line):
            out.append(_normalize_quartz(line))
    path.write_text("".join(out))


def _extract_body(response_text: str) -> str | None:
    """Extract changelog body from agent stdout: from opening --- to end.

    Handles leading prose, code fences, and relaxed frontmatter (--- with title: in next lines).
    Returns None if no body found.
    """
    stripped = response_text.strip()
    if stripped.startswith("```"):
        match = re.match(
            r"^```(?:markdown|md)?\s*\n(.*)(?:\n```\s*$)?", stripped, re.DOTALL
        )
        if match:
            stripped = match.group(1).strip()
    lines = stripped.splitlines()
    lookahead = 10
    for i, line in enumerate(lines):
        if line.strip() != "---":
            continue
        chunk = (
            "\n".join(lines[i : i + lookahead])
            if i + lookahead <= len(lines)
            else "\n".join(lines[i:])
        )
        if "title:" in chunk:
            return "\n".join(lines[i:]).rstrip()
    if stripped.startswith("---") and "title:" in stripped[:500]:
        return stripped.rstrip()
    match = re.search(r"\n---\s*\n[\s\S]*?title:", stripped)
    if match:
        start = match.start() + 1
        return stripped[start:].rstrip()
    return None


def _apply_fallback_fixes(content: str) -> str:
    """Apply known typo/wording fixes when agent did not return the full document."""
    result = content
    for old, new in _CONSISTENCY_REPLACEMENTS:
        result = result.replace(old, new)
    return result


def _run_polish(
    changelog_path: Path,
    repo_root: Path,
    prompt_path: Path | None,
) -> None:
    """Run Cursor agent to polish changelog; extract body or apply fallback fixes."""
    _load_dotenv(repo_root)
    if not os.environ.get("CURSOR_API_KEY", "").strip():
        print("changelog: skip polish (CURSOR_API_KEY not set)")
        return
    config_prompt_path = repo_root / "config" / "changelog_consistency_prompt.txt"
    path = prompt_path if prompt_path is not None else (
        config_prompt_path if config_prompt_path.is_file() else None
    )
    instructions = load_prompt_template("changelog_consistency_prompt.txt", path)
    content = changelog_path.read_text()
    prompt = f"{instructions}\n\n---\n\n{content}"
    timeout = int(os.environ.get("TOCIFY_CURSOR_TIMEOUT", "0")) or 120
    with tempfile.NamedTemporaryFile(
        mode="w", delete=False, suffix=".txt", encoding="utf-8"
    ) as f:
        f.write(prompt)
        temp_path = f.name
    try:
        result = subprocess.run(
            ["agent", "-p", temp_path, "--output-format", "text", "--trust"],
            capture_output=True,
            text=True,
            env=os.environ,
            timeout=timeout,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"agent exit {result.returncode}: "
                f"{result.stderr or result.stdout or 'no output'}"
            )
        response_text = (result.stdout or "").strip()
    except FileNotFoundError:
        raise SystemExit(
            "changelog: 'agent' not on PATH. Install Cursor CLI, then export PATH=\"$HOME/.cursor/bin:$PATH\""
        ) from None
    except subprocess.TimeoutExpired:
        raise SystemExit(f"changelog: agent timed out (>{timeout}s)") from None
    finally:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
    body = _extract_body(response_text)
    if body is None:
        debug_path = repo_root / "changelog_agent_last_response.txt"
        try:
            debug_path.write_text(response_text, encoding="utf-8")
        except OSError:
            pass
        body = _apply_fallback_fixes(content)
        changelog_path.write_text(body + "\n")
        print(
            "changelog: applied fallback consistency fixes (agent returned summary, not full doc)"
        )
    else:
        changelog_path.write_text(body + "\n")
        print("changelog: polished with Cursor agent")


def run_changelog_pipeline(
    changelog_path: Path,
    repo_root: Path,
    *,
    run_cliff: bool = True,
    cliff_path: Path | None = None,
    skip_polish: bool = False,
    prompt_path: Path | None = None,
) -> None:
    """Run full changelog pipeline: optional git-cliff, then dedupe, add_dates, filter, optional polish.

    - changelog_path: Path to the changelog file (must exist after git-cliff if run_cliff).
    - repo_root: Git repo root for git log and git-cliff cwd. Used for .env and config/ prompt override.
    - run_cliff: If True and cliff.toml exists, run git-cliff (cliff.toml must set output to changelog_path).
    - cliff_path: Path to cliff.toml (default repo_root/cliff.toml).
    - skip_polish: If True, skip Cursor agent polish step.
    - prompt_path: Override path to changelog_consistency_prompt.txt (default repo_root/config/).
    """
    if not changelog_path.exists() and not run_cliff:
        raise FileNotFoundError(f"Changelog file not found: {changelog_path}")
    resolved_cliff = (cliff_path or repo_root / "cliff.toml").resolve()
    if run_cliff and resolved_cliff.is_file():
        if not changelog_path.exists():
            # git-cliff will create it; ensure parent exists
            changelog_path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git-cliff", "-c", str(resolved_cliff)],
            cwd=repo_root,
            check=True,
        )
        if not changelog_path.exists():
            raise FileNotFoundError(
                f"git-cliff did not produce {changelog_path}; set output in cliff.toml to this path"
            )
    _dedupe_changelog(changelog_path)
    _add_changelog_dates(changelog_path, repo_root)
    _filter_changelog(changelog_path)
    if not skip_polish:
        _run_polish(changelog_path, repo_root, prompt_path)
