"""
Runs skill extraction over job_documents entries whose raw_jd is a JSON
string (as produced by the fetch-multi endpoint), matching against the
same SQL skills table used for resumes.

Populates extracted_data.requirements[] with one entry per matched skill.
requirement_type defaults to "REQUIRED" for every match - keyword matching
alone can't tell whether a job posting means "must have" vs "nice to have",
so this is a known simplification worth mentioning in your report.
"""

import json
from typing import Any, Dict

from backend.app.role_classifier import classify_industry, classify_profession
from backend.app.skill_matcher import match_skills_with_ids


def _parse_job(raw_jd: str) -> Dict[str, Any]:
    """Parses raw_jd back into a dict if it's JSON; returns {} otherwise (e.g. manually-pasted text)."""
    try:
        parsed = json.loads(raw_jd)
        return parsed if isinstance(parsed, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _get_searchable_text(job: Dict[str, Any], raw_jd: str) -> str:
    """
    Pulls out the fields worth searching for skill keywords; falls back
    to the raw string itself if raw_jd isn't valid JSON (e.g. manually-
    pasted job descriptions from the /api/jobs/ingest endpoint).
    """
    if not job:
        return raw_jd

    parts = [
        job.get("title", ""),
        job.get("description", ""),
        " ".join(job.get("tags", [])),
    ]
    return " ".join(part for part in parts if part)


def extract_skills_from_job(raw_jd: str) -> Dict[str, Any]:
    """
    Returns an extracted_data dict with requirements[] populated from
    matched skills, and responsibilities[] pulled from the job's bullet
    points if available (see job_sources.py's extract_list_items).
    role_category is left as a placeholder - this function's job is
    skills/responsibilities extraction, not role classification.
    """
    job = _parse_job(raw_jd)
    searchable_text = _get_searchable_text(job, raw_jd)
    matches = match_skills_with_ids(searchable_text)

    requirements = [
        {
            "skill_id": skill_id,
            "requirement_type": "REQUIRED",
            "minimum_years": None,
            "evidence": None,
        }
        for skill_id, _name in matches
    ]

    return {
        "role_category": classify_profession(searchable_text),
        "industry": classify_industry(searchable_text),
        "requirements": requirements,
        "responsibilities": job.get("responsibilities", []),
    }