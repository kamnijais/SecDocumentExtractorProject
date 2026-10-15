"""Pydantic schemas for the SEC document extraction API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class GenerateReportsRequest(BaseModel):
    """Request body for generating the latest 10-K PDF reports."""

    tickers: list[str] = Field(
        ...,
        min_length=1,
        description=(
            "One or more stock ticker symbols to fetch and convert. "
            "Currently limited to: AAPL, META, GOOGL, AMZN, NFLX, GS."
        ),
        examples=[["AAPL", "MSFT"]],
    )


class ReportResultResponse(BaseModel):
    """Per-ticker result returned by the API."""

    ticker: str
    filing_url: str | None
    pdf_path: str | None
    error: str | None = None


class ReportSummaryResponse(BaseModel):
    """Summary counts for a batch report-generation request."""

    requested_count: int
    success_count: int
    missing_count: int
    error_count: int


class GenerateReportsResponse(BaseModel):
    """Batch response for latest 10-K report generation."""

    tickers: list[str]
    results: list[ReportResultResponse]
    summary: ReportSummaryResponse


class HealthResponse(BaseModel):
    """Lightweight health/status response."""

    status: str
    output_dir: str

