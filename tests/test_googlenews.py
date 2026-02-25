"""Unit tests for tocify.googlenews: fetch_google_news_items schema and date filtering."""

import sys
import unittest
from pathlib import Path

# Ensure project root is on path and tocify is the package (unittest discover -s tests can leave a wrong tocify in sys.modules)
_root = Path(__file__).resolve().parent.parent
_root_str = str(_root)
if _root_str not in sys.path:
    sys.path.insert(0, _root_str)
# Force re-import of tocify from project root so tocify.googlenews exists
for key in list(sys.modules):
    if key == "tocify" or key.startswith("tocify."):
        del sys.modules[key]

from datetime import date
from types import SimpleNamespace
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


class _EntryDict(dict):
    """Dict that also supports getattr so feedparser entry fields work (e.g. published_parsed)."""

    def __getattr__(self, name: str):
        return self.get(name)


def _parsed_feed_for(content: bytes) -> SimpleNamespace:
    """Return a feedparser-like feed for our test RSS bytes (avoids feedparser version/env variance)."""
    # published_parsed: (year, month, day, hour, minute, sec, wday, yday, isdst) per feedparser
    if content == RSS_IN_RANGE:
        entry = _EntryDict({
            "title": "Neural oscillations study",
            "link": "https://example.com/article1",
            "description": "Summary of the article.",
            "published_parsed": (2025, 1, 20, 12, 0, 0, 0, 0, 0),
        })
        return SimpleNamespace(entries=[entry])
    if content == RSS_OUT_OF_RANGE:
        entry = _EntryDict({
            "title": "Old article",
            "link": "https://example.com/old",
            "description": "Old summary.",
            "published_parsed": (2018, 1, 1, 12, 0, 0, 0, 0, 0),
        })
        return SimpleNamespace(entries=[entry])
    return SimpleNamespace(entries=[])


class TestFetchGoogleNewsItems(unittest.TestCase):
    def test_returns_same_schema_as_rss(self) -> None:
        """Every item has id, source, title, link, published_utc, summary."""
        def parse_side_effect(content, *args, **kwargs):
            return _parsed_feed_for(content)

        with patch("tocify.googlenews.requests.get") as mock_get, patch(
            "tocify.googlenews.feedparser.parse", side_effect=parse_side_effect
        ):
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

        def get_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            if call_count == 1:
                mock_resp.content = RSS_IN_RANGE  # 2025-01-20
            else:
                mock_resp.content = RSS_OUT_OF_RANGE  # 2018-01-01
            return mock_resp

        def parse_side_effect(content, *args, **kwargs):
            return _parsed_feed_for(content)

        with patch("tocify.googlenews.requests.get", side_effect=get_side_effect), patch(
            "tocify.googlenews.feedparser.parse", side_effect=parse_side_effect
        ):
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
        def parse_side_effect(content, *args, **kwargs):
            return _parsed_feed_for(content)

        with patch("tocify.googlenews.requests.get") as mock_get, patch(
            "tocify.googlenews.feedparser.parse", side_effect=parse_side_effect
        ):
            mock_resp = MagicMock()
            mock_resp.content = RSS_IN_RANGE
            mock_resp.raise_for_status = MagicMock()
            mock_get.return_value = mock_resp

            start = date(2025, 1, 1)
            end = date(2025, 1, 31)
            items = fetch_google_news_items(start, end, ["EEG", "EEG"])
        ids = [it["id"] for it in items]
        self.assertEqual(len(ids), len(set(ids)))
