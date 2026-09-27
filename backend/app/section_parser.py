"""
Splits raw resume text into sections (education, experience, projects, ...)
using a regex over common header phrasings. This is a heuristic, not a
guarantee - resumes with unusual formatting/headers may not split cleanly.
"""

import re
from typing import Dict, List

# Maps our schema's section names to the header phrasings we'll look for.
# Add more variants here as you encounter real resumes that don't match.
SECTION_HEADER_PATTERNS: Dict[str, List[str]] = {
    "education": [r"education", r"academic background", r"qualifications"],
    "experience": [
        r"(work\s+)?experience",
        r"employment history",
        r"internship experience",
        r"professional experience",
    ],
    "projects": [r"projects", r"academic projects", r"personal projects"],
}

# Sections we recognise but don't currently store in the schema - listing
# them here means their content gets excluded from misclassified sections.
# Keep this list growing as new real resumes surface headers we don't catch yet.
KNOWN_OTHER_HEADERS = [
    r"skills",
    r"technical skills",
    r"certifications?( (&|and) learning)?",
    r"certifications? (&|and) training",
    r"summary",
    r"profile",
    r"objective",
    r"contact",
    r"references",
    r"languages",
    r"other experience",
    r"extracurricular(\s+activities)?",
    r"activities",
    r"awards?( (&|and) honou?rs)?",
    r"volunteer(ing)?( experience)?",
    r"publications",
    r"interests",
    r"hobbies",
]


def _build_header_regex() -> re.Pattern:
    """
    Builds one regex that matches ANY recognised header (from our target
    sections or the 'other' list), anchored to the start of a line.
    Matching is used to find where each section starts and ends.
    """
    all_patterns = []
    for variants in SECTION_HEADER_PATTERNS.values():
        all_patterns.extend(variants)
    all_patterns.extend(KNOWN_OTHER_HEADERS)

    # Sort longest-first so e.g. "work experience" matches before "experience" alone
    all_patterns.sort(key=len, reverse=True)
    joined = "|".join(all_patterns)

    # ^\s* allows leading whitespace; header text is usually short and on its own line
    return re.compile(rf"^\s*({joined})\s*:?\s*$", re.IGNORECASE | re.MULTILINE)


_HEADER_REGEX = _build_header_regex()


def _which_target_section(header_text: str) -> str | None:
    """Given matched header text, returns which of our 3 target sections it belongs to, if any."""
    header_lower = header_text.strip().lower()
    for section_name, variants in SECTION_HEADER_PATTERNS.items():
        for variant in variants:
            if re.fullmatch(variant, header_lower, re.IGNORECASE):
                return section_name
    return None


def split_into_sections(raw_text: str) -> Dict[str, List[str]]:
    """
    Returns {"education": [...], "experience": [...], "projects": [...]},
    where each list contains non-empty lines found under that header.
    Sections not found in the text come back as an empty list.
    """
    result: Dict[str, List[str]] = {"education": [], "experience": [], "projects": []}

    matches = list(_HEADER_REGEX.finditer(raw_text))
    if not matches:
        return result  # No recognisable headers at all - nothing to extract

    for i, match in enumerate(matches):
        section_name = _which_target_section(match.group(1))
        if section_name is None:
            continue  # It's a header we recognise but don't store (e.g. "Certifications")

        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(raw_text)
        section_text = raw_text[start:end]

        lines = [line.strip() for line in section_text.splitlines()]
        lines = [line for line in lines if line]  # drop blank lines
        result[section_name].extend(lines)

    return result
