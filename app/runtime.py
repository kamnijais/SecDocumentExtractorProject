"""Shared application wiring for CLI and API entry points."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator

from app.core.config import Settings, load_settings
from app.services.filing_service import FilingService
from app.services.report_service import ReportService
from app.services.sec_client import SecEdgarClient


@dataclass(frozen=True)
class ApplicationServices:
    """Bundle of configured services shared by the CLI and the API."""

    settings: Settings
    sec_client: SecEdgarClient
    filing_lookup_service: FilingService
    report_service: ReportService


@contextmanager
def application_services(settings: Settings | None = None) -> Iterator[ApplicationServices]:
    """Build the service graph for one workflow run and clean up the HTTP session after.

    Pass in `settings` explicitly in tests; leave it out to load from `.env`.
    """

    active_settings = settings or load_settings()
    with SecEdgarClient(
        submissions_base_url=active_settings.sec_submissions_base_url,
        archive_base_url=active_settings.sec_archive_url,
        ticker_mapping_url=active_settings.sec_ticker_mapping_url,
        user_agent=active_settings.sec_user_agent,
        timeout_seconds=active_settings.sec_timeout_seconds,
    ) as sec_client:
        filing_lookup_service = FilingService(sec_client)
        yield ApplicationServices(
            settings=active_settings,
            sec_client=sec_client,
            filing_lookup_service=filing_lookup_service,
            report_service=ReportService(filing_lookup_service, sec_client, active_settings.sec_output_dir),
        )

