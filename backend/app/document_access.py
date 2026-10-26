"""Schema-aware helpers for the two current MongoDB document shapes."""

from typing import Any

from pymongo import ReturnDocument
from pymongo.database import Database


def section_items(values: list[Any]) -> list[dict[str, Any]]:
    """Convert the old string extraction shape to the committed object shape."""
    return [value if isinstance(value, dict) else {"text": str(value)} for value in values]


def job_title(document: dict[str, Any]) -> str:
    extracted = document.get("extracted_data", {})
    provider = extracted.get("provider", {}) if isinstance(extracted, dict) else {}
    return str(provider.get("title") or "Untitled Role")


def provider_extracted_data(extracted: dict[str, Any], job: dict[str, Any]) -> dict[str, Any]:
    """Keep provider metadata nested where the strict top-level validator permits it."""
    result = dict(extracted)
    result["provider"] = {
        "source": job.get("source", ""),
        "external_job_id": job.get("external_job_id", ""),
        "title": job.get("title", "Untitled Role"),
        "company_name": job.get("company", "Unknown Company"),
        "application_url": job.get("url", ""),
    }
    return result


def replace_current_resume(db: Database, document: dict[str, Any]) -> dict[str, Any]:
    """Atomically replace the one current resume protected by the unique user index."""
    # One atomic call returns the document this request wrote. A separate find_one after
    # replace_one could return a concurrent upload's document instead.
    stored = db["resume_documents"].find_one_and_replace(
        {"user_id": document["user_id"]},
        document,
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    if stored is None:
        raise RuntimeError("MongoDB did not return the replaced resume document.")
    return stored
