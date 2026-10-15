"""Unit tests for the API server launcher (`app.api.app.main`)."""

from __future__ import annotations

from pathlib import Path
import unittest
from unittest.mock import patch

from app.api import app as app_module
from app.core.config import Settings


class ApiMainTests(unittest.TestCase):
    """Verify the dev launcher reads host/port/reload from config, not hardcoded values."""

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

    def test_main_passes_settings_driven_host_port_and_reload_to_uvicorn(self) -> None:
        custom_settings = self._settings(api_host="0.0.0.0", api_port=9090, api_reload=True)

        with patch("app.api.app.load_settings", return_value=custom_settings), patch(
            "app.api.app.uvicorn.run"
        ) as mock_run:
            app_module.main()

        mock_run.assert_called_once_with(
            "app.api.app:app",
            host="0.0.0.0",
            port=9090,
            reload=True,
        )


if __name__ == "__main__":
    unittest.main()

