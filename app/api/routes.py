"""REST routes for SEC filing PDF generation."""

from __future__ import annotations

from typing import Iterator

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.schemas import (
    GenerateReportsRequest,
    GenerateReportsResponse,
    HealthResponse,
    ReportResultResponse,
    ReportSummaryResponse,
)
from app.core.config import COMPANY_NAMES_BY_TICKER, DEFAULT_USER_AGENT, Settings, load_settings, normalize_tickers
from app.runtime import application_services
from app.services.report_service import ReportService

router = APIRouter()

# Absolute safety ceiling on batch size, independent of how large the
# supported-ticker allowlist ever grows. The *effective* limit used per
# request is min(this, len(settings.supported_tickers)) - see
# _max_tickers_for() below - so the two validations never disagree with each
# other (e.g. capping at 10 when only 6 tickers can ever pass the whitelist
# check would be a dead, misleading limit).
MAX_TICKERS_PER_REQUEST_CEILING = 10


def _max_tickers_for(settings: Settings) -> int:
    """Effective per-request ticker cap: never more than the allowlist size."""

    return min(MAX_TICKERS_PER_REQUEST_CEILING, len(settings.supported_tickers))


def get_settings() -> Settings:
    return load_settings()


def get_report_service(settings: Settings = Depends(get_settings)) -> Iterator[ReportService]:
    """FastAPI dependency: builds a ReportService per-request and tears it down after."""

    if settings.sec_user_agent == DEFAULT_USER_AGENT:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SEC_USER_AGENT must be configured before using the report-generation API.",
        )

    with application_services(settings) as services:
        yield services.report_service


@router.get("/health", response_model=HealthResponse, tags=["health"])
def health(settings: Settings = Depends(get_settings)) -> HealthResponse:

    return HealthResponse(status="ok", output_dir=str(settings.sec_output_dir))


@router.post("/reports/latest-10k", response_model=GenerateReportsResponse, tags=["reports"])
def generate_latest_10k_reports(
    request: GenerateReportsRequest,
    settings: Settings = Depends(get_settings),
    report_service: ReportService = Depends(get_report_service),
) -> GenerateReportsResponse:
    """Generate readable PDF reports for the latest available 10-K filings."""

    normalized_tickers = list(normalize_tickers(request.tickers))
    if not normalized_tickers:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one non-empty ticker symbol is required.",
        )
    if len(normalized_tickers) > _max_tickers_for(settings):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"A maximum of {_max_tickers_for(settings)} unique ticker symbols is allowed per request "
                "to keep SEC traffic within a small, reviewable batch size."
            ),
        )

    unsupported_tickers = [ticker for ticker in normalized_tickers if ticker not in settings.supported_tickers]
    if unsupported_tickers:
        supported_list = ", ".join(
            f"{ticker} ({COMPANY_NAMES_BY_TICKER[ticker]})" if ticker in COMPANY_NAMES_BY_TICKER else ticker
            for ticker in settings.supported_tickers
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Unsupported ticker(s): {', '.join(unsupported_tickers)}. "
                f"This API currently only supports: {supported_list}."
            ),
        )

    generated_reports = report_service.generate_latest_10k_pdfs(tuple(normalized_tickers))
    results = [
        ReportResultResponse(
            ticker=result.ticker,
            filing_url=result.filing_url,
            pdf_path=str(result.pdf_path) if result.pdf_path else None,
            error=result.error,
        )
        for result in generated_reports
    ]

    success_count = sum(1 for result in generated_reports if result.pdf_path)
    missing_count = sum(1 for result in generated_reports if not result.pdf_path and not result.error)
    error_count = sum(1 for result in generated_reports if result.error)

    return GenerateReportsResponse(
        tickers=normalized_tickers,
        results=results,
        summary=ReportSummaryResponse(
            requested_count=len(normalized_tickers),
            success_count=success_count,
            missing_count=missing_count,
            error_count=error_count,
        ),
    )

