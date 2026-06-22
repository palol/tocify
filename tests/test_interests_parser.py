"""Regression tests for interests markdown parsing in tocify.digest."""

import unittest

from tocify.digest import INTERESTS_MAX_CHARS, parse_interests_md


class InterestsParserTests(unittest.TestCase):
    def test_parse_keywords_and_narrative_basic(self) -> None:
        md = "## Keywords\n- EEG\n- LFP\n\n## Narrative\nNeural dynamics focus.\n"

        parsed = parse_interests_md(md)

        self.assertEqual(parsed["keywords"], ["EEG", "LFP"])
        self.assertEqual(parsed["narrative"], "Neural dynamics focus.")
        self.assertEqual(parsed["companies"], [])

    def test_parse_with_h2_h3_headings(self) -> None:
        md = (
            "## Keywords\n- EEG\n\n"
            "### Narrative\nSignal methods.\n\n"
            "### Companies\n- OpenAI\n"
        )

        parsed = parse_interests_md(md)

        self.assertEqual(parsed["keywords"], ["EEG"])
        self.assertEqual(parsed["narrative"], "Signal methods.")
        self.assertEqual(parsed["companies"], ["OpenAI"])

    def test_parse_stops_at_next_heading(self) -> None:
        md = (
            "## Narrative\n"
            "Line one.\n"
            "Line two.\n\n"
            "## Companies\n"
            "- Acme\n"
        )

        parsed = parse_interests_md(md)

        self.assertEqual(parsed["narrative"], "Line one.\nLine two.")

    def test_parse_companies_optional(self) -> None:
        md = "## Keywords\n- EEG\n\n## Narrative\nText.\n"

        parsed = parse_interests_md(md)

        self.assertEqual(parsed["companies"], [])

    def test_parse_handles_bullet_and_plain_lines(self) -> None:
        md = (
            "## Keywords\n"
            "- EEG\n"
            "* MEG\n"
            "+ LFP\n"
            "plain keyword\n\n"
            "## Narrative\nx\n"
        )

        parsed = parse_interests_md(md)

        self.assertEqual(parsed["keywords"], ["EEG", "MEG", "LFP", "plain keyword"])

    def test_parse_empty_when_heading_missing(self) -> None:
        md = "## Other\ncontent\n"

        parsed = parse_interests_md(md)

        self.assertEqual(parsed["keywords"], [])
        self.assertEqual(parsed["narrative"], "")
        self.assertEqual(parsed["companies"], [])

    def test_narrative_respects_interest_max_chars(self) -> None:
        md = f"## Narrative\n{'x' * (INTERESTS_MAX_CHARS + 10)}\n"

        parsed = parse_interests_md(md)

        self.assertEqual(len(parsed["narrative"]), INTERESTS_MAX_CHARS + 1)
        self.assertTrue(parsed["narrative"].endswith("…"))

    def test_parse_handles_crlf_and_case_insensitive_headings(self) -> None:
        md = "## KEYWORDS\r\n- EEG\r\n\r\n## NARRATIVE\r\nLine.\r\n"

        parsed = parse_interests_md(md)

        self.assertEqual(parsed["keywords"], ["EEG"])
        self.assertEqual(parsed["narrative"], "Line.")


if __name__ == "__main__":
    unittest.main()
