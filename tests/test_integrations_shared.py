"""Tests for tocify.integrations._shared (extract_first_json_object, parse_structured_response)."""

import tempfile
import unittest
from pathlib import Path

from tocify.integrations._shared import (
    REQUIRED_PROMPT_PLACEHOLDERS,
    SCHEMA,
    extract_first_json_object,
    load_prompt_template,
    parse_structured_response,
)


class ExtractFirstJsonObjectTests(unittest.TestCase):
    def test_single_object_no_whitespace(self) -> None:
        text = '{"a": 1}'
        self.assertEqual(extract_first_json_object(text), '{"a": 1}')

    def test_leading_trailing_text(self) -> None:
        text = 'prefix {"week_of": "2025-01-01", "notes": "", "ranked": []} suffix'
        self.assertEqual(
            extract_first_json_object(text),
            '{"week_of": "2025-01-01", "notes": "", "ranked": []}',
        )

    def test_two_objects_returns_first_only(self) -> None:
        text = '{"first": true} {"second": true}'
        self.assertEqual(extract_first_json_object(text), '{"first": true}')

    def test_braces_inside_string_values_ignored(self) -> None:
        text = r'{"why": "Example: { optional }"}'
        self.assertEqual(
            extract_first_json_object(text),
            r'{"why": "Example: { optional }"}',
        )

    def test_no_object_raises(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            extract_first_json_object("no json here")
        self.assertIn("No JSON object found", str(ctx.exception))

    def test_truncated_object_raises(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            extract_first_json_object('{"a": 1')
        self.assertIn("truncated or unclosed", str(ctx.exception))


class ParseStructuredResponseTests(unittest.TestCase):
    def test_valid_with_ranked_returns_data(self) -> None:
        data = parse_structured_response(
            '{"week_of": "2025-01-01", "notes": "", "ranked": [{"id": "x", "title": "t", "link": "l", "source": "s", "published_utc": null, "score": 0.5, "why": "w", "tags": []}]}'
        )
        self.assertIn("ranked", data)
        self.assertEqual(len(data["ranked"]), 1)

    def test_missing_ranked_raises(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            parse_structured_response('{"week_of": "2025-01-01", "notes": ""}')
        self.assertIn("ranked", str(ctx.exception))

    def test_invalid_json_raises_with_snippet_and_hint(self) -> None:
        invalid = '{"a": "broken " quote"}'
        with self.assertRaises(ValueError) as ctx:
            parse_structured_response(invalid)
        msg = str(ctx.exception)
        self.assertIn("Check for unescaped double quotes", msg)
        self.assertIn("truncation", msg)


class PromptTemplateTests(unittest.TestCase):
    def test_load_prompt_template_raises_on_missing_placeholders(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            prompt_path = Path(td) / "prompt.txt"
            prompt_path.write_text("Missing placeholders {{ITEMS}} only", encoding="utf-8")
            with self.assertRaises(RuntimeError) as ctx:
                load_prompt_template(str(prompt_path))
        msg = str(ctx.exception)
        self.assertIn("Prompt template missing required placeholders", msg)
        for token in REQUIRED_PROMPT_PLACEHOLDERS:
            if token != "{{ITEMS}}":
                self.assertIn(token, msg)

    def test_load_prompt_template_accepts_all_placeholders(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            prompt_path = Path(td) / "prompt.txt"
            prompt_path.write_text(
                "\n".join(REQUIRED_PROMPT_PLACEHOLDERS),
                encoding="utf-8",
            )
            template = load_prompt_template(str(prompt_path))
        self.assertEqual(template, "\n".join(REQUIRED_PROMPT_PLACEHOLDERS))


class SchemaContractTests(unittest.TestCase):
    def test_schema_enforces_score_why_and_tag_limits(self) -> None:
        ranked_props = SCHEMA["properties"]["ranked"]["items"]["properties"]
        self.assertEqual(ranked_props["score"]["minimum"], 0)
        self.assertEqual(ranked_props["score"]["maximum"], 1)
        self.assertEqual(ranked_props["why"]["maxLength"], 320)
        self.assertEqual(ranked_props["tags"]["minItems"], 1)
        self.assertEqual(ranked_props["tags"]["maxItems"], 8)
        self.assertEqual(ranked_props["tags"]["items"]["maxLength"], 40)
