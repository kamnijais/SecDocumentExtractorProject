"""Unit tests for the SEC client and filing service."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from app.core.exceptions import SecApiResponseError, TickerResolutionError
from app.services.filing_service import FilingService
from app.services.sec_client import SecEdgarClient


class SecEdgarClientTests(unittest.TestCase):
    """Verify low-level SEC client behavior without hitting the network."""

    def setUp(self) -> None:
        self.client = SecEdgarClient(
            submissions_base_url="https://data.sec.gov",
            archive_base_url="https://www.sec.gov/Archives/edgar/data",
            ticker_mapping_url="https://www.sec.gov/files/company_tickers.json",
            user_agent="Test User test@example.com",
            timeout_seconds=1,
        )
        self.addCleanup(self.client.close)

    def test_resolve_cik_uses_cached_mapping_after_first_lookup(self) -> None:
        mapping = {"0": {"ticker": "AAPL", "cik_str": 320193}}

        with patch.object(self.client, "_get_json", return_value=mapping) as mock_get_json:
            first = self.client.resolve_cik("AAPL")
            second = self.client.resolve_cik("aapl")

        self.assertEqual(first, "0000320193")
        self.assertEqual(second, "0000320193")
        # the real assertion here: second lookup shouldn't hit _get_json again
        self.assertEqual(mock_get_json.call_count, 1)

    def test_resolve_cik_raises_for_unknown_ticker(self) -> None:
        with patch.object(self.client, "_get_json", return_value={}):
            with self.assertRaises(TickerResolutionError):
                self.client.resolve_cik("UNKNOWN")

    def test_build_filing_url_normalizes_accession_number(self) -> None:
        filing_url = self.client.build_filing_url(
            cik="0000320193",
            accession_number="0000320193-25-000079",
            primary_document="aapl-20250927.htm",
        )

        self.assertEqual(
            filing_url,
            "https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/aapl-20250927.htm",
        )


class FilingServiceTests(unittest.TestCase):
    """Verify higher-level filing lookup behavior."""

    def setUp(self) -> None:
        self.client = SecEdgarClient(
            submissions_base_url="https://data.sec.gov",
            archive_base_url="https://www.sec.gov/Archives/edgar/data",
            ticker_mapping_url="https://www.sec.gov/files/company_tickers.json",
            user_agent="Test User test@example.com",
            timeout_seconds=1,
        )
        self.service = FilingService(self.client)
        self.addCleanup(self.client.close)

    def test_fetch_latest_10k_url_returns_archive_url(self) -> None:
        # form list is intentionally not all 10-K - we want to confirm the
        # service skips the 8-K and picks the right accession number.
        submissions = {
            "filings": {
                "recent": {
                    "form": ["8-K", "10-K"],
                    "accessionNumber": ["0000000000-00-000001", "0000320193-25-000079"],
                    "primaryDocument": ["other.htm", "aapl-20250927.htm"],
                }
            }
        }

        with patch.object(self.client, "resolve_cik", return_value="0000320193"), patch.object(
            self.client,
            "get_company_submissions",
            return_value=submissions,
        ):
            filing_url = self.service.fetch_latest_10k_url("AAPL")

        self.assertEqual(
            filing_url,
            "https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/aapl-20250927.htm",
        )

    def test_fetch_latest_10k_url_raises_for_malformed_payload(self) -> None:

        with patch.object(self.client, "resolve_cik", return_value="0000320193"), patch.object(
            self.client,
            "get_company_submissions",
            return_value={"filings": {}},
        ):
            with self.assertRaises(SecApiResponseError):
                self.service.fetch_latest_10k_url("AAPL")


if __name__ == "__main__":
    unittest.main()

