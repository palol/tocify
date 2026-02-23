"""Cursor CLI triage backend. Needs CURSOR_API_KEY and `agent` on PATH."""

import json
import os
import subprocess
import time

from tocify.integrations._shared import (
    build_triage_prompt,
    extract_first_json_object,
    parse_structured_response,
)

SUMMARY_MAX_CHARS = int(os.getenv("SUMMARY_MAX_CHARS", "500"))
# Subprocess timeout (seconds); large batches may need more. 0 = no timeout.
CURSOR_TIMEOUT = int(os.getenv("TOCIFY_CURSOR_TIMEOUT", "600"))
CURSOR_RETRIES = max(1, int(os.getenv("TOCIFY_CURSOR_RETRIES", "2")))

# Must match SCHEMA in _shared (Cursor has no structured-output API)
CURSOR_PROMPT_SUFFIX = """

Return **only** a single JSON object, no markdown code fences, no commentary. Escape any double quotes inside string values with backslash (\\"). Schema:
{"week_of": "<ISO date>", "notes": "<string>", "ranked": [{"id": "<string>", "title": "<string>", "link": "<string>", "source": "<string>", "published_utc": "<string|null>", "score": <0-1>, "why": "<max 320 chars>", "tags": ["<1-8 tags, each <=40 chars>"]}]}
"""


def is_available() -> bool:
    """Return True if CURSOR_API_KEY is set (required for Cursor backend)."""
    return bool(os.environ.get("CURSOR_API_KEY", "").strip())


def call_cursor_triage(interests: dict, items: list[dict], prompt_path: str | None = None) -> dict:
    """Triage items. If prompt_path is None, uses TOCIFY_PROMPT_PATH env or 'prompt.txt'."""
    prompt, _ = build_triage_prompt(
        interests, items, summary_max_chars=SUMMARY_MAX_CHARS, prompt_path=prompt_path
    )
    prompt = prompt + CURSOR_PROMPT_SUFFIX
    args = ["agent", "-p", "--output-format", "text", "--trust", prompt]
    last = None
    timeout = CURSOR_TIMEOUT if CURSOR_TIMEOUT > 0 else None
    for attempt in range(CURSOR_RETRIES):
        try:
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                env=os.environ,
                timeout=timeout,
            )
            if result.returncode != 0:
                raise RuntimeError(
                    f"cursor CLI exit {result.returncode}: {result.stderr or result.stdout or 'no output'}"
                )
            response_text = (result.stdout or "").strip()
            extracted = extract_first_json_object(response_text)
            return parse_structured_response(extracted)
        except (ValueError, json.JSONDecodeError, RuntimeError, subprocess.TimeoutExpired) as e:
            last = e
            if attempt == 0:
                time.sleep(3)
    raise last
