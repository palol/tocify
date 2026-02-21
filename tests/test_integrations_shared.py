"""Tests for tocify.integrations._shared (extract_first_json_object, parse_structured_response)."""

import json
import unittest

from tocify.integrations._shared import (
    extract_first_json_object,
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
