"""
Cleans HTML-formatted (and sometimes double-escaped) job description text
into plain, readable text - and extracts bullet-point list items
separately, since those usually correspond to responsibilities.
"""

import html
import re
from typing import List

_TAG_RE = re.compile(r"<[^>]+>")
_LIST_ITEM_RE = re.compile(r"<li[^>]*>(.*?)</li>", re.IGNORECASE | re.DOTALL)
_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
# Closing block-level tags should leave a line break behind, or text from
# adjacent blocks runs together with no separator (e.g. "TitleNext paragraph")
_BLOCK_CLOSE_RE = re.compile(
    r"</(p|div|li|ul|ol|h1|h2|h3|h4|h5|h6)\s*>", re.IGNORECASE
)


def _fully_unescape(raw: str) -> str:
    """
    Some sources (Arbeitnow) double-encode: entities like &lt;div&gt;
    decode into literal "<div>" text rather than a real tag. Unescape
    repeatedly until it stops changing, so both single- and double-
    escaped input end up as real HTML.
    """
    previous = None
    current = raw
    for _ in range(3):  # safety cap - real content never needs more than 2-3 passes
        if current == previous:
            break
        previous = current
        current = html.unescape(current)
    return current


def strip_html_to_text(raw_html: str) -> str:
    """Converts HTML (possibly double-escaped) into clean plain text."""
    if not raw_html:
        return ""

    text = _fully_unescape(raw_html)
    text = _BR_RE.sub("\n", text)
    text = _BLOCK_CLOSE_RE.sub("\n", text)
    text = _TAG_RE.sub("", text)

    # Collapse repeated blank lines/whitespace left behind by removed tags
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_list_items(raw_html: str) -> List[str]:
    """
    Pulls out the text of every <li>...</li> element, cleaned of any
    nested tags. Useful for responsibilities/requirements that are
    formatted as bullet lists in the original posting.
    """
    if not raw_html:
        return []

    text = _fully_unescape(raw_html)
    items = _LIST_ITEM_RE.findall(text)

    cleaned_items = []
    for item in items:
        cleaned = _TAG_RE.sub("", item)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if cleaned:
            cleaned_items.append(cleaned)

    return cleaned_items