"""SQL for a student's job tracker (public.user_jobs).

Same idiom as sql_skills.py: one operation opens one connection, works on one
cursor inside one transaction, commits once and closes in a finally block.
Every statement filters by the verified user id passed in by the route.

updated_at is never written here. Migration 003's BEFORE UPDATE trigger moves
it only when the row really changed, which is what makes a repeated PUT with
the same status a no-op. The same migration's BEFORE INSERT trigger rejects a
new row for an inactive (or unknown) job with SQLSTATE 23514.
"""

from typing import Protocol
from uuid import UUID

import psycopg2
from psycopg2 import errors
from psycopg2.extensions import connection as PGConnection

from .schemas import JobSummary, TrackerItem
from .sql_access import SqlAccessError
from .sql_db import get_pg_connection

TRACKER_STATUSES = ("NOT_INTERESTED", "SAVED", "APPLIED", "INTERVIEW", "REJECTED", "OFFER")

LIMIT_DEFAULT = 20
LIMIT_MAX = 50
OFFSET_MAX = 10_000

_UNAVAILABLE = "Your tracker is unavailable."

_ITEM_COLUMNS = """
    j.job_id, j.title, j.company_name, j.location, j.job_type, j.work_arrangement,
    j.application_url, j.source, j.source_posted_at, j.is_active,
    t.status, t.created_at, t.updated_at
"""


class TrackerProfileMissing(Exception):
    """The caller has no row in public.users."""


class TrackerJobMissing(Exception):
    """A new tracker row was requested for an unknown or inactive job."""


class TrackerStore(Protocol):
    def put(self, user_id: UUID, job_id: UUID, status: str) -> TrackerItem: ...

    def list_items(
        self, user_id: UUID, statuses: list[str] | None, limit: int, offset: int
    ) -> tuple[list[TrackerItem], int]: ...

    def summary(self, user_id: UUID) -> dict[str, int]: ...

    def delete(self, user_id: UUID, job_id: UUID) -> None: ...


def _connect() -> PGConnection:
    try:
        return get_pg_connection()
    except (RuntimeError, psycopg2.Error) as exc:
        raise SqlAccessError(_UNAVAILABLE) from exc


def _item(row: tuple) -> TrackerItem:
    return TrackerItem(
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
        status=row[10],
        created_at=row[11],
        updated_at=row[12],
    )


def _profile_exists(cursor, user_id: UUID) -> bool:
    cursor.execute("SELECT 1 FROM public.users WHERE user_id = %s", (str(user_id),))
    return cursor.fetchone() is not None


class SqlTrackerStore:
    def put(self, user_id: UUID, job_id: UUID, status: str) -> TrackerItem:
        """Create or update the decision in one statement; return the item.

        A bare INSERT ... ON CONFLICT DO UPDATE cannot be used: Postgres fires
        BEFORE INSERT row triggers before it looks for the conflict, so the
        active-job trigger would reject updates of existing rows whose job has
        since gone inactive. The UPDATE therefore runs first and the INSERT
        (still ON CONFLICT DO UPDATE, for a concurrent first PUT) only when it
        matched nothing. An UPDATE to an unchanged status is skipped by the
        WHEN (OLD.* IS DISTINCT FROM NEW.*) trigger, so updated_at stays put.

        A failed insert is classified by looking at the profile
        after the rollback: with no profile the answer is "profile" whatever
        else is wrong (the active-job trigger fires before the user FK, so the
        error code alone cannot tell the two apart).
        """
        conn = _connect()
        try:
            try:
                with conn.cursor() as cursor:
                    cursor.execute(
                        f"""
                        WITH upd AS (
                            UPDATE public.user_jobs SET status = %(status)s
                             WHERE user_id = %(user)s AND job_id = %(job)s
                            RETURNING user_id, job_id, status, created_at, updated_at
                        ), ins AS (
                            INSERT INTO public.user_jobs (user_id, job_id, status)
                            SELECT %(user)s, %(job)s, %(status)s
                             WHERE NOT EXISTS (SELECT 1 FROM upd)
                            ON CONFLICT (user_id, job_id) DO UPDATE SET status = EXCLUDED.status
                            RETURNING user_id, job_id, status, created_at, updated_at
                        ), t AS (
                            SELECT * FROM upd UNION ALL SELECT * FROM ins
                        )
                        SELECT {_ITEM_COLUMNS}
                          FROM t JOIN public.jobs AS j ON j.job_id = t.job_id
                        """,
                        {"user": str(user_id), "job": str(job_id), "status": status},
                    )
                    row = cursor.fetchone()
                conn.commit()
                return _item(row)
            except (errors.ForeignKeyViolation, errors.CheckViolation) as exc:
                conn.rollback()
                # A CHECK on the status column carries a constraint name; the
                # active-job trigger's error has none. Only the latter is ours.
                if isinstance(exc, errors.CheckViolation) and exc.diag.constraint_name:
                    raise
                with conn.cursor() as cursor:
                    if not _profile_exists(cursor, user_id):
                        raise TrackerProfileMissing from exc
                raise TrackerJobMissing from exc
        except psycopg2.Error as exc:
            conn.rollback()
            raise SqlAccessError("Your tracker could not be saved; nothing was written.") from exc
        finally:
            conn.close()

    def list_items(
        self, user_id: UUID, statuses: list[str] | None, limit: int, offset: int
    ) -> tuple[list[TrackerItem], int]:
        conn = _connect()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT {_ITEM_COLUMNS}, COUNT(*) OVER () AS total
                      FROM public.user_jobs AS t
                      JOIN public.jobs AS j ON j.job_id = t.job_id
                     WHERE t.user_id = %s
                       AND (%s::text[] IS NULL OR t.status = ANY(%s::text[]))
                     ORDER BY t.updated_at DESC, t.job_id
                     LIMIT %s OFFSET %s
                    """,
                    (str(user_id), statuses, statuses, limit, offset),
                )
                rows = cursor.fetchall()
                if rows:
                    total = rows[0][13]
                elif offset == 0:
                    total = 0
                else:
                    # COUNT(*) OVER () yields no row on a page past the end,
                    # so the total needs its own query in that one case.
                    cursor.execute(
                        """
                        SELECT COUNT(*) FROM public.user_jobs
                         WHERE user_id = %s
                           AND (%s::text[] IS NULL OR status = ANY(%s::text[]))
                        """,
                        (str(user_id), statuses, statuses),
                    )
                    total = cursor.fetchone()[0]
        except psycopg2.Error as exc:
            raise SqlAccessError("Your tracker could not be read.") from exc
        finally:
            conn.close()
        return [_item(row) for row in rows], int(total)

    def summary(self, user_id: UUID) -> dict[str, int]:
        conn = _connect()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT status, job_count FROM public.v_user_tracker_summary"
                    " WHERE user_id = %s",
                    (str(user_id),),
                )
                rows = cursor.fetchall()
        except psycopg2.Error as exc:
            raise SqlAccessError("Your tracker could not be read.") from exc
        finally:
            conn.close()
        counts = dict.fromkeys(TRACKER_STATUSES, 0)
        counts.update({status: int(count) for status, count in rows})
        return counts

    def delete(self, user_id: UUID, job_id: UUID) -> None:
        """Idempotent: an absent row is already the desired state."""
        conn = _connect()
        try:
            with conn.cursor() as cursor:
                if not _profile_exists(cursor, user_id):
                    raise TrackerProfileMissing
                cursor.execute(
                    "DELETE FROM public.user_jobs WHERE user_id = %s AND job_id = %s",
                    (str(user_id), str(job_id)),
                )
            conn.commit()
        except psycopg2.Error as exc:
            conn.rollback()
            raise SqlAccessError("Your tracker could not be changed; nothing was written.") from exc
        finally:
            conn.close()


def get_tracker_store() -> TrackerStore:
    return SqlTrackerStore()
