"""
Renders a job posting dict (as returned by job_fetcher) into a PDF file,
so the ingest pipeline has an actual document to save + extract text from
(matching the same PDF-first flow as the resume upload feature).
"""

import html
import re
from typing import Any, Dict

from fpdf import FPDF


def _strip_html(raw_html: str) -> str:
    """Arbeitnow's description field contains HTML - strip tags and unescape entities."""
    text = re.sub(r"<br\s*/?>", "\n", raw_html)  # line breaks first
    text = re.sub(r"<[^>]+>", "", text)  # remove remaining tags
    text = html.unescape(text)  # &amp; -> &, etc.
    return text.strip()


def _extract_company_name(job: Dict[str, Any]) -> str:
    """
    Arbeitnow's 'company' field can be a plain string or a nested object
    with a 'name' key depending on the endpoint/response - handle both.
    """
    company = job.get("company") or job.get("company_name")
    if isinstance(company, dict):
        return company.get("name", "Unknown Company")
    return company or "Unknown Company"


def generate_job_pdf(job: Dict[str, Any]) -> bytes:
    """
    Builds a simple one-page-plus PDF containing the job's title, company,
    location, tags and full description. Returns the PDF as raw bytes.
    """
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    def write_block(font_style: str, size: int, text: str, line_height: int = 8) -> None:
        """multi_cell leaves the x-cursor at the page's right edge, not back
        at the left margin - reset it before every call or the next call
        thinks there's almost no width left to render into."""
        pdf.set_x(pdf.l_margin)
        pdf.set_font("Helvetica", font_style, size)
        pdf.multi_cell(0, line_height, text)

    write_block("B", 16, job.get("title", "Untitled Role"), line_height=10)

    company = _extract_company_name(job)
    location = job.get("location", "Not specified")
    remote = "Remote" if job.get("remote") else "On-site"
    write_block("", 12, f"{company} | {location} | {remote}")

    tags = job.get("tags", [])
    if tags:
        write_block("I", 11, "Tags: " + ", ".join(tags))

    url = job.get("url", "")
    if url:
        write_block("", 10, f"Source: {url}")

    pdf.ln(4)
    description_text = _strip_html(job.get("description", ""))
    # fpdf2's multi_cell can't handle non-Latin1 characters with core fonts -
    # replace anything it can't encode rather than crashing the whole request.
    safe_text = description_text.encode("latin-1", errors="replace").decode("latin-1")
    write_block("", 11, safe_text, line_height=6)

    return bytes(pdf.output())
