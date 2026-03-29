"""Unit tests for tocify.semanticscholar: query normalization and date-window filtering."""

import sys
import types
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

_root = Path(__file__).resolve().parent.parent
_root_str = str(_root)
if _root_str not in sys.path:
    sys.path.insert(0, _root_str)

tocify_mod = sys.modules.get("tocify")
if tocify_mod is None or not hasattr(tocify_mod, "__path__"):
    pkg = types.ModuleType("tocify")
    pkg.__path__ = [str(_root / "tocify")]
    sys.modules["tocify"] = pkg

from tocify.semanticscholar import fetch_semantic_scholar_items
from tocify.utils import sha1


class _Response:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class SemanticScholarTests(unittest.TestCase):
    def test_returns_normalized_items_and_normalizes_query(self) -> None:
        payload = {
            "total": 1,
            "offset": 0,
            "next": 1,
            "data": [
                {
                    "title": "Brain Computer Interfaces in Practice",
                    "abstract": "A detailed abstract about BCI progress.",
                    "publicationDate": "2026-01-05",
                    "year": 2026,
                    "url": "https://www.semanticscholar.org/paper/example",
                    "externalIds": {"DOI": "10.1234/bci.2026.1"},
                    "publicationVenue": {"name": "Neuro Journal"},
                }
            ],
        }

        with patch("tocify.semanticscholar.requests.get", return_value=_Response(payload)) as mock_get:
            items = fetch_semantic_scholar_items(
                date(2026, 1, 1),
                date(2026, 1, 7),
                query="brain-computer   interface",
            )

        self.assertEqual(len(items), 1)
        self.assertEqual(
            items[0],
            {
                "id": sha1("Semantic Scholar|Brain Computer Interfaces in Practice|https://doi.org/10.1234/bci.2026.1"),
                "source": "Neuro Journal",
                "title": "Brain Computer Interfaces in Practice",
                "link": "https://doi.org/10.1234/bci.2026.1",
                "published_utc": "2026-01-05T00:00:00+00:00",
                "summary": "A detailed abstract about BCI progress.",
            },
        )

        params = mock_get.call_args.kwargs["params"]
        self.assertEqual(params["query"], "brain computer interface")
        self.assertEqual(params["publicationDateOrYear"], "2026-01-01:2026-01-07")

    def test_filters_items_outside_date_window_and_uses_year_fallback(self) -> None:
        payload = {
            "total": 3,
            "offset": 0,
            "next": 3,
            "data": [
                {
                    "title": "In-range paper",
                    "abstract": "kept",
                    "publicationDate": "2026-01-03",
                    "year": 2026,
                    "url": "https://example.com/in-range",
                    "externalIds": {},
                    "venue": "Venue A",
                },
                {
                    "title": "Out-of-range paper",
                    "abstract": "dropped",
                    "publicationDate": "2026-02-01",
                    "year": 2026,
                    "url": "https://example.com/out-of-range",
                    "externalIds": {},
                    "venue": "Venue B",
                },
                {
                    "title": "Year-only paper",
                    "abstract": "kept by year fallback",
                    "publicationDate": None,
                    "year": 2026,
                    "url": "https://example.com/year-only",
                    "externalIds": {},
                    "venue": "Venue C",
                },
            ],
        }

        with patch("tocify.semanticscholar.requests.get", return_value=_Response(payload)):
            items = fetch_semantic_scholar_items(
                date(2026, 1, 1),
                date(2026, 1, 7),
                query="bci",
            )

        self.assertEqual([item["title"] for item in items], ["In-range paper", "Year-only paper"])
        self.assertEqual(items[1]["published_utc"], "2026-01-01T00:00:00+00:00")


if __name__ == "__main__":
    unittest.main()
