"""Small SQL boundary for cross-store parent checks and job synchronization."""

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Any, Iterable
from urllib.parse import urlparse
from uuid import UUID

import psycopg2

from .sql_db import get_pg_connection


class SqlAccessError(RuntimeError):
    """SQL is unavailable or rejected a cross-store operation."""


class SqlParentMissing(SqlAccessError):
    """The Mongo document's SQL parent does not exist."""


_JOB_PIPELINE_LOCK_KEY = 2003001


@contextmanager
def job_pipeline_lock() -> Iterator[None]:
    """Serialize job reads and cross-store writes with a transaction lock."""
    try:
        conn = get_pg_connection()
    except (RuntimeError, psycopg2.Error) as exc:
        raise SqlAccessError("SQL job synchronization is unavailable.") from exc
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_xact_lock(%s)", (_JOB_PIPELINE_LOCK_KEY,))
            acquired = cursor.fetchone()
            if not acquired or not acquired[0]:
                raise SqlAccessError("SQL job synchronization is busy; retry shortly.")
        yield
    except psycopg2.Error as exc:
        raise SqlAccessError("SQL job synchronization is unavailable.") from exc
    finally:
        try:
            conn.rollback()
        finally:
            conn.close()


def _run_parent_check(query: str, value: str, label: str) -> None:
    try:
        UUID(value)
        conn = get_pg_connection()
    except (ValueError, RuntimeError, psycopg2.Error) as exc:
        raise SqlAccessError(f"SQL {label} validation is unavailable.") from exc
    try:
        with conn.cursor() as cursor:
            cursor.execute(query, (value,))
            if cursor.fetchone() is None:
                raise SqlParentMissing(f"SQL {label} does not exist.")
    except SqlParentMissing:
        raise
    except psycopg2.Error as exc:
        raise SqlAccessError(f"SQL {label} validation failed.") from exc
    finally:
        conn.close()


def ensure_sql_user_exists(user_id: str) -> None:
    _run_parent_check("SELECT 1 FROM public.users WHERE user_id = %s", user_id, "user")


def ensure_sql_job_exists(job_id: str) -> None:
    _run_parent_check("SELECT 1 FROM public.jobs WHERE job_id = %s", job_id, "job")


def get_active_job_ids() -> set[str]:
    """Return active SQL job IDs while the caller holds the pipeline lock."""
    try:
        conn = get_pg_connection()
    except (RuntimeError, psycopg2.Error) as exc:
        raise SqlAccessError("SQL job state lookup is unavailable.") from exc
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT job_id FROM public.jobs WHERE is_active = true")
            return {str(row[0]) for row in cursor.fetchall()}
    except psycopg2.Error as exc:
        raise SqlAccessError("SQL job state lookup is unavailable.") from exc
    finally:
        conn.close()


def _job_uuid(job_id: str) -> UUID:
    try:
        return UUID(str(job_id))
    except (TypeError, ValueError) as exc:
        raise SqlAccessError("The job reference must be a valid UUID.") from exc


def _valid_url(value: Any) -> bool:
    parsed = urlparse(str(value))
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def upsert_provider_job(job: Mapping[str, Any], extracted: Mapping[str, Any]) -> UUID:
    source = job.get("source")
    external_id = job.get("external_job_id")
    title = job.get("title")
    company = job.get("company")
    application_url = job.get("url")
    if not isinstance(source, str) or not source.strip():
        raise SqlAccessError("Provider job is missing a valid source.")
    if (
        external_id is None
        or isinstance(external_id, bool)
        or not isinstance(external_id, (str, int))
    ):
        raise SqlAccessError("Provider job is missing a stable external job ID.")
    if (
        not isinstance(title, str)
        or not title.strip()
        or not isinstance(company, str)
        or not company.strip()
    ):
        raise SqlAccessError("Provider job is missing title or company.")
    if not isinstance(application_url, str) or not _valid_url(application_url):
        raise SqlAccessError("Provider job is missing a stable identity or valid application URL.")
    source = source.strip()
    external_id = str(external_id).strip()
    title = title.strip()
    company = company.strip()
    application_url = application_url.strip()
    if not external_id:
        raise SqlAccessError("Provider job is missing a stable external job ID.")

    try:
        conn = get_pg_connection()
    except (RuntimeError, psycopg2.Error) as exc:
        raise SqlAccessError("SQL job storage is unavailable.") from exc
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO public.jobs
                    (source, external_job_id, title, company_name, location,
                     application_url, last_seen_at, is_active)
                VALUES (%s, %s, %s, %s, %s, %s, now(), false)
                ON CONFLICT (source, external_job_id) DO UPDATE SET
                    title = EXCLUDED.title,
                    company_name = EXCLUDED.company_name,
                    location = EXCLUDED.location,
                    application_url = EXCLUDED.application_url,
                    last_seen_at = now(),
                    is_active = false
                RETURNING job_id
                """,
                (source, external_id, title, company, job.get("location"), application_url),
            )
            row = cursor.fetchone()
            if row is None:
                raise SqlAccessError("SQL job upsert did not return a job id.")
            job_id = row[0]
            _replace_job_skills(cursor, job_id, extracted.get("requirements", []))
        conn.commit()
        return job_id
    except SqlAccessError:
        conn.rollback()
        raise
    except psycopg2.Error as exc:
        conn.rollback()
        raise SqlAccessError("SQL job upsert failed; no fetched job is confirmed.") from exc
    finally:
        conn.close()


def _replace_job_skills(
    cursor: Any, job_id: Any, requirements: Iterable[Mapping[str, Any]]
) -> None:
    """Replace links as one unit so re-extraction removes stale skills."""
    normalized: list[tuple[int, str]] = []
    for requirement in requirements:
        evidence = str(requirement.get("evidence", "")).strip()
        requirement_type = str(requirement.get("requirement_type", "")).strip().upper()
        try:
            skill_id = int(requirement["skill_id"])
        except (KeyError, TypeError, ValueError) as exc:
            raise SqlAccessError(
                "Extracted job skills must reference canonical skill IDs."
            ) from exc
        if skill_id < 1 or not evidence or requirement_type not in {"REQUIRED", "PREFERRED"}:
            raise SqlAccessError(
                "Extracted job skills contain invalid evidence or requirement type."
            )
        normalized.append((skill_id, requirement_type))

    cursor.execute("DELETE FROM public.job_skills WHERE job_id = %s", (job_id,))
    for skill_id, requirement_type in normalized:
        cursor.execute(
            """
            INSERT INTO public.job_skills (job_id, skill_id, requirement_type)
            VALUES (%s, %s, %s)
            ON CONFLICT (job_id, skill_id) DO UPDATE
                SET requirement_type = EXCLUDED.requirement_type
            """,
            (job_id, skill_id, requirement_type),
        )


def replace_job_skills(job_id: str, requirements: Iterable[Mapping[str, Any]]) -> None:
    """Synchronize canonical SQL links for an already-existing job."""
    parsed_job_id = _job_uuid(job_id)
    try:
        conn = get_pg_connection()
    except (RuntimeError, psycopg2.Error) as exc:
        raise SqlAccessError("SQL job storage is unavailable.") from exc
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT 1 FROM public.jobs WHERE job_id = %s", (str(parsed_job_id),))
            if cursor.fetchone() is None:
                raise SqlParentMissing("SQL job does not exist.")
            _replace_job_skills(cursor, str(parsed_job_id), requirements)
        conn.commit()
    except SqlAccessError:
        conn.rollback()
        raise
    except psycopg2.Error as exc:
        conn.rollback()
        raise SqlAccessError("SQL job skill synchronization failed.") from exc
    finally:
        conn.close()


def get_job_active_state(job_id: str) -> bool | None:
    """Return the previous active state, or ``None`` for a new SQL parent."""
    parsed_job_id = _job_uuid(job_id)
    try:
        conn = get_pg_connection()
    except (RuntimeError, psycopg2.Error) as exc:
        raise SqlAccessError("SQL job storage is unavailable.") from exc
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT is_active FROM public.jobs WHERE job_id = %s", (str(parsed_job_id),)
            )
            row = cursor.fetchone()
            return None if row is None else bool(row[0])
    except psycopg2.Error as exc:
        raise SqlAccessError("SQL job state lookup failed.") from exc
    finally:
        conn.close()


def set_job_active(job_id: str, is_active: bool) -> None:
    """Set readiness only after the corresponding Mongo document is durable."""
    parsed_job_id = _job_uuid(job_id)
    try:
        conn = get_pg_connection()
    except (RuntimeError, psycopg2.Error) as exc:
        raise SqlAccessError("SQL job storage is unavailable.") from exc
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "UPDATE public.jobs SET is_active = %s, last_seen_at = now() WHERE job_id = %s",
                (is_active, str(parsed_job_id)),
            )
            if cursor.rowcount != 1:
                raise SqlParentMissing("SQL job does not exist.")
        conn.commit()
    except SqlAccessError:
        conn.rollback()
        raise
    except psycopg2.Error as exc:
        conn.rollback()
        raise SqlAccessError("SQL job readiness update failed.") from exc
    finally:
        conn.close()
