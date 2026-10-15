"""Business logic for turning the latest 10-K filing into a PDF report."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import unicodedata

from bs4 import BeautifulSoup, NavigableString
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import simpleSplit
from reportlab.pdfgen.canvas import Canvas

from app.core.exceptions import SecApiResponseError
from app.services.filing_service import FilingService
from app.services.sec_client import SecEdgarClient


@dataclass(frozen=True)
class GeneratedPdfReport:
    """Outcome for a single ticker processed into a PDF report."""

    ticker: str
    filing_url: str | None
    pdf_path: Path | None
    error: str | None = None


class ReportService:
    """Turns a SEC 10-K HTML filing into a readable text PDF."""

    # Tags that should start a new "paragraph" when we flatten the HTML to text.
    # This list isn't exhaustive (SEC filings love nesting divs inside divs inside
    # tables...) but it covers the common structural elements well enough.
    _BLOCK_TAGS = {
        "address",
        "article",
        "aside",
        "blockquote",
        "div",
        "dl",
        "fieldset",
        "figcaption",
        "figure",
        "footer",
        "form",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "hr",
        "li",
        "main",
        "nav",
        "ol",
        "p",
        "pre",
        "section",
        "table",
        "tr",
        "ul",
    }

    # reportlab's base Helvetica font only supports WinAnsi/cp1252, but SEC
    # filings are full of "smart" Unicode punctuation (curly quotes, en/em
    # dashes, bullets...). Map the common ones to their ASCII equivalents so
    # they don't just get dropped or turned into boxes in the PDF.
    _UNICODE_REPLACEMENTS = str.maketrans(
        {
            "\u00a0": " ",
            "\u00ad": "",
            "\u2010": "-",
            "\u2011": "-",
            "\u2012": "-",
            "\u2013": "-",
            "\u2014": "-",
            "\u2015": "-",
            "\u2018": "'",
            "\u2019": "'",
            "\u201a": "'",
            "\u201b": "'",
            "\u201c": '"',
            "\u201d": '"',
            "\u201e": '"',
            "\u2022": "*",
            "\u2026": "...",
            "\u2212": "-",
        }
    )

    def __init__(
        self,
        filing_lookup_service: FilingService,
        sec_client: SecEdgarClient,
        report_output_directory: Path,
    ) -> None:
        self.filing_lookup_service = filing_lookup_service
        self.sec_client = sec_client
        self.report_output_directory = report_output_directory
        self.report_output_directory.mkdir(parents=True, exist_ok=True)

    def generate_latest_10k_pdf(self, ticker: str) -> GeneratedPdfReport:
        """Look up, download, and render the latest 10-K for one ticker.

        Any failure along the way (network, parsing, missing filing, etc.) is
        captured in the returned report's `error` field rather than raised, so
        callers processing a batch don't need their own try/except per ticker.
        """

        filing_url: str | None = None
        try:
            filing_url = self.filing_lookup_service.fetch_latest_10k_url(ticker)
            if not filing_url:
                return GeneratedPdfReport(ticker=ticker, filing_url=None, pdf_path=None)

            html = self.sec_client.fetch_text(filing_url)
            pdf_path = self.report_output_directory / f"{ticker.upper()}_latest_10k.pdf"
            self._write_pdf(pdf_path=pdf_path, ticker=ticker, source_url=filing_url, html=html)
            return GeneratedPdfReport(ticker=ticker, filing_url=filing_url, pdf_path=pdf_path)
        except Exception as exc:
            return GeneratedPdfReport(ticker=ticker, filing_url=filing_url, pdf_path=None, error=str(exc))

    def generate_latest_10k_pdfs(self, tickers: tuple[str, ...]) -> list[GeneratedPdfReport]:
        """Generate PDFs for a batch of tickers, continuing past individual failures."""

        return [self.generate_latest_10k_pdf(ticker) for ticker in tickers]

    def _write_pdf(self, pdf_path: Path, ticker: str, source_url: str, html: str) -> None:
        """Lay out the extracted paragraphs onto letter-size pages and save the PDF."""

        paragraphs = self._html_to_paragraphs(html)
        canvas = Canvas(str(pdf_path), pagesize=letter)
        page_width, page_height = letter
        margin = 0.65 * 72  # ~0.65in margins, in points (72pt = 1in)
        text_width = page_width - (2 * margin)
        body_font = "Helvetica"
        body_size = 9
        leading = 11  # line height in points

        def new_page() -> None:
            nonlocal cursor_y
            canvas.showPage()
            cursor_y = self._draw_header(canvas, ticker, source_url, margin, page_width, page_height)

        cursor_y = self._draw_header(canvas, ticker, source_url, margin, page_width, page_height)

        for paragraph in paragraphs:
            wrapped_lines = simpleSplit(paragraph, body_font, body_size, text_width)
            if not wrapped_lines:
                cursor_y -= leading
                continue

            for line in wrapped_lines:
                if cursor_y < margin:
                    new_page()
                canvas.setFont(body_font, body_size)
                canvas.drawString(margin, cursor_y, line)
                cursor_y -= leading

            cursor_y -= leading // 2  # small gap between paragraphs

        canvas.save()

    def _draw_header(
        self,
        canvas: Canvas,
        ticker: str,
        source_url: str,
        margin: float,
        page_width: float,
        page_height: float,
    ) -> float:
        """Draw the title + source URL at the top of a page, return the next free y."""

        canvas.setFont("Helvetica-Bold", 16)
        cursor_y = page_height - margin
        canvas.drawString(margin, cursor_y, f"{ticker.upper()} Latest 10-K Report")

        canvas.setFont("Helvetica", 9)
        cursor_y -= 18

        for line in simpleSplit(f"Source URL: {source_url}", "Helvetica", 9, page_width - (2 * margin)):
            canvas.drawString(margin, cursor_y, line)
            cursor_y -= 12

        canvas.drawString(margin, cursor_y, "Generated from SEC HTML filing content")
        return cursor_y - 18

    def _html_to_paragraphs(self, html: str) -> list[str]:
        """Strip the HTML down to a list of readable text paragraphs.

        We insert a newline around block-level tags before calling get_text()
        so BeautifulSoup doesn't just mash every <div>/<td>/<p> together into
        one giant wall of text - that's the main thing that used to make these
        PDFs look like garbage.
        """

        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()

        for tag in soup.find_all("br"):
            tag.replace_with(NavigableString("\n"))

        for cell in soup.find_all(["th", "td"]):
            cell.append(NavigableString(" | "))

        for tag in soup.find_all(self._BLOCK_TAGS):
            tag.insert_before(NavigableString("\n"))
            tag.insert_after(NavigableString("\n"))

        raw_text = soup.get_text()
        paragraphs: list[str] = []
        buffer: list[str] = []

        for line in raw_text.splitlines():
            cleaned = self._normalize_pdf_text(line)
            if cleaned:
                buffer.append(cleaned)
                continue

            if buffer:
                paragraphs.append(" ".join(buffer))
                buffer = []

        if buffer:
            paragraphs.append(" ".join(buffer))

        paragraphs = [paragraph for paragraph in paragraphs if paragraph]

        if not paragraphs:
            raise SecApiResponseError("The SEC filing HTML did not contain any extractable text.")

        return paragraphs

    def _normalize_pdf_text(self, text: str) -> str:
        """Collapse whitespace and map Unicode punctuation down to cp1252-safe characters."""

        collapsed = " ".join(text.split())
        if not collapsed:
            return ""

        normalized = unicodedata.normalize("NFKC", collapsed).translate(self._UNICODE_REPLACEMENTS)
        return normalized.encode("cp1252", "ignore").decode("cp1252").strip()

