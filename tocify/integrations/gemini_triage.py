"""Gemini triage backend. Needs GEMINI_API_KEY. Model via GEMINI_MODEL env."""

import json
import os
import time
from typing import Any

from tocify.integrations._shared import (
    SCHEMA,
    build_triage_prompt,
    extract_first_json_object,
    parse_structured_response,
)

SUMMARY_MAX_CHARS = int(os.getenv("SUMMARY_MAX_CHARS", "500"))


def is_available() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY", "").strip())


def make_gemini_client() -> Any:
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("GEMINI_API_KEY missing/invalid.")
    try:
        from google import genai
    except ImportError as e:
        raise RuntimeError("google-genai is not installed. Add it to requirements and reinstall.") from e
    return genai.Client(api_key=key)


def _generate_response_text(client: Any, model: str, prompt: str) -> str:
    # SDK versions differ in schema field naming; try both known variants.
    cfg_candidates = (
        {"response_mime_type": "application/json", "response_schema": SCHEMA},
        {"response_mime_type": "application/json", "response_json_schema": SCHEMA},
    )
    last = None
    for config in cfg_candidates:
        try:
            resp = client.models.generate_content(model=model, contents=prompt, config=config)
            text = (getattr(resp, "text", None) or "").strip()
            if not text:
                raise ValueError("Empty response text from Gemini")
            return text
        except TypeError as e:
            last = e
    if last is not None:
        raise RuntimeError("Gemini client rejected schema config; check google-genai version.") from last
    raise RuntimeError("Gemini returned no response.")


def _parse_response_text(response_text: str) -> dict:
    try:
        return parse_structured_response(response_text)
    except (json.JSONDecodeError, ValueError):
        extracted = extract_first_json_object(response_text)
        return parse_structured_response(extracted)


def call_gemini_triage(client: Any, interests: dict, items: list[dict]) -> dict:
    model = os.getenv("GEMINI_MODEL", "").strip() or "gemini-2.0-flash"
    prompt, _ = build_triage_prompt(interests, items, summary_max_chars=SUMMARY_MAX_CHARS)

    last = None
    for attempt in range(6):
        try:
            response_text = _generate_response_text(client, model, prompt)
            return _parse_response_text(response_text)
        except Exception as e:
            last = e
            if attempt < 5:
                time.sleep(min(60, 2 ** attempt))
    raise last
