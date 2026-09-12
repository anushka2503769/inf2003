"""
Helpers for pulling raw text out of an uploaded resume file, and for
turning that raw text into structured fields (skills/education/
experience/projects) using keyword matching + section splitting.
"""

from io import BytesIO

import pypdf
from docx import Document

from backend.app.section_parser import split_into_sections
from backend.app.skill_matcher import match_skills

SUPPORTED_CONTENT_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

SUPPORTED_EXTENSIONS = {".pdf", ".docx"}


def resolve_file_kind(filename: str, content_type: str) -> str:
    """
    Determines whether a file is a PDF or DOCX, trusting the filename
    extension over content_type - clients (Postman, browsers, some OSes)
    frequently send a generic 'application/octet-stream' instead of the
    correct MIME type, especially for DOCX.

    Returns "pdf" or "docx", or raises ValueError if neither matches.
    """
    lower_name = filename.lower()

    if lower_name.endswith(".pdf") or content_type == "application/pdf":
        return "pdf"

    if lower_name.endswith(".docx") or content_type == (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ):
        return "docx"

    raise ValueError(
        f"Unsupported file: filename='{filename}', content_type='{content_type}'. "
        "Use a .pdf or .docx file."
    )


def extract_raw_text(file_bytes: bytes, file_kind: str) -> str:
    """Extract plain text from a PDF or DOCX file's raw bytes. file_kind is 'pdf' or 'docx'."""
    if file_kind == "pdf":
        reader = pypdf.PdfReader(BytesIO(file_bytes))
        return "\n".join(page.extract_text() or "" for page in reader.pages)

    if file_kind == "docx":
        document = Document(BytesIO(file_bytes))
        return "\n".join(paragraph.text for paragraph in document.paragraphs)

    raise ValueError(f"Unsupported file_kind: {file_kind}")


def extract_structured_fields(raw_text: str) -> dict:
    """
    Keyword/rule-based extraction:
    - skills: matched against the SQL skills table (see skill_matcher.py)
    - education/experience/projects: split out by section header (see section_parser.py)
    """
    sections = split_into_sections(raw_text)

    return {
        "skills": match_skills(raw_text),
        "education": sections["education"],
        "experience": sections["experience"],
        "projects": sections["projects"],
    }