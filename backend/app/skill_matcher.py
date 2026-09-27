"""
Matches known skill names against resume text using case-insensitive,
whole-word (or whole-phrase) regex matching.
"""

import re
from typing import List, Tuple

from .skills_repository import get_all_skills


def _build_skill_pattern(skill_name: str) -> re.Pattern:
    """
    Builds a case-insensitive whole-word/phrase regex for a skill name.
    \\b word boundaries stop "Java" from matching inside "JavaScript",
    and re.escape handles skills with special characters like "C++".
    """
    escaped = re.escape(skill_name)
    return re.compile(rf"\b{escaped}\b", re.IGNORECASE)


def match_skills(raw_text: str, *, require_database: bool = True) -> List[str]:
    """
    Returns the names of all known skills found in raw_text.
    Order follows the skills table order; duplicates are not possible
    since each skill is checked once.
    """
    matched_names: List[str] = []
    for _skill_id, name in get_all_skills(require_database=require_database):
        pattern = _build_skill_pattern(name)
        if pattern.search(raw_text):
            matched_names.append(name)
    return matched_names


def match_skills_with_ids(
    raw_text: str, *, require_database: bool = False
) -> List[Tuple[int, str]]:
    """
    Same as match_skills(), but also returns each match's skill_id -
    useful if you want to store the SQL reference alongside the name
    (e.g. for later joining against user_skills).
    """
    matches: List[Tuple[int, str]] = []
    for skill_id, name in get_all_skills(require_database=require_database):
        pattern = _build_skill_pattern(name)
        if pattern.search(raw_text):
            matches.append((skill_id, name))
    return matches
