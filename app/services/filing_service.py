"""Business logic for locating SEC filing URLs."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.exceptions import SecApiResponseError
from app.services.sec_client import SecEdgarClient


@dataclass(frozen=True)
class FilingResult:
    """Outcome for a single ticker processed by the filing service."""

    ticker: str
    filing_url: str | None
    error: str | None = None


class FilingService:
    """Finds the latest 10-K filing URL for a ticker, on top of a SecEdgarClient."""

    def __init__(self, sec_client: SecEdgarClient) -> None:
        self.sec_client = sec_client

    def fetch_latest_10k_url(self, ticker: str) -> str | None:
        """Resolve ticker -> CIK -> submissions feed -> most recent 10-K document URL.

        Returns None if the company has no 10-K in its recent filings list (this is
        a normal case, not an error - some tickers just won't have one).
        """

        cik = self.sec_client.resolve_cik(ticker)
        submissions_payload = self.sec_client.get_company_submissions(cik)

        filings = submissions_payload.get("filings")
        if not isinstance(filings, dict):
            raise SecApiResponseError("SEC submissions payload is missing the 'filings' object.")

        recent_filings = filings.get("recent")
        if not isinstance(recent_filings, dict):
            raise SecApiResponseError("SEC submissions payload is missing the 'recent' filings object.")

        forms = recent_filings.get("form")
        accession_numbers = recent_filings.get("accessionNumber")
        primary_documents = recent_filings.get("primaryDocument")
        if not isinstance(forms, list) or not isinstance(accession_numbers, list) or not isinstance(primary_documents, list):
            raise SecApiResponseError("SEC submissions payload does not contain the expected recent filing lists.")

        # The "recent" arrays are parallel lists indexed by filing, newest first,
        # so the first 10-K we hit is the latest one.
        for idx, form in enumerate(forms):
            if form == "10-K":
                accession_number = accession_numbers[idx]
                primary_document = primary_documents[idx]
                if not isinstance(accession_number, str) or not isinstance(primary_document, str):
                    raise SecApiResponseError("SEC submissions payload contains invalid filing metadata types.")
                return self.sec_client.build_filing_url(cik, accession_number, primary_document)

        return None

    def fetch_latest_10k_urls(self, tickers: tuple[str, ...]) -> list[FilingResult]:
        """Same as fetch_latest_10k_url, but for a batch - one bad ticker won't abort the rest."""

        results: list[FilingResult] = []
        for ticker in tickers:
            try:
                filing_url = self.fetch_latest_10k_url(ticker)
            except Exception as exc:
                results.append(FilingResult(ticker=ticker, filing_url=None, error=str(exc)))
                continue

            results.append(FilingResult(ticker=ticker, filing_url=filing_url))

        return results

