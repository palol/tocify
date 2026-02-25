import unittest
from datetime import date
from unittest.mock import patch

from tocify.newsrooms import _LinkExtractor, _fetch_newsroom_url
from tocify.utils import sha1


class _Response:
    def __init__(self, text: str):
        self.text = text

    def raise_for_status(self) -> None:
        return None


class NewsroomLinkExtractorTests(unittest.TestCase):
    def test_handle_data_only_captures_text_within_anchor(self) -> None:
        parser = _LinkExtractor("https://example.com/newsroom", "example.com")
        parser.feed(
            """
            <a href="/news/2026/01/15/story-one">Story One</a>
            <div>Unrelated body text between links.</div>
            <a href="/news/2026/01/16/story-two">Story Two</a>
            """
        )
        self.assertEqual(
            parser.links,
            [
                ("https://example.com/news/2026/01/15/story-one", "Story One"),
                ("https://example.com/news/2026/01/16/story-two", "Story Two"),
            ],
        )

    def test_fetch_newsroom_url_uses_clean_anchor_text_for_title_and_id(self) -> None:
        html = """
        <main>
          <a href="/news/2026/01/15/story-one">Story One</a>
          <p>Unrelated body text between links.</p>
          <a href="/news/2026/01/16/story-two">Story Two</a>
        </main>
        """
        with patch("tocify.newsrooms.requests.get", return_value=_Response(html)):
            items = _fetch_newsroom_url(
                "https://example.com/newsroom",
                start_date=date(2026, 1, 1),
                end_date=date(2026, 12, 31),
                timeout=5,
            )

        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["title"], "Story One")
        self.assertEqual(
            items[0]["id"],
            sha1("example.com|Story One|https://example.com/news/2026/01/15/story-one"),
        )
        self.assertEqual(items[1]["title"], "Story Two")
        self.assertEqual(
            items[1]["id"],
            sha1("example.com|Story Two|https://example.com/news/2026/01/16/story-two"),
        )


if __name__ == "__main__":
    unittest.main()
