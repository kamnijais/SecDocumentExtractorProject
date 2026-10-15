"""SEC EDGAR client used to resolve tickers and fetch filing metadata."""

from __future__ import annotations

import os
import time
from typing import Any

import requests

from app.core.exceptions import ConfigurationError, SecApiResponseError, TickerResolutionError


class SecEdgarClient:
    """Thin wrapper around the SEC EDGAR HTTP API (submissions + archive + ticker mapping)."""

    def __init__(
        self,
        submissions_base_url: str,
        archive_base_url: str,
        ticker_mapping_url: str,
        user_agent: str | None = None,
        timeout_seconds: int = 30,
    ) -> None:
        """Set up the HTTP session. Raises ConfigurationError if no user agent is available.

        SEC requires a real `User-Agent` identifying the caller (name + email) on every
        request, so we fail fast here instead of letting requests get silently rejected
        later.
        """

        user_agent = user_agent or os.getenv("SEC_USER_AGENT")
        if not user_agent:
            raise ConfigurationError("SEC_USER_AGENT environment variable is required.")

        self.submissions_base_url = submissions_base_url.rstrip("/")
        self.archive_base_url = archive_base_url.rstrip("/")
        self.ticker_mapping_url = ticker_mapping_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

        self.http_session = requests.Session()
        self.http_session.headers.update(
            {
                "User-Agent": user_agent,
                "Accept": "application/json, text/plain, */*",
                "Accept-Encoding": "gzip, deflate",
            }
        )

        # Ticker -> CIK is effectively static for the lifetime of a run, so we
        # cache both the raw mapping and individual lookups to avoid refetching
        # the (fairly large) company_tickers.json more than once.
        self._cik_by_ticker_cache: dict[str, str] = {}
        self._company_ticker_mapping_cache: dict[str, dict[str, Any]] | None = None

    def __enter__(self) -> "SecEdgarClient":
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.close()

    def close(self) -> None:
        """Close the underlying HTTP session."""

        self.http_session.close()

    def resolve_cik(self, ticker: str) -> str:
        """Look up the zero-padded CIK for a ticker (e.g. AAPL -> 0000320193).

        Raises TickerResolutionError if the ticker isn't in the SEC mapping.
        """

        ticker_upper = ticker.strip().upper()
        if ticker_upper in self._cik_by_ticker_cache:
            return self._cik_by_ticker_cache[ticker_upper]

        company_ticker_mapping = self._load_company_tickers()
        for company_ticker_entry in company_ticker_mapping.values():
            if company_ticker_entry["ticker"].upper() == ticker_upper:
                cik_padded = str(company_ticker_entry["cik_str"]).zfill(10)
                self._cik_by_ticker_cache[ticker_upper] = cik_padded
                return cik_padded

        raise TickerResolutionError(f"Ticker symbol '{ticker_upper}' could not be resolved.")

    def get_company_submissions(self, cik: str) -> dict[str, Any]:
        """Fetch the submissions JSON document for a zero-padded CIK."""

        return self._get_json(f"{self.submissions_base_url}/submissions/CIK{cik}.json")

    def fetch_text(self, url: str) -> str:
        """GET an arbitrary SEC URL and return the response body as text."""

        self._throttle()
        response = self.http_session.get(url, timeout=self.timeout_seconds)
        response.raise_for_status()
        return response.text

    def build_filing_url(self, cik: str, accession_number: str, primary_document: str) -> str:
        """Build the absolute archive URL for a specific filing document."""

        cik_short = int(cik)
        normalized_accession = accession_number.replace("-", "")
        return f"{self.archive_base_url}/{cik_short}/{normalized_accession}/{primary_document}"

    def _load_company_tickers(self) -> dict[str, Any]:
        if self._company_ticker_mapping_cache is None:
            self._company_ticker_mapping_cache = self._get_json(self.ticker_mapping_url)

        return self._company_ticker_mapping_cache

    def _get_json(self, url: str) -> dict[str, Any]:
        """GET a URL and parse it as a JSON object, raising SecApiResponseError otherwise."""

        self._throttle()
        response = self.http_session.get(url, timeout=self.timeout_seconds)
        response.raise_for_status()

        try:
            response_payload = response.json()
        except requests.exceptions.JSONDecodeError as exc:
            # SEC occasionally returns an HTML error page (e.g. during an outage)
            # instead of JSON, so surface enough of the response to debug that.
            content_type = response.headers.get("Content-Type", "unknown")
            snippet = response.text[:200].strip().replace("\n", " ")
            raise SecApiResponseError(
                f"SEC response from {url} was not valid JSON. "
                f"Content-Type: {content_type}. Response starts with: {snippet!r}"
            ) from exc

        if not isinstance(response_payload, dict):
            raise SecApiResponseError(
                f"Expected a JSON object from {url}, but received {type(response_payload).__name__}."
            )

        return response_payload

    def _throttle(self) -> None:
        # SEC asks for no more than ~10 requests/second; 0.11s keeps us under that
        # with a small safety margin.
        time.sleep(0.11)

