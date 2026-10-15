"""Application entry point for SEC document extraction."""

from __future__ import annotations

# Allow `python app/main.py` to work even if the package isn't installed/on
# PYTHONPATH yet (e.g. running straight from a clone before `uv sync`).
try:
    from app.core.config import DEFAULT_USER_AGENT, load_settings
    from app.runtime import application_services
except ModuleNotFoundError:
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from app.core.config import DEFAULT_USER_AGENT, load_settings
    from app.runtime import application_services


def main() -> int:
    """Run the extraction workflow for every ticker configured in `.env`.

    Returns 0 on a clean run (even if no filings were found) and 1 if at
    least one ticker blew up while we were processing it.
    """

    settings = load_settings()

    print("SEC Document Extraction ready.")
    print(f"Submissions base URL: {settings.sec_submissions_base_url}")
    print(f"PDF output directory: {settings.sec_output_dir}")

    if settings.sec_user_agent == DEFAULT_USER_AGENT:
        print("Set SEC_USER_AGENT in .env before making SEC requests.")
        return 0

    if not settings.tickers:
        print("Set SEC_TICKERS or SEC_TICKER in .env to fetch the latest 10-K filing URL for one or more companies.")
        return 0

    print(f"Tickers to process: {', '.join(settings.tickers)}")

    with application_services(settings) as services:
        results = services.report_service.generate_latest_10k_pdfs(settings.tickers)

    success_count = 0
    missing_count = 0
    failure_count = 0

    for result in results:
        print(f"\nProcessing {result.ticker}...")
        if result.error:
            failure_count += 1
            print(f"Error for {result.ticker}: {result.error}")
        elif result.pdf_path:
            success_count += 1
            print(f"Latest 10-K PDF for {result.ticker}: {result.pdf_path}")
            if result.filing_url:
                print(f"Source URL: {result.filing_url}")
        else:
            missing_count += 1
            print(f"No recent 10-K filing found for {result.ticker}.")

    print("\nRun summary:")
    print(f"- Successful filings found: {success_count}")
    print(f"- No 10-K found: {missing_count}")
    print(f"- Errors: {failure_count}")

    return 1 if failure_count else 0


if __name__ == "__main__":
    raise SystemExit(main())

