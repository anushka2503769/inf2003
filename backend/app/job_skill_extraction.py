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
import re
from typing import Any, Dict

from .role_classifier import classify_industry, classify_profession
from .skill_matcher import match_skills_with_ids


def _parse_job(raw_jd: str) -> Dict[str, Any]:
    """Parse raw_jd as JSON, returning {} for manually pasted text."""
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


def _evidence(text: str, skill_name: str) -> str:
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", text):
        sentence = sentence.strip()
        if sentence and re.search(re.escape(skill_name), sentence, flags=re.IGNORECASE):
            return sentence
    return ""


def _requirement_type(text: str, skill_name: str) -> str:
    match = re.search(re.escape(skill_name), text, flags=re.IGNORECASE)
    nearby = text[
        max(0, (match.start() if match else 0) - 100) : (match.end() if match else 0) + 100
    ]
    return (
        "PREFERRED"
        if re.search(r"preferred|nice to have|bonus", nearby, flags=re.IGNORECASE)
        else "REQUIRED"
    )


def _minimum_years(text: str, skill_name: str) -> int | None:
    skill = re.escape(skill_name)
    patterns = (
        rf"{skill}[^.\n]{{0,80}}?(\d+)\+?\s+years?",
        rf"(\d+)\+?\s+years?[^.\n]{{0,80}}?{skill}",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return int(match.group(1))
    return None


def extract_skills_from_job(raw_jd: str, *, require_database: bool = False) -> Dict[str, Any]:
    """
    Returns an extracted_data dict with requirements[] populated from
    matched skills, and responsibilities[] pulled from the job's bullet
    points if available (see job_sources.py's extract_list_items).
    role_category is left as a placeholder - this function's job is
    skills/responsibilities extraction, not role classification.
    """
    job = _parse_job(raw_jd)
    searchable_text = _get_searchable_text(job, raw_jd)
    matches = match_skills_with_ids(searchable_text, require_database=require_database)

    requirements = []
    for skill_id, name in matches:
        evidence = _evidence(searchable_text, name)
        if not evidence:
            continue
        requirements.append(
            {
                "skill_id": skill_id,
                "requirement_type": _requirement_type(evidence, name),
                "minimum_years": _minimum_years(evidence, name),
                "evidence": evidence,
            }
        )

    provider = None
    if job:
        provider = {
            "source": str(job.get("source", "")),
            "external_job_id": str(job.get("external_job_id", "")),
            "title": str(job.get("title", "Untitled Role")),
            "company_name": str(job.get("company", job.get("company_name", "Unknown Company"))),
            "application_url": str(job.get("url", job.get("application_url", ""))),
        }

    return {
        "role_category": classify_profession(searchable_text),
        "industry": classify_industry(searchable_text),
        "requirements": requirements,
        "responsibilities": job.get("responsibilities", []),
        "provider": provider,
    }
