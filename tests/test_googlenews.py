"""Unit tests for tocify.googlenews: fetch_google_news_items schema and date filtering."""

import unittest
from datetime import date, datetime, timezone
from unittest.mock import patch, MagicMock

from tocify.googlenews import fetch_google_news_items

# Minimal RSS 2.0 with one item (in-range pubDate) and one item (out-of-range)
RSS_IN_RANGE = b"""<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0">
  <channel>
    <title>Google News</title>
    <item>
      <title>Neural oscillations study</title>
      <link>https://example.com/article1</link>
      <description>Summary of the article.</description>
      <pubDate>Mon, 20 Jan 2025 12:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""

RSS_OUT_OF_RANGE = b"""<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0">
  <channel>
    <title>Google News</title>
    <item>
      <title>Old article</title>
      <link>https://example.com/old</link>
      <description>Old summary.</description>
      <pubDate>Mon, 01 Jan 2018 12:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""


class TestFetchGoogleNewsItems(unittest.TestCase):
    def test_returns_same_schema_as_rss(self) -> None:
        """Every item has id, source, title, link, published_utc, summary."""
        with patch("tocify.googlenews.requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.content = RSS_IN_RANGE
            mock_resp.raise_for_status = MagicMock()
            mock_get.return_value = mock_resp

            start = date(2025, 1, 1)
            end = date(2025, 1, 31)
            items = fetch_google_news_items(start, end, ["EEG"])

        self.assertGreater(len(items), 0)
        for it in items:
            self.assertIn("id", it)
            self.assertIn("source", it)
            self.assertIn("title", it)
            self.assertIn("link", it)
            self.assertIn("published_utc", it)
            self.assertIn("summary", it)
            self.assertIsInstance(it["id"], str)
            self.assertIsInstance(it["source"], str)
            self.assertIn("Google News", it["source"])

    def test_filters_items_outside_date_window(self) -> None:
        """Items with pubDate outside start_date..end_date are excluded."""
        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            if call_count == 1:
                mock_resp.content = RSS_IN_RANGE  # 2025-01-20
            else:
                mock_resp.content = RSS_OUT_OF_RANGE  # 2018-01-01
            return mock_resp

        with patch("tocify.googlenews.requests.get", side_effect=side_effect):
            start = date(2025, 1, 1)
            end = date(2025, 1, 31)
            # First request returns in-range item; second returns out-of-range (filtered out)
            items = fetch_google_news_items(start, end, ["EEG", "old"])

        self.assertEqual(len(items), 1)
        self.assertIn("Neural oscillations", items[0]["title"])

    def test_empty_queries_returns_empty_list(self) -> None:
        items = fetch_google_news_items(date(2025, 1, 1), date(2025, 1, 31), [])
        self.assertEqual(items, [])

    def test_dedupes_by_id_across_queries(self) -> None:
        with patch("tocify.googlenews.requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.content = RSS_IN_RANGE
            mock_resp.raise_for_status = MagicMock()
            mock_get.return_value = mock_resp

            start = date(2025, 1, 1)
            end = date(2025, 1, 31)
            items = fetch_google_news_items(start, end, ["EEG", "EEG"])
        ids = [it["id"] for it in items]
        self.assertEqual(len(ids), len(set(ids)))
