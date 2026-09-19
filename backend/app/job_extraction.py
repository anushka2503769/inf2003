"""Job-description extraction entry point used by manual ingestion."""

from .job_skill_extraction import extract_skills_from_job


def extract_job_fields(raw_jd: str, *, require_database: bool = True) -> dict:
    return extract_skills_from_job(raw_jd, require_database=require_database)
