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
from typing import Any, Callable, Dict, List

import requests

from backend.app.html_text import extract_list_items, strip_html_to_text
from backend.app.job_pdf import _extract_company_name


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

    root = ET.fromstring(response.content)
    job_elements = root.findall(".//job")[:limit]

    normalized = []
    for job_el in job_elements:
        title = (job_el.findtext("title") or "Untitled Role").strip()
        company = (job_el.findtext("company") or "Unknown Company").strip()
        location = (job_el.findtext("location") or "Not specified").strip()
        salary = (job_el.findtext("salary") or "").strip()
        raw_description = job_el.findtext("description") or ""

        normalized.append(
            {
                "title": title,
                "company": company,
                "location": location,
                "remote": "remote" in location.lower(),
                "tags": [salary] if salary else [],  # no dedicated tags field in this feed
                "url": "",  # this feed doesn't include a per-job link
                "description": strip_html_to_text(raw_description),
                "responsibilities": extract_list_items(raw_description),
                "source": "devitjobs_uk",
            }
        )
    return normalized


# ---------------------------------------------------------------------------
# Registry - add new sources here once you write their fetch function above
# ---------------------------------------------------------------------------
SOURCE_REGISTRY: Dict[str, Callable[[int], List[Dict[str, Any]]]] = {
    "arbeitnow": fetch_arbeitnow,
    "devitjobs_uk": fetch_devitjobs_uk,
}


def fetch_from_sources(source_names: List[str], limit_per_source: int = 5) -> List[Dict[str, Any]]:
    """
    Fetches from each named source and returns one combined, normalized list.
    Unknown source names are skipped with a warning rather than raising,
    so one typo doesn't break a multi-source request.
    """
    all_jobs: List[Dict[str, Any]] = []

    for name in source_names:
        fetch_fn = SOURCE_REGISTRY.get(name)
        if fetch_fn is None:
            print(f"[fetch_from_sources] Unknown source '{name}' - skipping. "
                  f"Known sources: {list(SOURCE_REGISTRY.keys())}")
            continue

        try:
            jobs = fetch_fn(limit_per_source)
            print(f"[fetch_from_sources] {name}: fetched {len(jobs)} jobs")
            all_jobs.extend(jobs)
        except Exception as exc:
            print(f"[fetch_from_sources] {name}: fetch failed - {exc}")

    return all_jobs