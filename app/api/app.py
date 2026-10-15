"""FastAPI application for SEC filing to PDF generation."""

from __future__ import annotations

import uvicorn
from fastapi import FastAPI

from app.api.routes import router
from app.core.config import load_settings


def create_app() -> FastAPI:
    app = FastAPI(
        title="SEC Document Extractor API",
        version="0.1.0",
        description=(
            "Generate readable PDF reports from the latest available SEC 10-K filings. "
            "The API accepts one or more ticker symbols and returns per-ticker file results."
        ),
    )
    app.include_router(router)
    return app


app = create_app()


def main() -> None:
    # Host/port/reload are config-driven (API_HOST, API_PORT, API_RELOAD) rather
    # than hardcoded, so this doubles as both the local dev launcher and a
    # starting point for container/deployment use without editing source.
    # Defaults to loopback-only, matching the rest of this app's env-driven
    # settings pattern (SEC_USER_AGENT, SEC_OUTPUT_DIR, etc.).
    settings = load_settings()
    uvicorn.run(
        "app.api.app:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.api_reload,
    )


if __name__ == "__main__":
    main()

