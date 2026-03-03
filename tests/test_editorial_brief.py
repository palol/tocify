"""Tests for editorial weekly brief output (default): one sentence triage block, no triage_backend/triage_model in frontmatter, no score line in entries, sanitized why."""

import unittest
from tocify.runner.brief_writer import (
    editorial_triage_sentence,
    render_brief_md,
    render_brief_entry_blocks,
    merge_brief_frontmatter,
    sanitize_why_editorial,
)


class EditorialBriefTests(unittest.TestCase):
    def test_editorial_triage_sentence_with_pool(self) -> None:
        self.assertEqual(
            editorial_triage_sentence(5, 10),
            "This week we selected 5 items from a larger pool of 10 candidates.",
        )

    def test_editorial_triage_sentence_without_pool(self) -> None:
        self.assertEqual(
            editorial_triage_sentence(3, None),
            "This week we selected 3 items from a larger pool of candidates.",
        )

    def test_render_brief_md_editorial_omits_triage_keys_from_frontmatter(self) -> None:
        result = {
            "week_of": "2026-02-16",
            "notes": "",
            "ranked": [{"id": "1", "title": "T", "link": "https://x.com", "source": "S", "score": 0.9, "why": "Relevant.", "tags": []}],
            "triage_backend": "openai",
            "triage_model": "gpt-4o",
        }
        items_by_id = {"1": {}}
        kept = [result["ranked"][0]]
        md = render_brief_md(
            result, items_by_id, kept, "bci", min_score_read=0.65, editorial_triage=True
        )
        self.assertIn("This week we selected 1 item from a larger pool of 1 candidate.", md)
        self.assertNotIn("**Included:**", md)
        self.assertNotIn("**Scored:**", md)
        self.assertNotIn("triage_backend", md)
        self.assertNotIn("triage_model", md)
        self.assertIn("included", md)  # kept for merge
        self.assertIn("scored", md)

    def test_render_brief_md_legacy_includes_triage_block_and_frontmatter(self) -> None:
        result = {
            "week_of": "2026-02-16",
            "notes": "",
            "ranked": [{"id": "1", "title": "T", "link": "https://x.com", "source": "S", "score": 0.9, "why": "Relevant.", "tags": []}],
            "triage_backend": "openai",
            "triage_model": "gpt-4o",
        }
        items_by_id = {"1": {}}
        kept = [result["ranked"][0]]
        md = render_brief_md(
            result, items_by_id, kept, "bci", min_score_read=0.65, editorial_triage=False
        )
        self.assertIn("**Included:** 1 (score ≥ 0.65)", md)
        self.assertIn("**Scored:** 1 total items", md)
        self.assertIn("triage_backend", md)
        self.assertIn("openai", md)
        self.assertIn("triage_model", md)
        self.assertIn("gpt-4o", md)

    def test_render_brief_entry_blocks_editorial_omits_score_line_and_sanitizes_why(self) -> None:
        kept = [
            {
                "id": "1",
                "title": "Paper",
                "link": "https://example.com/1",
                "source": "Journal",
                "score": 0.85,
                "why": "Tier-2; down-weighted for title. Relevant for BCI.",
                "tags": ["neuro"],
            }
        ]
        items_by_id = {"1": {}}
        md = render_brief_entry_blocks(kept, items_by_id, editorial_triage=True)
        self.assertNotIn("Score: **", md)
        self.assertNotIn("Tier-2", md)
        self.assertNotIn("down-weighted", md)
        self.assertIn("Relevant for BCI", md)

    def test_render_brief_entry_blocks_legacy_includes_score(self) -> None:
        kept = [{"id": "1", "title": "T", "link": "https://x.com", "source": "S", "score": 0.9, "why": "Relevant.", "tags": []}]
        items_by_id = {"1": {}}
        md = render_brief_entry_blocks(kept, items_by_id, editorial_triage=False)
        self.assertIn("Score: **0.90**", md)

    def test_sanitize_why_editorial_strips_internal_phrases(self) -> None:
        self.assertEqual(sanitize_why_editorial("Tier-2; down-weighted. Good for BCI."), "Good for BCI.")
        self.assertEqual(sanitize_why_editorial(""), "")
        self.assertEqual(sanitize_why_editorial("Relevant for methods."), "Relevant for methods.")
        # Leading punctuation left after strip is removed
        self.assertEqual(sanitize_why_editorial("Tier-2. Relevant."), "Relevant.")

    def test_merge_brief_frontmatter_editorial_strips_triage_keys(self) -> None:
        existing = {"date": "2026-02-16", "included": 2, "scored": 10, "triage_backend": "openai", "triage_model": "gpt-4o"}
        merged = merge_brief_frontmatter(existing, [], 5, 12, editorial_triage=True)
        self.assertEqual(merged["included"], 5)
        self.assertEqual(merged["scored"], 12)
        self.assertNotIn("triage_backend", merged)
        self.assertNotIn("triage_model", merged)


if __name__ == "__main__":
    unittest.main()
