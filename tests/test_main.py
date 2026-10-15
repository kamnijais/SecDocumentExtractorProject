"""Unit tests for the application entry point."""

from __future__ import annotations

from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

from app.core.config import DEFAULT_USER_AGENT, Settings
from app.services.report_service import GeneratedPdfReport
from app import main as app_main


class MainTests(unittest.TestCase):
    """Verify top-level CLI orchestration behavior."""

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

    def test_main_returns_zero_when_user_agent_is_default_placeholder(self) -> None:
        settings = self._settings(sec_user_agent=DEFAULT_USER_AGENT)

        with patch("app.main.load_settings", return_value=settings), patch("app.main.application_services") as mock_services:
            exit_code = app_main.main()

        self.assertEqual(exit_code, 0)
        mock_services.assert_not_called()

    def test_main_returns_zero_when_no_tickers_are_configured(self) -> None:
        settings = self._settings(tickers=())

        with patch("app.main.load_settings", return_value=settings), patch("app.main.application_services") as mock_services:
            exit_code = app_main.main()

        self.assertEqual(exit_code, 0)
        mock_services.assert_not_called()

    def test_main_returns_one_when_any_report_generation_fails(self) -> None:
        settings = self._settings(tickers=("AAPL", "MSFT"))
        mock_report_service = MagicMock()
        mock_report_service.generate_latest_10k_pdfs.return_value = [
            GeneratedPdfReport(
                ticker="AAPL",
                filing_url="https://example.test/aapl-10k.html",
                pdf_path=Path("generated_reports/AAPL_latest_10k.pdf"),
            ),
            GeneratedPdfReport(ticker="MSFT", filing_url=None, pdf_path=None, error="network error"),
        ]
        # application_services() is a contextmanager, so we need the mock to
        # behave like one too (__enter__ returning the services bundle).
        mock_runtime_services = MagicMock()
        mock_runtime_services.report_service = mock_report_service
        mock_services_context = MagicMock()
        mock_services_context.__enter__.return_value = mock_runtime_services

        with patch("app.main.load_settings", return_value=settings), patch(
            "app.main.application_services",
            return_value=mock_services_context,
        ):
            exit_code = app_main.main()

        self.assertEqual(exit_code, 1)
        mock_services_context.__enter__.assert_called_once_with()
        mock_report_service.generate_latest_10k_pdfs.assert_called_once_with(("AAPL", "MSFT"))


if __name__ == "__main__":
    unittest.main()

