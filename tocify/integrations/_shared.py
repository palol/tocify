"""Shared prompt template and JSON schema for all triage backends.

OpenAI, Claude, and Gemini all use JSON Schema for structured output; SCHEMA is the
single source of truth. Cursor has no schema API and uses prompt-only + parse.
"""

import json
import os

REQUIRED_PROMPT_PLACEHOLDERS = (
    "{{ITEMS}}",
    "{{KEYWORDS}}",
    "{{NARRATIVE}}",
    "{{COMPANIES}}",
)

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "week_of": {"type": "string"},
        "notes": {"type": "string"},
        "ranked": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "id": {"type": "string", "maxLength": 128},
                    "title": {"type": "string", "maxLength": 400},
                    "link": {"type": "string", "maxLength": 2048},
                    "source": {"type": "string", "maxLength": 200},
                    "published_utc": {"type": ["string", "null"]},
                    "score": {"type": "number", "minimum": 0, "maximum": 1},
                    "why": {"type": "string", "maxLength": 320},
                    "tags": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 8,
                        "items": {"type": "string", "maxLength": 40},
                    },
                },
                "required": ["id", "title", "link", "source", "published_utc", "score", "why", "tags"],
            },
        },
    },
    "required": ["week_of", "notes", "ranked"],
}


def load_prompt_template(path: str | None = None) -> str:
    """Load triage prompt template. Uses TOCIFY_PROMPT_PATH env if set, else path or 'prompt.txt'."""
    if path is None:
        path = os.getenv("TOCIFY_PROMPT_PATH", "prompt.txt")
    if not os.path.exists(path):
        raise RuntimeError(f"Prompt file not found: {path}")
    with open(path, encoding="utf-8") as f:
        template = f.read()
    missing = [token for token in REQUIRED_PROMPT_PLACEHOLDERS if token not in template]
    if missing:
        missing_str = ", ".join(missing)
        raise RuntimeError(f"Prompt template missing required placeholders ({missing_str}): {path}")
    return template


def build_triage_prompt(
    interests: dict, items: list[dict], *, summary_max_chars: int = 500, prompt_path: str | None = None
) -> tuple[str, list[dict]]:
    """Build the triage prompt and lean items. Returns (prompt_string, lean_items)."""
    lean_items = [
        {
            "id": it["id"],
            "source": it["source"],
            "title": it["title"],
            "link": it["link"],
            "published_utc": it.get("published_utc"),
            "summary": (it.get("summary") or "")[:summary_max_chars],
        }
        for it in items
    ]
    template = load_prompt_template(prompt_path)
    companies = interests.get("companies", [])
    prompt = (
        template.replace("{{KEYWORDS}}", json.dumps(interests["keywords"], ensure_ascii=False))
        .replace("{{NARRATIVE}}", interests["narrative"])
        .replace("{{COMPANIES}}", json.dumps(companies, ensure_ascii=False))
        .replace("{{ITEMS}}", json.dumps(lean_items, ensure_ascii=False))
    )
    return (prompt, lean_items)


def extract_first_json_object(response_text: str) -> str:
    """Extract the first top-level {...} from text, respecting string boundaries."""
    start = response_text.find("{")
    if start < 0:
        raise ValueError("No JSON object found in response")
    depth = 0
    i = start
    in_string = False
    escape_next = False
    n = len(response_text)
    while i < n:
        c = response_text[i]
        if escape_next:
            escape_next = False
            i += 1
            continue
        if in_string:
            if c == "\\":
                escape_next = True
            elif c == '"':
                in_string = False
            i += 1
            continue
        if c == '"':
            in_string = True
            i += 1
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return response_text[start : i + 1]
        i += 1
    raise ValueError("JSON object in response is truncated or unclosed (brace count did not reach 0)")


def parse_structured_response(response_text: str) -> dict:
    """Parse JSON from a structured-output response; validate 'ranked' exists."""
    try:
        data = json.loads(response_text)
    except json.JSONDecodeError as e:
        pos = getattr(e, "pos", None)
        snippet = ""
        if pos is not None and 0 <= pos <= len(response_text):
            lo = max(0, pos - 40)
            hi = min(len(response_text), pos + 40)
            snippet = response_text[lo:hi]
            if lo > 0:
                snippet = "..." + snippet
            if hi < len(response_text):
                snippet = snippet + "..."
            snippet = repr(snippet)
        msg = f"{e}. {snippet}" if snippet else str(e)
        msg += " Check for unescaped double quotes in string values, truncation, or multiple JSON objects."
        raise ValueError(msg) from e
    if not isinstance(data, dict) or "ranked" not in data:
        raise ValueError("Response missing required 'ranked' field")
    return data
