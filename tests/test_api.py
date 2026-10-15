"""Unit tests for the REST API layer."""

from __future__ import annotations

from pathlib import Path
import unittest
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.api.app import app
from app.api import routes
from app.core.config import DEFAULT_USER_AGENT, Settings
from app.services.report_service import GeneratedPdfReport


class ApiTests(unittest.TestCase):
    """Verify REST endpoint behavior for SEC report generation."""

    def setUp(self) -> None:
        self.client = TestClient(app)
        self.addCleanup(app.dependency_overrides.clear)

    def _settings(self, **overrides: object) -> Settings:
        data: dict[str, object] = {
            "sec_submissions_base_url": "https://data.sec.gov",
            "sec_archive_url": "https://www.sec.gov/Archives/edgar/data",
            "sec_ticker_mapping_url": "https://www.sec.gov/files/company_tickers.json",
            "sec_user_agent": "Test User test@example.com",
            "sec_timeout_seconds": 30,
            "sec_output_dir": Path("generated_reports"),
            "tickers": ("AAPL",),
            "supported_tickers": ("AAPL", "META", "GOOGL", "AMZN", "NFLX", "GS"),
            "api_host": "127.0.0.1",
            "api_port": 8000,
            "api_reload": False,
            "company_cik": None,
        }
        data.update(overrides)
        return Settings(**data)

    def test_health_endpoint_returns_status(self) -> None:
        app.dependency_overrides[routes.get_settings] = lambda: self._settings()

        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"status": "ok", "output_dir": "generated_reports"},
        )

    def test_generate_latest_10k_reports_returns_batch_results(self) -> None:
        mock_report_service = MagicMock()
        mock_report_service.generate_latest_10k_pdfs.return_value = [
            GeneratedPdfReport(
                ticker="AAPL",
                filing_url="https://example.test/aapl-10k.html",
                pdf_path=Path("generated_reports/AAPL_latest_10k.pdf"),
            ),
            GeneratedPdfReport(ticker="GS", filing_url=None, pdf_path=None, error="network error"),
        ]

        app.dependency_overrides[routes.get_settings] = lambda: self._settings()
        app.dependency_overrides[routes.get_report_service] = lambda: mock_report_service

        response = self.client.post(
            "/reports/latest-10k",
            # mixed case + whitespace + a duplicate, to make sure normalization
            # actually runs before hitting the report service
            json={"tickers": ["aapl", " gs ", "AAPL"]},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            mock_report_service.generate_latest_10k_pdfs.call_args.args[0],
            ("AAPL", "GS"),
        )
        self.assertEqual(
            response.json(),
            {
                "tickers": ["AAPL", "GS"],
                "results": [
                    {
                        "ticker": "AAPL",
                        "filing_url": "https://example.test/aapl-10k.html",
                        "pdf_path": "generated_reports/AAPL_latest_10k.pdf",
                        "error": None,
                    },
                    {
                        "ticker": "GS",
                        "filing_url": None,
                        "pdf_path": None,
                        "error": "network error",
                    },
                ],
                "summary": {
                    "requested_count": 2,
                    "success_count": 1,
                    "missing_count": 0,
                    "error_count": 1,
                },
            },
        )

    def test_generate_latest_10k_reports_rejects_default_user_agent(self) -> None:
        app.dependency_overrides[routes.get_settings] = lambda: self._settings(sec_user_agent=DEFAULT_USER_AGENT)

        response = self.client.post("/reports/latest-10k", json={"tickers": ["AAPL"]})

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json(),
            {"detail": "SEC_USER_AGENT must be configured before using the report-generation API."},
        )

    def test_generate_latest_10k_reports_rejects_batch_larger_than_supported_ticker_count(self) -> None:
        # With only 6 tickers ever able to pass the whitelist check, the
        # effective cap should be 6, not the absolute ceiling of 10 - a batch
        # of 7 unique tickers should be rejected on size alone, before the
        # whitelist check even runs (count validation happens first).
        mock_report_service = MagicMock()

        app.dependency_overrides[routes.get_settings] = lambda: self._settings()
        app.dependency_overrides[routes.get_report_service] = lambda: mock_report_service

        response = self.client.post(
            "/reports/latest-10k",
            json={"tickers": ["AAPL", "META", "GOOGL", "AMZN", "NFLX", "GS", "MSFT"]},
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(
            response.json(),
            {
                "detail": (
                    "A maximum of 6 unique ticker symbols is allowed per request "
                    "to keep SEC traffic within a small, reviewable batch size."
                )
            },
        )
        mock_report_service.generate_latest_10k_pdfs.assert_not_called()

    def test_generate_latest_10k_reports_caps_at_ten_when_allowlist_is_larger(self) -> None:
        # If the allowlist is ever configured with more than 10 tickers, the
        # absolute safety ceiling (10) should take over as the binding limit
        # instead of the (now larger) allowlist size.
        mock_report_service = MagicMock()
        large_allowlist = ("AAPL", "META", "GOOGL", "AMZN", "NFLX", "GS", "MSFT", "NVDA", "TSLA", "IBM", "ORCL", "CRM")

        app.dependency_overrides[routes.get_settings] = lambda: self._settings(supported_tickers=large_allowlist)
        app.dependency_overrides[routes.get_report_service] = lambda: mock_report_service

        response = self.client.post(
            "/reports/latest-10k",
            json={"tickers": list(large_allowlist[:11])},  # 11 unique, valid tickers
        )

        self.assertEqual(response.status_code, 422)
        self.assertIn("A maximum of 10 unique ticker symbols", response.json()["detail"])
        mock_report_service.generate_latest_10k_pdfs.assert_not_called()

    def test_generate_latest_10k_reports_rejects_unsupported_ticker(self) -> None:
        mock_report_service = MagicMock()

        app.dependency_overrides[routes.get_settings] = lambda: self._settings()
        app.dependency_overrides[routes.get_report_service] = lambda: mock_report_service

        # MSFT is a real, valid ticker - it's just not one of the six companies
        # this API currently supports. That distinction is the whole point of
        # this test (as opposed to a malformed/empty ticker).
        response = self.client.post("/reports/latest-10k", json={"tickers": ["AAPL", "MSFT"]})

        self.assertEqual(response.status_code, 422)
        self.assertEqual(
            response.json(),
            {
                "detail": (
                    "Unsupported ticker(s): MSFT. This API currently only supports: "
                    "AAPL (Apple), META (Meta), GOOGL (Alphabet), AMZN (Amazon), "
                    "NFLX (Netflix), GS (Goldman Sachs)."
                )
            },
        )
        mock_report_service.generate_latest_10k_pdfs.assert_not_called()

    def test_generate_latest_10k_reports_accepts_all_six_supported_tickers(self) -> None:
        mock_report_service = MagicMock()
        mock_report_service.generate_latest_10k_pdfs.return_value = [
            GeneratedPdfReport(ticker=ticker, filing_url=f"https://example.test/{ticker}.html", pdf_path=Path(f"generated_reports/{ticker}_latest_10k.pdf"))
            for ticker in ("AAPL", "META", "GOOGL", "AMZN", "NFLX", "GS")
        ]

        app.dependency_overrides[routes.get_settings] = lambda: self._settings()
        app.dependency_overrides[routes.get_report_service] = lambda: mock_report_service

        response = self.client.post(
            "/reports/latest-10k",
            json={"tickers": ["AAPL", "META", "GOOGL", "AMZN", "NFLX", "GS"]},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["summary"]["success_count"], 6)


if __name__ == "__main__":
    unittest.main()

