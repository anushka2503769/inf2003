"""
Registry of job sources. Each source function fetches from its own API
and returns a list of jobs already normalized into a common shape:

    {
        "title": str,
        "company": str,
        "location": str,
        "remote": bool,
        "tags": list[str],
        "url": str,
        "description": str,
        "source": str,   # which API it came from, e.g. "arbeitnow"
    }

Adding a new source later = write one function matching this shape,
then register it in SOURCE_REGISTRY at the bottom of this file.
"""

import time
import xml.etree.ElementTree as ET

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

    normalized = []
    for job in raw_jobs:
        raw_description = job.get("description", "")
        normalized.append(
            {
                "title": job.get("title", "Untitled Role"),
                "company": _extract_company_name(job),
                "location": job.get("location", "Not specified"),
                "remote": bool(job.get("remote", False)),
                "tags": job.get("tags", []),
                "url": job.get("url", ""),
                "description": strip_html_to_text(raw_description),
                "responsibilities": extract_list_items(raw_description),
                "source": "arbeitnow",
                "external_job_id": job.get("id") or job.get("slug"),
            }
        )
    return normalized


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

    normalized = []
    for job_el in job_elements:
        title = (job_el.findtext("title") or "Untitled Role").strip()
        company = (job_el.findtext("company") or "Unknown Company").strip()
        location = (job_el.findtext("location") or "Not specified").strip()
        external_id = (job_el.findtext("id") or job_el.findtext("job_id") or "").strip()
        application_url = (job_el.findtext("url") or job_el.findtext("link") or "").strip()
        salary = (job_el.findtext("salary") or "").strip()
        raw_description = job_el.findtext("description") or ""

        normalized.append(
            {
                "title": title,
                "company": company,
                "location": location,
                "remote": "remote" in location.lower(),
                "tags": [salary] if salary else [],  # no dedicated tags field in this feed
                "url": application_url,
                "description": strip_html_to_text(raw_description),
                "responsibilities": extract_list_items(raw_description),
                "source": "devitjobs_uk",
                "external_job_id": external_id,
            }
        )
    return normalized


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

    normalized = []
    for job in raw_jobs:
        raw_description = job.get("description", "")
        normalized.append(
            {
                "title": job.get("title", "Untitled Role"),
                "company": job.get("company_name", "Unknown Company"),
                "location": job.get("location", "Not specified"),
                "remote": job.get("workplace") == "remote",
                "tags": job.get("tags", []),
                "url": job.get("url", "") or job.get("apply_url", ""),
                "description": strip_html_to_text(raw_description) if raw_description else "",
                "responsibilities": extract_list_items(raw_description) if raw_description else [],
                "source": "ai_dev_jobs",
                "external_job_id": job.get("id") or job.get("job_id") or job.get("job_uid"),
            }
        )
    return normalized


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
