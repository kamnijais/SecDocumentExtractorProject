"""Unit tests for configuration loading and normalization."""

from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from app.core.config import DEFAULT_USER_AGENT, load_settings
from app.core.exceptions import ConfigurationError


class ConfigTests(unittest.TestCase):
    """Verify that environment-backed settings are normalized consistently."""

    def test_load_settings_reads_defaults_and_deduplicates_tickers(self) -> None:
        with TemporaryDirectory() as temp_dir:
            dotenv_path = Path(temp_dir) / ".env"
            dotenv_path.write_text(
                "\n".join(
                    [
                        "SEC_USER_AGENT=Test User test@example.com",
                        "SEC_TICKERS=aapl, msft, AAPL",
                        "SEC_TICKER=nvda",
                        "SEC_TIMEOUT_SECONDS=45",
                    ]
                ),
                encoding="utf-8",
            )

            with patch.dict(os.environ, {}, clear=True):
                settings = load_settings(dotenv_path)

        self.assertEqual(settings.sec_submissions_base_url, "https://data.sec.gov")
        self.assertEqual(settings.sec_archive_url, "https://www.sec.gov/Archives/edgar/data")
        self.assertEqual(settings.sec_ticker_mapping_url, "https://www.sec.gov/files/company_tickers.json")
        self.assertEqual(settings.sec_user_agent, "Test User test@example.com")
        self.assertEqual(settings.sec_timeout_seconds, 45)
        self.assertEqual(str(settings.sec_output_dir), "generated_reports")
        # "nvda" from SEC_TICKER should merge with the SEC_TICKERS list, dedupe
        # the duplicate AAPL, and keep first-seen order.
        self.assertEqual(settings.tickers, ("AAPL", "MSFT", "NVDA"))
        self.assertIsNone(settings.company_cik)
        self.assertEqual(settings.api_host, "127.0.0.1")
        self.assertEqual(settings.api_port, 8000)
        self.assertFalse(settings.api_reload)

    def test_load_settings_defaults_supported_tickers_to_the_six_configured_companies(self) -> None:
        with TemporaryDirectory() as temp_dir:
            dotenv_path = Path(temp_dir) / ".env"
            dotenv_path.write_text("SEC_USER_AGENT=Test User test@example.com\n", encoding="utf-8")

            with patch.dict(os.environ, {}, clear=True):
                settings = load_settings(dotenv_path)

        self.assertEqual(settings.supported_tickers, ("AAPL", "META", "GOOGL", "AMZN", "NFLX", "GS"))

    def test_load_settings_overrides_supported_tickers_from_env(self) -> None:
        with TemporaryDirectory() as temp_dir:
            dotenv_path = Path(temp_dir) / ".env"
            dotenv_path.write_text(
                "SEC_USER_AGENT=Test User test@example.com\nSEC_SUPPORTED_TICKERS=aapl, msft\n",
                encoding="utf-8",
            )

            with patch.dict(os.environ, {}, clear=True):
                settings = load_settings(dotenv_path)

        self.assertEqual(settings.supported_tickers, ("AAPL", "MSFT"))

    def test_load_settings_uses_default_user_agent_when_blank(self) -> None:
        with TemporaryDirectory() as temp_dir:
            dotenv_path = Path(temp_dir) / ".env"
            dotenv_path.write_text("SEC_USER_AGENT=   \n", encoding="utf-8")

            with patch.dict(os.environ, {}, clear=True):
                settings = load_settings(dotenv_path)

        self.assertEqual(settings.sec_user_agent, DEFAULT_USER_AGENT)

    def test_load_settings_raises_for_invalid_timeout(self) -> None:
        with TemporaryDirectory() as temp_dir:
            dotenv_path = Path(temp_dir) / ".env"
            dotenv_path.write_text("SEC_TIMEOUT_SECONDS=abc\n", encoding="utf-8")

            with patch.dict(os.environ, {}, clear=True):
                with self.assertRaises(ConfigurationError):
                    load_settings(dotenv_path)

    def test_load_settings_raises_for_non_positive_timeout(self) -> None:
        with TemporaryDirectory() as temp_dir:
            dotenv_path = Path(temp_dir) / ".env"
            dotenv_path.write_text("SEC_TIMEOUT_SECONDS=0\n", encoding="utf-8")

            with patch.dict(os.environ, {}, clear=True):
                with self.assertRaises(ConfigurationError):
                    load_settings(dotenv_path)

    def test_load_settings_normalizes_company_cik(self) -> None:
        with TemporaryDirectory() as temp_dir:
            dotenv_path = Path(temp_dir) / ".env"
            dotenv_path.write_text("SEC_COMPANY_CIK=320193\n", encoding="utf-8")

            with patch.dict(os.environ, {}, clear=True):
                settings = load_settings(dotenv_path)

        self.assertEqual(settings.company_cik, "0000320193")

    def test_load_settings_raises_for_non_numeric_company_cik(self) -> None:

        with TemporaryDirectory() as temp_dir:
            dotenv_path = Path(temp_dir) / ".env"
            dotenv_path.write_text("SEC_COMPANY_CIK=ABC123\n", encoding="utf-8")

            with patch.dict(os.environ, {}, clear=True):
                with self.assertRaises(ConfigurationError):
                    load_settings(dotenv_path)

    def test_load_settings_overrides_api_host_port_and_reload_from_env(self) -> None:
        with TemporaryDirectory() as temp_dir:
            dotenv_path = Path(temp_dir) / ".env"
            dotenv_path.write_text(
                "API_HOST=0.0.0.0\nAPI_PORT=9090\nAPI_RELOAD=true\n",
                encoding="utf-8",
            )

            with patch.dict(os.environ, {}, clear=True):
                settings = load_settings(dotenv_path)

        self.assertEqual(settings.api_host, "0.0.0.0")
        self.assertEqual(settings.api_port, 9090)
        self.assertTrue(settings.api_reload)

    def test_load_settings_raises_for_invalid_api_port(self) -> None:
        with TemporaryDirectory() as temp_dir:
            dotenv_path = Path(temp_dir) / ".env"
            dotenv_path.write_text("API_PORT=not-a-number\n", encoding="utf-8")

            with patch.dict(os.environ, {}, clear=True):
                with self.assertRaises(ConfigurationError):
                    load_settings(dotenv_path)

    def test_load_settings_raises_for_out_of_range_api_port(self) -> None:
        with TemporaryDirectory() as temp_dir:
            dotenv_path = Path(temp_dir) / ".env"
            dotenv_path.write_text("API_PORT=70000\n", encoding="utf-8")

            with patch.dict(os.environ, {}, clear=True):
                with self.assertRaises(ConfigurationError):
                    load_settings(dotenv_path)


if __name__ == "__main__":
    unittest.main()

