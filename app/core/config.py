"""Configuration helpers for the SEC document extraction application."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
import os

from dotenv import load_dotenv

from app.core.exceptions import ConfigurationError

DEFAULT_DOTENV_PATH = Path(__file__).resolve().parents[2] / ".env"
DEFAULT_USER_AGENT = "SecDocumentExtraction/0.1.0 (set SEC_USER_AGENT in .env)"

# Default allowlist for the API's ticker restriction. This is only a fallback -
# the actual enforced list is `Settings.supported_tickers`, which reads from
# `SEC_SUPPORTED_TICKERS` so the list can be changed via config instead of a
# code change. A full database felt like overkill for "6 fixed strings"; env
# config matches how every other setting in this app already works.
_DEFAULT_SUPPORTED_TICKERS = "AAPL,META,GOOGL,AMZN,NFLX,GS"

# Friendly display names, used only for error messages/docs. Purely cosmetic -
# a ticker configured via SEC_SUPPORTED_TICKERS that isn't in this dict is
# still accepted, it just won't have a company name attached in the message.
COMPANY_NAMES_BY_TICKER: dict[str, str] = {
    "AAPL": "Apple",
    "META": "Meta",
    "GOOGL": "Alphabet",
    "AMZN": "Amazon",
    "NFLX": "Netflix",
    "GS": "Goldman Sachs",
}


@dataclass(frozen=True)
class Settings:
    """Runtime configuration loaded from environment variables."""

    sec_submissions_base_url: str
    sec_archive_url: str
    sec_ticker_mapping_url: str
    sec_user_agent: str
    sec_timeout_seconds: int
    sec_output_dir: Path
    tickers: tuple[str, ...]
    supported_tickers: tuple[str, ...]
    api_host: str
    api_port: int
    api_reload: bool
    company_cik: str | None = None


def load_settings(dotenv_path: Path | None = None) -> Settings:
    """Read `.env` (or the given path) and build a validated `Settings` object.

    Falls back to sensible SEC defaults when a value isn't set, so the app
    still runs with just `SEC_USER_AGENT` configured.
    """

    load_dotenv(dotenv_path or DEFAULT_DOTENV_PATH, override=False)

    timeout_value = os.getenv("SEC_TIMEOUT_SECONDS", "30")
    try:
        timeout_seconds = int(timeout_value)
    except ValueError as exc:
        raise ConfigurationError("SEC_TIMEOUT_SECONDS must be an integer.") from exc

    if timeout_seconds <= 0:
        raise ConfigurationError("SEC_TIMEOUT_SECONDS must be greater than zero.")

    port_value = os.getenv("API_PORT", "8000")
    try:
        api_port = int(port_value)
    except ValueError as exc:
        raise ConfigurationError("API_PORT must be an integer.") from exc

    if not 0 < api_port < 65536:
        raise ConfigurationError("API_PORT must be between 1 and 65535.")

    return Settings(
        sec_submissions_base_url=os.getenv("SEC_BASE_URL", "https://data.sec.gov").rstrip("/"),
        sec_archive_url=os.getenv("SEC_ARCHIVE_URL", "https://www.sec.gov/Archives/edgar/data").rstrip("/"),
        sec_ticker_mapping_url=os.getenv("SEC_TICKER_MAPPING_URL", "https://www.sec.gov/files/company_tickers.json").rstrip("/"),
        sec_user_agent=os.getenv("SEC_USER_AGENT", DEFAULT_USER_AGENT).strip() or DEFAULT_USER_AGENT,
        sec_timeout_seconds=timeout_seconds,
        sec_output_dir=Path(os.getenv("SEC_OUTPUT_DIR", "generated_reports")),
        tickers=_parse_tickers(
            os.getenv("SEC_TICKERS"),
            os.getenv("SEC_TICKER"),
        ),
        supported_tickers=normalize_tickers(
            os.getenv("SEC_SUPPORTED_TICKERS", _DEFAULT_SUPPORTED_TICKERS).split(",")
        ),
        api_host=os.getenv("API_HOST", "127.0.0.1"),
        api_port=api_port,
        api_reload=os.getenv("API_RELOAD", "false").strip().lower() in ("1", "true", "yes"),
        company_cik=_normalize_cik(os.getenv("SEC_COMPANY_CIK")),
    )


def _normalize_cik(value: str | None) -> str | None:
    """Zero-pad a raw CIK to the 10-digit form the SEC expects.

    Blank/missing values are fine (CIK is optional config), but anything
    non-numeric is a real mistake and should fail loudly.
    """

    if value is None:
        return None

    cleaned = value.strip()
    if not cleaned:
        return None

    if not cleaned.isdigit():
        raise ConfigurationError("SEC_COMPANY_CIK must contain digits only.")

    return cleaned.zfill(10)


def _parse_tickers(batch_value: str | None, single_value: str | None) -> tuple[str, ...]:
    """Merge `SEC_TICKERS` (comma list) and `SEC_TICKER` (single) into one tuple."""

    values: list[str] = []

    if batch_value:
        values.extend(batch_value.split(","))
    if single_value:
        values.append(single_value)

    return normalize_tickers(values)


def normalize_tickers(values: Iterable[str]) -> tuple[str, ...]:
    """Upper-case, trim, and de-dupe ticker symbols while keeping first-seen order."""

    normalized: list[str] = []
    seen: set[str] = set()
    for raw_value in values:
        ticker = raw_value.strip().upper()
        if not ticker:
            continue
        if ticker not in seen:
            seen.add(ticker)
            normalized.append(ticker)

    return tuple(normalized)

