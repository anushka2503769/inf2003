"""
Registry of job sources. Each source function fetches from its own API
and returns a list of jobs already normalized into a common shape:

    {
        "title": str,
        "company": str,
        "location": str | None,          # None when the provider gives none
        "remote": bool,
        "job_type": str | None,          # INTERNSHIP / FULL_TIME / PART_TIME
        "work_arrangement": str | None,  # REMOTE / HYBRID / ONSITE
        "source_posted_at": str | None,  # ISO 8601 timestamp, UTC
        "tags": list[str],
        "url": str,
        "description": str,
        "source": str,   # which API it came from, e.g. "arbeitnow"
    }

Adding a new source later = write one function matching this shape,
then register it in SOURCE_REGISTRY at the bottom of this file.
"""

import json
import re
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

try:
    from lxml import etree as lxml_etree

    _LXML_AVAILABLE = True
except ImportError:
    _LXML_AVAILABLE = False
from typing import Any, Callable, Dict, List

import requests

from .html_text import extract_list_items, strip_html_to_text
from .job_pdf import _extract_company_name

# ---------------------------------------------------------------------------
# Shared field inference (job_type, work_arrangement, location, posted date)
# ---------------------------------------------------------------------------
_INTERN_RE = re.compile(r"\b(intern|interns|internship|internships|praktik\w*)\b", re.IGNORECASE)
_PART_TIME_RE = re.compile(r"\bpart[\s_-]?time\b", re.IGNORECASE)
_FULL_TIME_RE = re.compile(r"\bfull[\s_-]?time\b", re.IGNORECASE)
_HYBRID_RE = re.compile(r"\bhybrid\b", re.IGNORECASE)
_REMOTE_RE = re.compile(r"\bremote(ly)?\b", re.IGNORECASE)
_ONSITE_RE = re.compile(r"\b(on[\s_-]?site|in[\s_-]office)\b", re.IGNORECASE)
_NO_LOCATION = {"", "not specified", "n/a", "none", "null"}


def clean_location(value: Any) -> str | None:
    """Trim a provider location; absent or placeholder values become None."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    return None if text.lower() in _NO_LOCATION else text


def infer_job_type(title: Any, *type_hints: Any) -> str | None:
    """INTERNSHIP if the title or stated type mentions intern, else FULL/PART_TIME, else None."""
    hints = [h for h in type_hints if isinstance(h, str)]
    for hint in type_hints:
        if isinstance(hint, (list, tuple)):
            hints.extend(h for h in hint if isinstance(h, str))
    text_title = title if isinstance(title, str) else ""
    if _INTERN_RE.search(text_title) or any(_INTERN_RE.search(h) for h in hints):
        return "INTERNSHIP"
    joined = " ".join(hints)
    if _PART_TIME_RE.search(joined):
        return "PART_TIME"
    if _FULL_TIME_RE.search(joined):
        return "FULL_TIME"
    return None


def infer_work_arrangement(
    *texts: Any, remote_flag: bool = False, remote_wording: bool = False
) -> str | None:
    """
    REMOTE when the provider flags it (or, with remote_wording, the text says remote),
    HYBRID when "hybrid" appears, ONSITE only when stated, else None.
    Texts are tried in order, so a more specific field (location) beats a long description.
    """
    if remote_flag:
        return "REMOTE"
    for text in texts:
        if not isinstance(text, str):
            continue
        if _HYBRID_RE.search(text):
            return "HYBRID"
        if remote_wording and _REMOTE_RE.search(text):
            return "REMOTE"
        if _ONSITE_RE.search(text):
            return "ONSITE"
    return None


def parse_posted_at(value: Any) -> str | None:
    """Epoch seconds/ms, ISO date/datetime or RFC 2822 text to a UTC ISO string, else None."""
    parsed: datetime | None = None
    try:
        if isinstance(value, bool) or value is None:
            return None
        if isinstance(value, (int, float)):
            seconds = value / 1000 if value > 1e11 else value
            parsed = datetime.fromtimestamp(seconds, tz=timezone.utc)
        elif isinstance(value, str) and value.strip():
            text = value.strip()
            try:
                parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            except ValueError:
                parsed = parsedate_to_datetime(text)
        elif isinstance(value, datetime):
            parsed = value
        elif isinstance(value, date):
            parsed = datetime(value.year, value.month, value.day)
    except (ValueError, TypeError, OverflowError, OSError):
        return None
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def _safe(normalizer: Callable[[Any], Dict[str, Any]], raw: Any, source: str) -> Dict[str, Any]:
    """Normalize one record; an unreadable one becomes a stub so it is rejected alone."""
    try:
        return normalizer(raw)
    except Exception:
        return _stub(source)


def _stub(source: str) -> Dict[str, Any]:
    """Placeholder for an unreadable provider record; it fails validation and is rejected."""
    return {"source": source, "external_job_id": None}


# ---------------------------------------------------------------------------
# Arbeitnow (REST, JSON, no API key) - https://arbeitnow.com/api/job-board-api
# ---------------------------------------------------------------------------
ARBEITNOW_API_URL = "https://arbeitnow.com/api/job-board-api"


def fetch_arbeitnow(limit: int = 5) -> List[Dict[str, Any]]:
    """
    Arbeitnow paginates results (one page per request), so pulling more
    than a single page's worth requires looping through pages - same
    logic as the original scraping script, just capped at `limit` jobs.
    """
    headers = {"User-Agent": "Mozilla/5.0 (compatible; jobless-simulator/1.0)"}
    collected: List[Dict[str, Any]] = []
    page = 1
    max_pages = 20  # safety cap so a bug can't loop forever

    while len(collected) < limit and page <= max_pages:
        response = requests.get(
            ARBEITNOW_API_URL, params={"page": page}, headers=headers, timeout=10
        )
        response.raise_for_status()
        data = response.json()

        raw_jobs = data.get("data", [])
        if not raw_jobs:
            break  # no more jobs available

        collected.extend(raw_jobs)

        links = data.get("links", {})
        if not links.get("next"):
            break  # reached the last page

        page += 1
        time.sleep(0.5)  # be polite to the server, same as the original script

    raw_jobs = collected[:limit]

    return [_safe(normalize_arbeitnow_job, job, "arbeitnow") for job in raw_jobs]


def normalize_arbeitnow_job(job: Dict[str, Any]) -> Dict[str, Any]:
    raw_description = job.get("description", "")
    title = job.get("title", "Untitled Role")
    location = clean_location(job.get("location"))
    job_types = job.get("job_types")
    remote = bool(job.get("remote", False))
    description = strip_html_to_text(raw_description)
    return {
        "title": title,
        "company": _extract_company_name(job),
        "location": location,
        "remote": remote,
        "job_type": infer_job_type(title, job_types),
        "work_arrangement": infer_work_arrangement(
            title, location, description, remote_flag=remote
        ),
        "source_posted_at": parse_posted_at(job.get("created_at")),
        "tags": job.get("tags", []),
        "url": job.get("url", ""),
        "description": description,
        "responsibilities": extract_list_items(raw_description),
        "source": "arbeitnow",
        "external_job_id": job.get("id") or job.get("slug"),
    }


# ---------------------------------------------------------------------------
# DevITjobs UK (XML feed, no API key) - https://devitjobs.uk/job_feed.xml
# ---------------------------------------------------------------------------
DEVITJOBS_UK_FEED_URL = "https://devitjobs.uk/job_feed.xml"


def fetch_devitjobs_uk(limit: int = 5) -> List[Dict[str, Any]]:
    headers = {"User-Agent": "Mozilla/5.0 (compatible; jobless-simulator/1.0)"}
    response = requests.get(DEVITJOBS_UK_FEED_URL, headers=headers, timeout=10)
    response.raise_for_status()

    if _LXML_AVAILABLE:
        # lxml's recover=True tolerates malformed XML (unescaped &, bad
        # control chars, etc.) that this feed sometimes contains, instead
        # of failing the whole fetch on one bad character.
        parser = lxml_etree.XMLParser(recover=True)
        root = lxml_etree.fromstring(response.content, parser=parser)
    else:
        # Fallback: standard library, which will raise ParseError on
        # malformed XML. Install lxml (uv add lxml) for more resilient parsing.
        root = ET.fromstring(response.content)
    job_elements = root.findall(".//job")[:limit]
    return [_safe(normalize_devitjobs_uk_job, job_el, "devitjobs_uk") for job_el in job_elements]


def _first_text(element: Any, *names: str) -> str:
    for name in names:
        value = (element.findtext(name) or "").strip()
        if value:
            return value
    return ""


def normalize_devitjobs_uk_job(job_el: Any) -> Dict[str, Any]:
    # The feed's date/type element names are not documented; the usual candidates
    # are tried and anything not found simply stays null.
    title = (job_el.findtext("title") or "Untitled Role").strip()
    company = (job_el.findtext("company") or "Unknown Company").strip()
    location = clean_location(job_el.findtext("location"))
    external_id = (job_el.findtext("id") or job_el.findtext("job_id") or "").strip()
    application_url = (job_el.findtext("url") or job_el.findtext("link") or "").strip()
    salary = (job_el.findtext("salary") or "").strip()
    raw_description = job_el.findtext("description") or ""
    description = strip_html_to_text(raw_description)
    workplace = _first_text(job_el, "workplace", "work_arrangement", "remote")
    remote = "remote" in (location or "").lower() or workplace.lower() in {
        "remote",
        "true",
        "yes",
        "1",
    }
    job_type_text = _first_text(job_el, "jobtype", "job_type", "employment_type", "type")
    return {
        "title": title,
        "company": company,
        "location": location,
        "remote": remote,
        "job_type": infer_job_type(title, job_type_text),
        "work_arrangement": infer_work_arrangement(
            workplace, title, location, description, remote_flag=remote
        ),
        "source_posted_at": parse_posted_at(
            _first_text(job_el, "pubdate", "published", "date", "posted", "created_at")
        ),
        "tags": [salary] if salary else [],  # no dedicated tags field in this feed
        "url": application_url,
        "description": description,
        "responsibilities": extract_list_items(raw_description),
        "source": "devitjobs_uk",
        "external_job_id": external_id,
    }


# ---------------------------------------------------------------------------
# AI Dev Jobs (REST, JSON, no API key for read access) - https://aidevboard.com/docs
# NOTE: docs confirm the endpoint, params, and pagination (page/limit, max 50),
# but do not show an example response body for GET /jobs itself - only for
# /jobs/match. This function defensively checks a few likely envelope shapes
# ("jobs" key, "data" key, or a bare list) since the exact key name wasn't
# confirmed in the documentation fetched. If this returns 0 jobs in practice,
# check the real response shape and adjust the _unwrap_jobs_response function.
# ---------------------------------------------------------------------------
AI_DEV_JOBS_API_URL = "https://aidevboard.com/api/v1/jobs"


def _unwrap_jobs_response(data: Any) -> List[Dict[str, Any]]:
    """Handles a few plausible response envelope shapes defensively."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("jobs", "data", "results", "items"):
            if isinstance(data.get(key), list):
                return data[key]
    return []


def fetch_ai_dev_jobs(limit: int = 5) -> List[Dict[str, Any]]:
    headers = {"User-Agent": "Mozilla/5.0 (compatible; jobless-simulator/1.0)"}
    collected: List[Dict[str, Any]] = []
    page = 1
    page_size = 50  # API's documented max per page
    max_pages = 20  # safety cap

    while len(collected) < limit and page <= max_pages:
        response = requests.get(
            AI_DEV_JOBS_API_URL,
            params={"page": page, "limit": page_size},
            headers=headers,
            timeout=10,
        )
        response.raise_for_status()
        jobs_page = _unwrap_jobs_response(response.json())

        if not jobs_page:
            break  # no more results, or unexpected response shape

        collected.extend(jobs_page)
        page += 1
        time.sleep(0.3)  # respect the documented hourly rate limit

    raw_jobs = collected[:limit]

    return [_safe(normalize_ai_dev_job, job, "ai_dev_jobs") for job in raw_jobs]


def normalize_ai_dev_job(job: Dict[str, Any]) -> Dict[str, Any]:
    # The response body is only partly documented, so the date and type field names
    # below are the likely candidates; missing ones leave the value null.
    raw_description = job.get("description", "")
    description = strip_html_to_text(raw_description) if raw_description else ""
    title = job.get("title", "Untitled Role")
    location = clean_location(job.get("location"))
    workplace = job.get("workplace")
    workplace_text = workplace if isinstance(workplace, str) else ""
    remote = workplace_text.lower() == "remote"
    posted = next(
        (
            job[key]
            for key in ("posted_at", "published_at", "date_posted", "created_at")
            if job.get(key)
        ),
        None,
    )
    return {
        "title": title,
        "company": job.get("company_name", "Unknown Company"),
        "location": location,
        "remote": remote,
        "job_type": infer_job_type(
            title, job.get("job_type"), job.get("employment_type"), job.get("type")
        ),
        "work_arrangement": infer_work_arrangement(
            workplace_text, title, location, description, remote_flag=remote
        ),
        "source_posted_at": parse_posted_at(posted),
        "tags": job.get("tags", []),
        "url": job.get("url", "") or job.get("apply_url", ""),
        "description": description,
        "responsibilities": extract_list_items(raw_description) if raw_description else [],
        "source": "ai_dev_jobs",
        "external_job_id": job.get("id") or job.get("job_id") or job.get("job_uid"),
    }


# ---------------------------------------------------------------------------
# LinkedIn via Apify (file import, no network) - written by scripts/fetch_linkedin_apify.py
# ---------------------------------------------------------------------------
LINKEDIN_APIFY_SOURCE = "linkedin_apify"


def _clean_text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _linkedin_posted_at(value: Any) -> str | None:
    """postedAt is a date; keep the date part and store it as midnight UTC."""
    text = _clean_text(value)
    match = re.match(r"\d{4}-\d{2}-\d{2}", text)
    return parse_posted_at(match.group(0)) if match else parse_posted_at(value)


def normalize_linkedin_apify_job(job: Dict[str, Any]) -> Dict[str, Any]:
    """Map one job from the Apify export to the shared provider shape."""
    external_id = job.get("id")
    external_id = None if isinstance(external_id, bool) else external_id
    apply_url = _clean_text(job.get("applyUrl"))
    page_url = _clean_text(job.get("url"))
    application_url = apply_url if apply_url.startswith(("http://", "https://")) else page_url
    title = _clean_text(job.get("title"))
    location = clean_location(job.get("location"))
    description = _clean_text(job.get("descriptionText"))
    employment_type = _clean_text(job.get("employmentType"))
    if employment_type.lower() == "internship":
        job_type: str | None = "INTERNSHIP"
    else:
        # Contract, Temporary and anything else unstated map to null.
        job_type = infer_job_type(title, employment_type)
    work_arrangement = infer_work_arrangement(location, description, remote_wording=True)
    industries = job.get("industries")
    if isinstance(industries, list):
        industries = ", ".join(str(item).strip() for item in industries if str(item).strip())
    industry = _clean_text(industries)
    html = job.get("descriptionHtml")
    return {
        "title": title,
        "company": _clean_text(job.get("companyName")),
        "location": location,
        "remote": work_arrangement == "REMOTE",
        "job_type": job_type,
        "work_arrangement": work_arrangement,
        "source_posted_at": _linkedin_posted_at(job.get("postedAt")),
        "tags": [],
        "url": application_url,
        "description": description,
        "responsibilities": extract_list_items(html) if isinstance(html, str) else [],
        "source": LINKEDIN_APIFY_SOURCE,
        "external_job_id": external_id,
        "raw_jd": description,
        "industry": industry or None,
    }


def load_linkedin_apify_file(path: str | Path) -> tuple[List[Dict[str, Any]], List[str]]:
    """
    Read an export written by scripts/fetch_linkedin_apify.py. Returns the valid
    normalized jobs and one short error per rejected record. Makes no network call.
    """
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ProviderJobError("The LinkedIn export file cannot be read as JSON.") from exc
    if not isinstance(document, dict) or not isinstance(document.get("jobs"), list):
        raise ProviderJobError("The file is not a LinkedIn Apify export (no jobs list).")
    if document.get("source") not in (None, LINKEDIN_APIFY_SOURCE):
        raise ProviderJobError("The file was not produced for the linkedin_apify source.")
    return validate_provider_jobs(
        [
            _safe(normalize_linkedin_apify_job, raw, LINKEDIN_APIFY_SOURCE)
            for raw in document["jobs"]
        ]
    )


# ---------------------------------------------------------------------------
# Registry - add new sources here once you write their fetch function above
# ---------------------------------------------------------------------------
SOURCE_REGISTRY: Dict[str, Callable[[int], List[Dict[str, Any]]]] = {
    "arbeitnow": fetch_arbeitnow,
    "devitjobs_uk": fetch_devitjobs_uk,
    "ai_dev_jobs": fetch_ai_dev_jobs,
}


class ProviderJobError(ValueError):
    """A provider record cannot be safely persisted without stable identity."""


def normalize_provider_job(job: Dict[str, Any]) -> Dict[str, Any]:
    """Validate the shared provider shape without inventing an identity."""
    normalized = dict(job)
    source = normalized.get("source")
    external_id = normalized.get("external_job_id")
    title = normalized.get("title")
    company = normalized.get("company")
    application_url = normalized.get("url")
    if not isinstance(source, str) or not source.strip():
        raise ProviderJobError("Provider job is missing a valid source.")
    if (
        external_id is None
        or isinstance(external_id, bool)
        or not isinstance(external_id, (str, int))
    ):
        raise ProviderJobError("Provider job is missing a stable external job ID.")
    if (
        not isinstance(title, str)
        or not title.strip()
        or not isinstance(company, str)
        or not company.strip()
    ):
        raise ProviderJobError("Provider job is missing title or company.")
    if not isinstance(application_url, str) or not application_url.strip().startswith(
        ("http://", "https://")
    ):
        raise ProviderJobError("Provider job is missing a valid application URL.")
    normalized["source"] = source.strip()
    normalized["external_job_id"] = str(external_id).strip()
    if not normalized["external_job_id"]:
        raise ProviderJobError("Provider job is missing a stable external job ID.")
    normalized["url"] = application_url.strip()
    return normalized


def fetch_from_sources(source_names: List[str], limit_per_source: int = 5) -> List[Dict[str, Any]]:
    """
    Fetches from each named source and returns one combined, normalized list.
    Unknown source names and malformed provider records fail clearly. A record
    with no stable ID is never assigned an ID derived from its title.
    """
    all_jobs: List[Dict[str, Any]] = []

    for name in source_names:
        fetch_fn = SOURCE_REGISTRY.get(name)
        if fetch_fn is None:
            raise ProviderJobError(f"Unknown job source '{name}'.")

        try:
            jobs = fetch_fn(limit_per_source)
            print(f"[fetch_from_sources] {name}: fetched {len(jobs)} jobs")
            all_jobs.extend(normalize_provider_job(job) for job in jobs)
        except ProviderJobError:
            raise
        except requests.RequestException as exc:
            raise ProviderJobError(f"Job source '{name}' is unavailable.") from exc

    return all_jobs


def validate_provider_jobs(jobs: List[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], List[str]]:
    """Validate each record on its own; return the valid ones and one error per bad one."""
    valid: List[Dict[str, Any]] = []
    errors: List[str] = []
    for job in jobs:
        try:
            valid.append(normalize_provider_job(job))
        except ProviderJobError as exc:
            source = job.get("source") if isinstance(job.get("source"), str) else "unknown"
            ident = job.get("external_job_id")
            has_id = isinstance(ident, (str, int)) and str(ident).strip()
            label = f"{source}/{str(ident).strip()[:40]}" if has_id else source
            errors.append(f"{label}: {exc}")
    return valid, errors


def collect_provider_jobs(
    source_names: List[str], limit_per_source: int = 5
) -> tuple[List[Dict[str, Any]], List[str]]:
    """
    Like fetch_from_sources, but a malformed record is reported and skipped instead
    of aborting the fetch. Unknown sources and unavailable providers still raise.
    """
    all_jobs: List[Dict[str, Any]] = []
    for name in source_names:
        fetch_fn = SOURCE_REGISTRY.get(name)
        if fetch_fn is None:
            raise ProviderJobError(f"Unknown job source '{name}'.")
        try:
            jobs = fetch_fn(limit_per_source)
        except requests.RequestException as exc:
            raise ProviderJobError(f"Job source '{name}' is unavailable.") from exc
        print(f"[collect_provider_jobs] {name}: fetched {len(jobs)} jobs")
        all_jobs.extend(jobs)
    return validate_provider_jobs(all_jobs)
