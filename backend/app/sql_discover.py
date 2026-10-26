"""SQL for the Discover feed (docs/API.md section 7).

Same idiom as sql_skills.py and sql_profile.py: one call opens one connection,
runs on one cursor inside one (read-only) transaction and closes in a finally
block. psycopg2 errors become SqlAccessError, which errors.py maps to 503.

The feed is one statement, DISCOVER_SQL, written to be read (and quoted in the
report): CTE candidate filters active jobs and anti-joins the caller's tracker
rows, CTE req counts REQUIRED/PREFERRED skills and how many the caller has,
CTE ranked computes coverage and RANK() and cuts the page, and the outer
SELECT builds the matched/missing skill lists for that page only.

Optional filters are written as "(param IS NULL OR condition)". psycopg2
interpolates parameters client-side, so the server sees a constant NULL and
folds the whole disjunction away; a set filter stays a plain predicate the
partial indexes from migration 003 can serve.
"""

from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

import psycopg2
from psycopg2.extensions import connection as PGConnection

from .schemas import DiscoverItem, DiscoverResponse, JobMatch, JobSummary, SkillRequirement
from .sql_access import SqlAccessError
from .sql_db import get_pg_connection
from .sql_skills import _like_pattern

LIMIT_DEFAULT = 20
LIMIT_MAX = 50
OFFSET_MAX = 10_000
TEXT_FILTER_MAX_LENGTH = 100

_UNAVAILABLE = "Discover is unavailable."

# A raw string so the backslash in ESCAPE '\' reaches PostgreSQL as written and
# the statement can be pasted into psql unchanged (with the %(name)s values
# substituted). No literal percent sign may appear: psycopg2 would read it as
# a placeholder.
DISCOVER_SQL = r"""
WITH candidate AS (
    -- Active jobs passing the optional filters, minus every job the caller
    -- already has a tracker row for (any status).
    SELECT j.job_id, j.title, j.company_name, j.location, j.job_type,
           j.work_arrangement, j.application_url, j.source,
           j.source_posted_at, j.is_active
      FROM public.jobs AS j
     WHERE j.is_active
       AND (%(job_type)s::text IS NULL OR j.job_type = %(job_type)s)
       AND (%(work_arrangement)s::text IS NULL
            OR j.work_arrangement = %(work_arrangement)s)
       AND (%(location)s::text IS NULL
            OR j.location ILIKE %(location)s ESCAPE '\')
       AND (%(q)s::text IS NULL
            OR j.title ILIKE %(q)s ESCAPE '\'
            OR j.company_name ILIKE %(q)s ESCAPE '\')
       AND NOT EXISTS (                                    -- anti-join
               SELECT 1
                 FROM public.user_jobs AS uj
                WHERE uj.user_id = %(user_id)s
                  AND uj.job_id = j.job_id)
),
req AS (
    -- Per candidate: requirements listed and how many the caller has. The
    -- LEFT JOINs keep a job with no job_skills rows (all counts 0) and leave
    -- us.skill_id NULL for a skill the caller lacks.
    SELECT c.job_id,
           COUNT(*) FILTER (WHERE js.requirement_type = 'REQUIRED')   AS required_total,
           COUNT(*) FILTER (WHERE js.requirement_type = 'REQUIRED'
                              AND us.skill_id IS NOT NULL)          AS required_matched,
           COUNT(*) FILTER (WHERE js.requirement_type = 'PREFERRED')  AS preferred_total,
           COUNT(*) FILTER (WHERE js.requirement_type = 'PREFERRED'
                              AND us.skill_id IS NOT NULL)          AS preferred_matched
      FROM candidate AS c
      LEFT JOIN public.job_skills AS js ON js.job_id = c.job_id
      LEFT JOIN public.user_skills AS us
             ON us.skill_id = js.skill_id AND us.user_id = %(user_id)s
     GROUP BY c.job_id
),
ranked AS (
    -- coverage is NULL when a job lists no REQUIRED skill, so NULLS LAST puts
    -- it after every scored job. RANK() is computed over all candidates before
    -- LIMIT, so ranks are global across pages; job_id makes the order total.
    SELECT c.*,
           r.required_total, r.required_matched,
           r.preferred_total, r.preferred_matched,
           s.coverage,
           RANK() OVER feed AS rank
      FROM candidate AS c
      JOIN req AS r USING (job_id)
     CROSS JOIN LATERAL (
           SELECT r.required_matched::numeric / NULLIF(r.required_total, 0) AS coverage
           ) AS s
    WINDOW feed AS (ORDER BY s.coverage DESC NULLS LAST,
                             r.preferred_matched DESC,
                             c.source_posted_at DESC NULLS LAST)
     ORDER BY s.coverage DESC NULLS LAST,
              r.preferred_matched DESC,
              c.source_posted_at DESC NULLS LAST,
              c.job_id
     LIMIT %(limit)s OFFSET %(offset)s
)
-- Skill lists for the page's rows only: REQUIRED first, then by name, each
-- flagged matched or not (the caller splits it into matched / missing).
SELECT ranked.*, page_skills.skills
  FROM ranked
  LEFT JOIN LATERAL (
       SELECT COALESCE(
                  json_agg(json_build_object('skill_id', sk.skill_id,
                                             'name', sk.name,
                                             'requirement_type', js.requirement_type,
                                             'matched', us.skill_id IS NOT NULL)
                           ORDER BY js.requirement_type <> 'REQUIRED',
                                    lower(sk.name), sk.skill_id),
                  '[]') AS skills
         FROM public.job_skills AS js
         JOIN public.skills AS sk ON sk.skill_id = js.skill_id
         LEFT JOIN public.user_skills AS us
                ON us.skill_id = js.skill_id AND us.user_id = %(user_id)s
        WHERE js.job_id = ranked.job_id
       ) AS page_skills ON true
 ORDER BY ranked.rank, ranked.job_id  -- rank encodes the three sort keys
"""

_PROFILE_EXISTS = "SELECT 1 FROM public.users WHERE user_id = %s"


@dataclass(frozen=True)
class DiscoverFilters:
    """Optional feed filters; None means "do not filter on this"."""

    job_type: str | None = None
    work_arrangement: str | None = None
    location: str | None = None
    q: str | None = None


class DiscoverProfileMissing(Exception):
    """The caller has no row in public.users."""


class DiscoverStore(Protocol):
    def feed(
        self, user_id: UUID, filters: DiscoverFilters, limit: int, offset: int
    ) -> DiscoverResponse: ...


def query_parameters(
    user_id: UUID, filters: DiscoverFilters, limit: int, offset: int
) -> dict[str, Any]:
    """Bind values for DISCOVER_SQL. Text filters become literal LIKE patterns."""
    return {
        "user_id": str(user_id),
        "job_type": filters.job_type,
        "work_arrangement": filters.work_arrangement,
        "location": _like_pattern(filters.location) if filters.location else None,
        "q": _like_pattern(filters.q) if filters.q else None,
        "limit": limit,
        "offset": offset,
    }


def _item(row: tuple) -> DiscoverItem:
    skills = row[16]
    return DiscoverItem(
        job=JobSummary(
            job_id=str(row[0]),
            title=row[1],
            company_name=row[2],
            location=row[3],
            job_type=row[4],
            work_arrangement=row[5],
            application_url=row[6],
            source=row[7],
            source_posted_at=row[8],
            is_active=row[9],
        ),
        match=JobMatch(
            required_total=row[10],
            required_matched=row[11],
            preferred_total=row[12],
            preferred_matched=row[13],
            coverage=None if row[14] is None else float(row[14]),
            matched_skills=[SkillRequirement(**s) for s in skills if s["matched"]],
            missing_skills=[SkillRequirement(**s) for s in skills if not s["matched"]],
        ),
        rank=row[15],
    )


def _connect() -> PGConnection:
    try:
        return get_pg_connection()
    except (RuntimeError, psycopg2.Error) as exc:
        raise SqlAccessError(_UNAVAILABLE) from exc


class PostgresDiscoverStore:
    def feed(
        self, user_id: UUID, filters: DiscoverFilters, limit: int, offset: int
    ) -> DiscoverResponse:
        """One page of the caller's feed, fetching limit + 1 rows for has_more."""
        conn = _connect()
        try:
            with conn.cursor() as cursor:
                cursor.execute(_PROFILE_EXISTS, (str(user_id),))
                if cursor.fetchone() is None:
                    raise DiscoverProfileMissing
                cursor.execute(DISCOVER_SQL, query_parameters(user_id, filters, limit + 1, offset))
                rows = cursor.fetchall()
        except psycopg2.Error as exc:
            raise SqlAccessError("Discover could not be loaded.") from exc
        finally:
            conn.close()  # read-only: closing discards the transaction

        return DiscoverResponse(
            items=[_item(row) for row in rows[:limit]], has_more=len(rows) > limit
        )


def get_discover_store() -> DiscoverStore:
    return PostgresDiscoverStore()
