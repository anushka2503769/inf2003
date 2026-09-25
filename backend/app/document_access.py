"""Schema-aware helpers for the two current MongoDB document shapes."""

from typing import Any

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
    collection = db["resume_documents"]
    result = collection.replace_one({"user_id": document["user_id"]}, document, upsert=True)
    if result.upserted_id is not None:
        document = dict(document)
        document["_id"] = result.upserted_id
        return document
    stored = collection.find_one({"user_id": document["user_id"]})
    if stored is None:
        raise RuntimeError("MongoDB did not return the replaced resume document.")
    return stored
