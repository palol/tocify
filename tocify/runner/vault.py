"""Vault layout: per-topic feeds/interests, shared briefs/logs/csv. VAULT_ROOT from BCI_VAULT_ROOT."""

import datetime as dt
import json
import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

VAULT_ROOT = Path(os.environ.get("BCI_VAULT_ROOT", ".")).resolve()
CONFIG_DIR = VAULT_ROOT / "config"
CONTENT_DIR = VAULT_ROOT / "content"
BRIEFS_DIR = CONTENT_DIR / "briefs"
LOGS_DIR = CONTENT_DIR / "logs"
TOPICS_DIR = CONTENT_DIR / "topics"

_BACKEND_MODEL_DEFAULTS: dict[str, tuple[str, str]] = {
    "openai": ("OPENAI_MODEL", "gpt-4o"),
    "gemini": ("GEMINI_MODEL", "gemini-2.0-flash"),
    "cursor": ("CURSOR_MODEL", "unknown"),
}


@dataclass(frozen=True)
class TopicPaths:
    """Paths for a single topic (unified briefs/logs/csv dirs; per-topic feeds/interests)."""

    feeds_path: Path
    interests_path: Path
    briefs_dir: Path
    logs_dir: Path
    briefs_articles_csv: Path
    prompt_path: Path


@dataclass
class PromptRunResult:
    """Result metadata for one backend prompt run."""

    backend: str
    model: str
    output_text: str = ""
    attempts: int = 0
    response_id: str = ""
    refs: list[Path] = field(default_factory=list)
    ref_chars: int = 0
    terminal_error: str = ""
    command: list[str] = field(default_factory=list)
    returncode: int = 0
    stderr: str = ""


def get_topic_paths(topic: str, vault_root: Path | None = None) -> TopicPaths:
    """Return paths for the given topic. Same briefs_dir, logs_dir, csv for all topics."""
    root = vault_root or VAULT_ROOT
    config = root / "config"
    content = root / "content"
    return TopicPaths(
        feeds_path=config / f"feeds.{topic}.txt",
        interests_path=config / f"interests.{topic}.md",
        briefs_dir=content / "briefs",
        logs_dir=content / "logs",
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
    briefs_dir = root / "content" / "briefs"
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
    briefs_dir = root / "content" / "briefs"
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


def _resolve_runner_backend_name() -> str:
    backend = os.getenv("TOCIFY_BACKEND", "").strip().lower()
    if not backend:
        backend = "cursor" if os.getenv("CURSOR_API_KEY", "").strip() else "openai"
    if backend not in _BACKEND_MODEL_DEFAULTS:
        known = sorted(_BACKEND_MODEL_DEFAULTS)
        raise RuntimeError(
            f"Unknown TOCIFY_BACKEND={backend!r}. Known: {known}. "
            "Set TOCIFY_BACKEND=openai|cursor|gemini or configure API keys."
        )
    return backend


def _resolve_runner_model(backend: str, model: str | None) -> str:
    model_env, default_model = _BACKEND_MODEL_DEFAULTS[backend]
    if model and model.strip():
        return model.strip()
    env_model = os.getenv(model_env, "").strip()
    if env_model:
        return env_model
    return default_model


def _maybe_expand_prompt(
    prompt: str,
    *,
    backend: str,
    expand_refs: bool | None,
) -> tuple[str, list[Path], int]:
    should_expand = backend in ("openai", "gemini") if expand_refs is None else bool(expand_refs)
    if not should_expand:
        return prompt, [], 0
    return _expand_prompt_references(prompt)


def _extract_json_object_text(response_text: str) -> str:
    start = response_text.find("{")
    end = response_text.rfind("}") + 1
    if start < 0 or end <= start:
        raise ValueError("No JSON object found in model output")
    return response_text[start:end]


def _run_openai_prompt(
    prompt: str,
    *,
    model: str,
    purpose: str,
    json_schema: dict | None,
    expand_refs: bool | None,
    raise_on_error: bool,
) -> PromptRunResult:
    result = PromptRunResult(backend="openai", model=model)
    try:
        expanded_prompt, refs, ref_chars = _maybe_expand_prompt(
            prompt,
            backend="openai",
            expand_refs=expand_refs,
        )
        result.refs = refs
        result.ref_chars = ref_chars
    except Exception as e:
        result.terminal_error = f"{e.__class__.__name__}: {e}"
        if raise_on_error:
            raise RuntimeError(f"openai {purpose} failed: {result.terminal_error}") from e
        return result

    try:
        import httpx
        from openai import APITimeoutError, APIConnectionError, OpenAI, RateLimitError
    except Exception as e:
        result.terminal_error = f"{e.__class__.__name__}: {e}"
        if raise_on_error:
            raise RuntimeError(f"openai {purpose} failed: {result.terminal_error}") from e
        return result

    try:
        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not api_key.startswith("sk-"):
            raise RuntimeError("OPENAI_API_KEY missing/invalid (expected to start with 'sk-').")
        http_client = httpx.Client(
            timeout=httpx.Timeout(connect=30.0, read=300.0, write=30.0, pool=30.0),
            http2=False,
            trust_env=False,
            headers={"Connection": "close", "Accept-Encoding": "gzip"},
        )
        client = OpenAI(api_key=api_key, http_client=http_client)
    except Exception as e:
        result.terminal_error = f"{e.__class__.__name__}: {e}"
        if raise_on_error:
            raise RuntimeError(f"openai {purpose} failed: {result.terminal_error}") from e
        return result

    for attempt in range(6):
        result.attempts = attempt + 1
        try:
            kwargs: dict[str, Any] = {"model": model, "input": expanded_prompt}
            if json_schema is not None:
                kwargs["text"] = {
                    "format": {
                        "type": "json_schema",
                        "name": "runner_structured_output",
                        "schema": json_schema,
                        "strict": True,
                    }
                }
            response = client.responses.create(**kwargs)
            result.response_id = getattr(response, "id", "") or ""
            result.output_text = (getattr(response, "output_text", "") or "").strip()
            if result.output_text:
                return result
            result.terminal_error = "RuntimeError: Empty output from OpenAI response."
        except (APITimeoutError, APIConnectionError, RateLimitError) as e:
            result.terminal_error = f"{e.__class__.__name__}: {e}"
            if attempt < 5:
                time.sleep(min(60, 2**attempt))
        except Exception as e:
            result.terminal_error = f"{e.__class__.__name__}: {e}"
            break

    if raise_on_error:
        raise RuntimeError(f"openai {purpose} failed: {result.terminal_error or 'unknown error'}")
    return result


def _run_gemini_prompt(
    prompt: str,
    *,
    model: str,
    purpose: str,
    json_schema: dict | None,
    expand_refs: bool | None,
    raise_on_error: bool,
) -> PromptRunResult:
    result = PromptRunResult(backend="gemini", model=model)
    try:
        expanded_prompt, refs, ref_chars = _maybe_expand_prompt(
            prompt,
            backend="gemini",
            expand_refs=expand_refs,
        )
        result.refs = refs
        result.ref_chars = ref_chars
    except Exception as e:
        result.terminal_error = f"{e.__class__.__name__}: {e}"
        if raise_on_error:
            raise RuntimeError(f"gemini {purpose} failed: {result.terminal_error}") from e
        return result

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        result.terminal_error = "RuntimeError: GEMINI_API_KEY missing/invalid."
        if raise_on_error:
            raise RuntimeError(f"gemini {purpose} failed: {result.terminal_error}")
        return result

    try:
        from google import genai
    except Exception as e:
        result.terminal_error = f"{e.__class__.__name__}: {e}"
        if raise_on_error:
            raise RuntimeError(f"gemini {purpose} failed: {result.terminal_error}") from e
        return result

    try:
        client = genai.Client(api_key=api_key)
    except Exception as e:
        result.terminal_error = f"{e.__class__.__name__}: {e}"
        if raise_on_error:
            raise RuntimeError(f"gemini {purpose} failed: {result.terminal_error}") from e
        return result

    for attempt in range(6):
        result.attempts = attempt + 1
        try:
            config_candidates: list[dict[str, Any] | None]
            if json_schema is None:
                config_candidates = [None]
            else:
                config_candidates = [
                    {"response_mime_type": "application/json", "response_schema": json_schema},
                    {"response_mime_type": "application/json", "response_json_schema": json_schema},
                ]

            response_text = ""
            last_type_error: Exception | None = None
            for config in config_candidates:
                try:
                    if config is None:
                        response = client.models.generate_content(model=model, contents=expanded_prompt)
                    else:
                        response = client.models.generate_content(
                            model=model,
                            contents=expanded_prompt,
                            config=config,
                        )
                    response_text = (getattr(response, "text", "") or "").strip()
                    if response_text:
                        break
                except TypeError as e:
                    last_type_error = e

            if not response_text and last_type_error is not None:
                raise RuntimeError("Gemini client rejected schema config; check google-genai version.") from last_type_error
            if not response_text:
                raise RuntimeError("Empty response text from Gemini")
            result.output_text = response_text
            return result
        except Exception as e:
            result.terminal_error = f"{e.__class__.__name__}: {e}"
            if attempt < 5:
                time.sleep(min(60, 2**attempt))

    if raise_on_error:
        raise RuntimeError(f"gemini {purpose} failed: {result.terminal_error or 'unknown error'}")
    return result


def _run_cursor_prompt(
    prompt: str,
    *,
    model: str,
    purpose: str,
    trust: bool,
    raise_on_error: bool,
) -> PromptRunResult:
    result = PromptRunResult(backend="cursor", model=model)
    cmd = ["agent", "-p", "--output-format", "text"]
    if trust:
        cmd.append("--trust")
    if model and model != "unknown":
        cmd.extend(["--model", model])
    cmd.append(prompt)

    try:
        completed = subprocess.run(cmd, capture_output=True, text=True, env=os.environ)
    except FileNotFoundError as e:
        raise RuntimeError(
            "Cursor backend selected but `agent` command was not found on PATH. "
            "Install Cursor CLI agent support or set TOCIFY_BACKEND=openai|gemini."
        ) from e

    result.command = cmd
    result.returncode = int(getattr(completed, "returncode", 0) or 0)
    result.output_text = (completed.stdout or "").strip()
    result.stderr = (completed.stderr or "").strip()
    if result.returncode != 0:
        result.terminal_error = (
            f"cursor {purpose} exit {result.returncode}: "
            f"{result.stderr or result.output_text or 'no output'}"
        )
        if raise_on_error:
            raise RuntimeError(result.terminal_error)
    return result


def run_backend_prompt(
    prompt: str,
    *,
    model: str | None = None,
    purpose: str = "runner",
    json_schema: dict | None = None,
    expand_refs: bool | None = None,
    trust: bool = False,
    raise_on_error: bool = True,
) -> PromptRunResult:
    """Run a prompt through the active backend and return result metadata."""
    backend = _resolve_runner_backend_name()
    selected_model = _resolve_runner_model(backend, model)

    if backend == "openai":
        return _run_openai_prompt(
            prompt,
            model=selected_model,
            purpose=purpose,
            json_schema=json_schema,
            expand_refs=expand_refs,
            raise_on_error=raise_on_error,
        )
    if backend == "gemini":
        return _run_gemini_prompt(
            prompt,
            model=selected_model,
            purpose=purpose,
            json_schema=json_schema,
            expand_refs=expand_refs,
            raise_on_error=raise_on_error,
        )
    return _run_cursor_prompt(
        prompt,
        model=selected_model,
        purpose=purpose,
        trust=trust,
        raise_on_error=raise_on_error,
    )


def run_structured_prompt(
    prompt: str,
    *,
    schema: dict,
    model: str | None = None,
    purpose: str = "runner-structured",
    expand_refs: bool | None = None,
    trust: bool = False,
) -> dict:
    """Run a prompt and parse the first JSON object from model output."""
    result = run_backend_prompt(
        prompt,
        model=model,
        purpose=purpose,
        json_schema=schema,
        expand_refs=expand_refs,
        trust=trust,
        raise_on_error=True,
    )
    response_text = (result.output_text or "").strip()
    if not response_text:
        raise ValueError("No JSON object found in model output")
    try:
        return json.loads(_extract_json_object_text(response_text))
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in model output: {e}") from e


def _build_prompt_log(
    result: PromptRunResult,
    final_output: str,
    used_fallback: bool,
    preserved_agent_file: bool,
) -> str:
    lines = [
        f"backend={result.backend}",
        f"model={result.model}",
        f"response_id={result.response_id or '(none)'}",
        f"attempts={result.attempts}",
        f"expanded_refs={len(result.refs)}",
        f"expanded_ref_chars={result.ref_chars}",
        f"used_fallback={used_fallback}",
        f"preserved_agent_file={preserved_agent_file}",
        f"output_chars={len(final_output)}",
    ]
    if result.command:
        lines.append("command=" + " ".join(result.command))
    if result.returncode:
        lines.append(f"returncode={result.returncode}")
    if result.terminal_error:
        lines.append(f"terminal_error={result.terminal_error}")
    if result.refs:
        lines.append("ref_paths=")
        lines.extend(str(p) for p in result.refs)
    if result.stderr:
        lines.append("stderr=")
        lines.append(result.stderr)
    return "\n".join(lines) + "\n"


def run_agent_and_save_output(
    prompt: str,
    output_path: Path,
    log_path: Path,
    fallback_content: str,
    *,
    model: str | None = None,
) -> None:
    """Run content generation and save output/log."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    output_pre_exists = output_path.exists()
    output_pre_mtime_ns: int | None = None
    if output_pre_exists:
        try:
            output_pre_mtime_ns = output_path.stat().st_mtime_ns
        except OSError:
            output_pre_mtime_ns = None

    result = run_backend_prompt(
        prompt,
        model=model,
        purpose="runner-generation",
        expand_refs=None,
        trust=False,
        raise_on_error=False,
    )

    response_text = (result.output_text or "").strip()
    used_fallback = not bool(response_text)
    preserved_agent_file = False

    if used_fallback:
        output_post_exists = output_path.exists()
        output_post_mtime_ns: int | None = None
        if output_post_exists:
            try:
                output_post_mtime_ns = output_path.stat().st_mtime_ns
            except OSError:
                output_post_mtime_ns = None

        file_changed_during_run = False
        if output_post_exists and not output_pre_exists:
            file_changed_during_run = True
        elif output_pre_exists and output_post_exists:
            if output_pre_mtime_ns is not None and output_post_mtime_ns is not None:
                file_changed_during_run = output_post_mtime_ns != output_pre_mtime_ns
            else:
                file_changed_during_run = True

        if file_changed_during_run and output_post_exists:
            preserved_agent_file = True
            used_fallback = False
            try:
                final_output = output_path.read_text(encoding="utf-8")
            except OSError:
                final_output = ""
        else:
            final_output = fallback_content
            output_path.write_text(final_output, encoding="utf-8")
    else:
        final_output = response_text
        output_path.write_text(final_output, encoding="utf-8")

    log_path.write_text(
        _build_prompt_log(result, final_output, used_fallback, preserved_agent_file),
        encoding="utf-8",
    )
