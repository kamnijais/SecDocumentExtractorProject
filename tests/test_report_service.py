"""Unit tests for PDF generation from SEC 10-K filings."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import MagicMock

from app.services.filing_service import FilingService
from app.services.report_service import ReportService


class ReportServiceTests(unittest.TestCase):
    """Verify that the report service creates PDF files from filing HTML."""

    def test_html_to_paragraphs_preserves_logical_blocks(self) -> None:
        service = ReportService(MagicMock(spec=FilingService), MagicMock(), Path("."))

        paragraphs = service._html_to_paragraphs(
            """
            <html>
              <body>
                <h1>Example 10-K</h1>
                <p>First paragraph.</p>
                <p>Second paragraph.</p>
                <table>
                  <tr><th>Year</th><th>Revenue</th></tr>
                  <tr><td>2025</td><td>$10</td></tr>
                </table>
              </body>
            </html>
            """
        )

        self.assertGreaterEqual(len(paragraphs), 4)
        self.assertEqual(paragraphs[0], "Example 10-K")
        self.assertEqual(paragraphs[1], "First paragraph.")
        self.assertEqual(paragraphs[2], "Second paragraph.")
        self.assertIn("Year | Revenue |", paragraphs[3])

    def test_normalize_pdf_text_replaces_common_unicode_punctuation(self) -> None:
        service = ReportService(MagicMock(spec=FilingService), MagicMock(), Path("."))

        normalized = service._normalize_pdf_text("“Revenue” grew — including café sales…")

        self.assertEqual(normalized, '"Revenue" grew - including café sales...')

    def test_generate_latest_10k_pdf_creates_pdf_file(self) -> None:
        filing_service = MagicMock(spec=FilingService)
        filing_service.fetch_latest_10k_url.return_value = "https://example.test/10k.html"

        client = MagicMock()
        client.fetch_text.return_value = """
            <html>
              <body>
                <h1>Example 10-K</h1>
                <p>This is a test filing for PDF generation.</p>
              </body>
            </html>
        """

        with TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            service = ReportService(filing_service, client, output_dir)
            result = service.generate_latest_10k_pdf("AAPL")

            self.assertEqual(result.ticker, "AAPL")
            self.assertEqual(result.filing_url, "https://example.test/10k.html")
            self.assertIsNotNone(result.pdf_path)
            self.assertTrue(result.pdf_path.exists())
            self.assertGreater(result.pdf_path.stat().st_size, 0)

            # cheap sanity check that we actually wrote a real PDF, not just
            # some bytes with a .pdf extension
            pdf_header = result.pdf_path.read_bytes()[:4]
            self.assertEqual(pdf_header, b"%PDF")

    def test_generate_latest_10k_pdf_returns_no_file_when_missing_report(self) -> None:
        filing_service = MagicMock(spec=FilingService)
        filing_service.fetch_latest_10k_url.return_value = None

        client = MagicMock()

        with TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            service = ReportService(filing_service, client, output_dir)
            result = service.generate_latest_10k_pdf("AAPL")

            self.assertIsNone(result.filing_url)
            self.assertIsNone(result.pdf_path)
            self.assertFalse(list(output_dir.iterdir()))

    def test_generate_latest_10k_pdfs_preserves_batch_order(self) -> None:

        service = ReportService(MagicMock(spec=FilingService), MagicMock(), Path("."))

        first = object()
        second = object()
        third = object()
        service.generate_latest_10k_pdf = MagicMock(side_effect=[first, second, third])

        results = service.generate_latest_10k_pdfs(("META", "AAPL", "NFLX"))

        self.assertEqual(results, [first, second, third])
        self.assertEqual(
            [call.args[0] for call in service.generate_latest_10k_pdf.call_args_list],
            ["META", "AAPL", "NFLX"],
        )


if __name__ == "__main__":
    unittest.main()

