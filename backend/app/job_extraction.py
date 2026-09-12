"""
Placeholder for real job-description parsing logic.

`extract_job_fields()` returns the shape required by the job_documents
validator (role_category, requirements[], responsibilities[]) so inserts
succeed even before the real classification logic is built. Wire this up
to whatever skill-matching / keyword approach the team lands on later -
requirements[].skill_id should reference Jason's SQL skills table.
"""


def extract_job_fields(raw_jd: str) -> dict:
    return {
        "role_category": "Unclassified",
        "requirements": [],
        "responsibilities": [],
    }