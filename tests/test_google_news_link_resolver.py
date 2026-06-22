import unittest
from unittest.mock import MagicMock, patch

import requests

from tocify.google_news_link_resolver import (
    is_google_news_url,
    resolve_google_news_links_in_items,
    resolve_google_news_url,
)


class GoogleNewsLinkResolverTests(unittest.TestCase):
    def test_is_google_news_url(self) -> None:
        self.assertTrue(is_google_news_url("https://news.google.com/rss/articles/ABC123"))
        self.assertFalse(is_google_news_url("https://example.com/article"))

    def test_resolve_google_news_url_prefers_query_destination(self) -> None:
        wrapped = (
            "https://news.google.com/rss/articles/CBMiQ2h0dHBzOi8vbmV3cy5nb29nbGUuY29tL2FydGljbGU"
            "?url=https%3A%2F%2Fexample.com%2Farticle-1&hl=en-US&gl=US&ceid=US:en"
        )
        resolved = resolve_google_news_url(wrapped)
        self.assertEqual(resolved, "https://example.com/article-1")

    def test_resolve_google_news_url_uses_redirect_when_needed(self) -> None:
        wrapped = "https://news.google.com/rss/articles/CBMiX2h0dHBzOi8vbmV3cy5nb29nbGUuY29tL3dyYXA"
        with patch("tocify.google_news_link_resolver.requests.Session") as session_cls:
            session = MagicMock()
            response = MagicMock()
            response.url = "https://publisher.example.com/story"
            session.get.return_value = response
            session_cls.return_value = session

            resolved = resolve_google_news_url(wrapped, timeout=7, max_redirects=4)

        self.assertEqual(resolved, "https://publisher.example.com/story")
        session.get.assert_called_once()
        self.assertEqual(session.max_redirects, 4)
        response.close.assert_called_once()
        session.close.assert_called_once()

    def test_resolve_google_news_url_keeps_original_on_failure(self) -> None:
        wrapped = "https://news.google.com/rss/articles/CBMiX2h0dHBzOi8vbmV3cy5nb29nbGUuY29tL2ZhaWw"
        with patch("tocify.google_news_link_resolver.requests.Session") as session_cls:
            session = MagicMock()
            session.get.side_effect = requests.RequestException("network down")
            session_cls.return_value = session
            resolved = resolve_google_news_url(wrapped, timeout=3, max_redirects=2)
        self.assertEqual(resolved, wrapped)

    def test_resolve_google_news_links_in_items_uses_cache_for_duplicates(self) -> None:
        wrapped = (
            "https://news.google.com/rss/articles/CBMiQ2h0dHBzOi8vbmV3cy5nb29nbGUuY29tL2FydGljbGU"
            "?url=https%3A%2F%2Fexample.com%2Fcached&hl=en-US&gl=US&ceid=US:en"
        )
        items = [
            {"id": "1", "link": wrapped, "title": "A"},
            {"id": "2", "link": wrapped, "title": "B"},
            {"id": "3", "link": "https://example.com/other", "title": "C"},
        ]
        with patch(
            "tocify.google_news_link_resolver._resolve_google_news_url_with_method",
            return_value=("https://example.com/cached", "query"),
        ) as resolve_fn:
            resolved, stats = resolve_google_news_links_in_items(items, workers=4)

        self.assertEqual(resolve_fn.call_count, 1)
        self.assertEqual(resolved[0]["link"], "https://example.com/cached")
        self.assertEqual(resolved[1]["link"], "https://example.com/cached")
        self.assertEqual(resolved[2]["link"], "https://example.com/other")
        self.assertEqual(stats["attempted"], 1)
        self.assertEqual(stats["resolved"], 1)
        self.assertEqual(stats["failed"], 0)
        self.assertEqual(stats["skipped_non_google"], 1)


if __name__ == "__main__":
    unittest.main()
