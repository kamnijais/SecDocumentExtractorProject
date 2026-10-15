# SEC Document Extractor Project

A Python project that fetches the latest SEC 10-K filing for one or more tickers and converts the filing into a readable PDF report.

## What the Project Does

- resolves a ticker symbol to its SEC CIK
- fetches the company's recent SEC submissions
- finds the latest available `10-K`
- downloads the filing HTML from EDGAR
- converts the filing into a text-based PDF report
- optionally exposes the same workflow through a REST endpoint

## Repository Layout

```text
SecDocumentExtractorProject/
├── .env.example
├── .gitignore
├── AI_USE_DISCLOSURE.md
├── app/
│   ├── api/
│   │   ├── app.py
│   │   ├── routes.py
│   │   └── schemas.py
│   ├── core/
│   │   ├── config.py
│   │   └── exceptions.py
│   ├── services/
│   │   ├── filing_service.py
│   │   ├── report_service.py
│   │   └── sec_client.py
│   ├── main.py
│   └── runtime.py
├── tests/
│   ├── test_api.py
│   ├── test_config.py
│   ├── test_main.py
│   ├── test_report_service.py
│   └── test_sec_client.py
├── pyproject.toml
├── README.md
├── requirements.txt
└── uv.lock
```

## Requirements

- Python `3.10+`
- an SEC-compliant `User-Agent` string

## Setup

1. Copy `.env.example` to `.env`.
2. Fill in your SEC user-agent information.
3. Install dependencies with either `uv` or `pip`.

Example environment file:

```dotenv
SEC_USER_AGENT=Your Name your.email@example.com
SEC_BASE_URL=https://data.sec.gov
SEC_ARCHIVE_URL=https://www.sec.gov/Archives/edgar/data
SEC_TICKER_MAPPING_URL=https://www.sec.gov/files/company_tickers.json
SEC_OUTPUT_DIR=generated_reports
SEC_TICKERS=AAPL,META,GOOGL
SEC_TICKER=
SEC_TIMEOUT_SECONDS=30
SEC_COMPANY_CIK=
SEC_SUPPORTED_TICKERS=AAPL,META,GOOGL,AMZN,NFLX,GS
API_HOST=127.0.0.1
API_PORT=8000
API_RELOAD=false
```

Notes:

- `SEC_TICKERS` accepts a comma-separated list.
- `SEC_TICKER` can be used for a single additional ticker.
- if both are set, the app de-duplicates and preserves first-seen order.
- the SEC URL values are optional overrides; the defaults match the values above.
- `SEC_SUPPORTED_TICKERS` controls which tickers the **REST API** will accept
  (see below). It defaults to the six companies listed in this README if not
  set, and can be overridden per-environment without a code change.
- `API_HOST` / `API_PORT` / `API_RELOAD` control how `app/api/app.py`'s dev
  launcher binds Uvicorn. These are config-driven rather than hardcoded so the
  bind address/port/reload behavior can change per environment (local dev vs.
  container vs. CI) without touching source. Defaults are loopback-only on
  port `8000` with reload disabled.

Install with `uv`:

```bash
uv sync
```

Install with `pip`:

```bash
python3 -m pip install -r requirements.txt
```

## Running the Project

Run via module:

```bash
python3 -m app.main
```

Run with `uv`:

```bash
uv run python -m app.main
```

Run via the console script after installation:

```bash
uv run sec-document-extraction
```

## Running the REST API

Start the API server with `uv`:

```bash
uv run sec-document-extraction-api
```

Or with Python directly:

```bash
python3 -m app.api.app
```

Once running, the API is available at `http://127.0.0.1:8000`.

### Endpoint Design

The API accepts a JSON body with a `tickers` array:

```json
{
  "tickers": ["AAPL", "META", "GOOGL"]
}
```

This format was chosen because it is:

- explicit and easy to validate
- naturally supports batch processing
- simple to discuss during an interview
- flexible enough for future metadata if the API grows later

Supported companies:

- the API currently only supports a small, fixed set of companies:
  - `AAPL` - Apple
  - `META` - Meta
  - `GOOGL` - Alphabet
  - `AMZN` - Amazon
  - `NFLX` - Netflix
  - `GS` - Goldman Sachs
- any other ticker is rejected with a `422` response

**Assumption:** the project assumes the API only needs to serve 10-K reports
for the six companies listed above, so `Settings.supported_tickers`
(`app/core/config.py`, driven by `SEC_SUPPORTED_TICKERS`) enforces that as an
explicit allowlist rather than leaving the endpoint open to arbitrary tickers.
This is a scope decision, not a technical limitation - the underlying pipeline
(ticker -> CIK -> SEC submissions -> filing download -> PDF) is ticker-agnostic
and already works for any company in SEC EDGAR. Supporting more companies
later is just a config change (`SEC_SUPPORTED_TICKERS=AAPL,META,GOOGL,AMZN,NFLX,GS,MSFT,...`),
not a code or redeploy change - no changes are needed in `SecEdgarClient`,
`FilingService`, or `ReportService`. A database was considered for this list
and intentionally not used: with only a handful of entries that rarely change,
an env-driven allowlist keeps the same configuration pattern already used for
every other setting in this app (`SEC_TICKERS`, `SEC_OUTPUT_DIR`, etc.)
without adding a storage dependency for something this small.

Batch-size note:

- the API caps a request at `min(10, number of supported tickers)` - with the
  default six-company allowlist, that means **6 unique tickers per request**,
  not a flat 10
- the flat `10` only becomes the binding limit if `SEC_SUPPORTED_TICKERS` is
  later configured with more than 10 companies
- this keeps the batch-size cap and the ticker allowlist logically consistent
  with each other instead of advertising a limit (10) that could never
  actually be reached while the allowlist stays small
- the client still applies per-request throttling internally on top of this

### REST Endpoints

- `GET /health` - health/status check
- `POST /reports/latest-10k` - fetch and convert the latest 10-K for one or more tickers

Example request:

```bash
curl -X POST "http://127.0.0.1:8000/reports/latest-10k" \
  -H "Content-Type: application/json" \
  -d '{"tickers": ["AAPL", "GS"]}'
```

Example response:

```json
{
  "tickers": ["AAPL", "GS"],
  "results": [
	{
	  "ticker": "AAPL",
	  "filing_url": "https://www.sec.gov/Archives/.../aapl-20250927.htm",
	  "pdf_path": "generated_reports/AAPL_latest_10k.pdf",
	  "error": null
	},
	{
	  "ticker": "GS",
	  "filing_url": null,
	  "pdf_path": null,
	  "error": "network error"
	}
  ],
  "summary": {
	"requested_count": 2,
	"success_count": 1,
	"missing_count": 0,
	"error_count": 1
  }
}
```

Example rejection for an unsupported ticker:

```bash
curl -X POST "http://127.0.0.1:8000/reports/latest-10k" \
  -H "Content-Type: application/json" \
  -d '{"tickers": ["MSFT"]}'
```

```json
{
  "detail": "Unsupported ticker(s): MSFT. This API currently only supports: AAPL (Apple), META (Meta), GOOGL (Alphabet), AMZN (Amazon), NFLX (Netflix), GS (Goldman Sachs)."
}
```

## Output Behavior

Generated reports are written to the directory configured by `SEC_OUTPUT_DIR`.

Important note about the PDFs:

- the output is a **readable text-based PDF rendering** of the SEC filing HTML
- it is **not** a pixel-perfect reproduction of the original SEC page layout
- the report is optimized for readability and extraction rather than visual fidelity

## Running Tests

Run the full unit test suite:

```bash
python3 -m unittest discover -s tests -v
```

Or with `uv`:

```bash
uv run python -m unittest discover -s tests -v
```

## AI Assistance Disclosure

This project used AI assistance during development. See `AI_USE_DISCLOSURE.md`
for the scope and boundaries of that assistance.

## Future Improvements

- **Dockerization** - not included in this submission by choice; planned as a
  follow-up so the API/CLI can be run in an isolated container without a local
  Python/`uv` setup.
- Structured logging in place of `print()` statements.
- Retry/backoff on transient SEC request failures.

## Design Notes

The project uses a layered structure:

- `app/api/` for the REST layer and request/response schemas
- `app/core/` for configuration and exception definitions
- `app/services/sec_client.py` for HTTP communication with SEC endpoints
- `app/services/filing_service.py` for filing lookup business logic
- `app/services/report_service.py` for HTML-to-PDF conversion
- `app/runtime.py` for shared service wiring
- `app/main.py` for CLI workflow orchestration

This separation keeps network access, business logic, and output generation independently testable.
