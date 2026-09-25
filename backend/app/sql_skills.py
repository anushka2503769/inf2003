"""SQL for the shared skill dictionary and a student's confirmed skills.

Same idiom as sql_access.py and sql_profile.py: one operation opens one
connection, does all of its work on one cursor inside one transaction, commits
once and closes in a finally block.

Membership changes also touch users.updated_at, and docs/API.md requires that
to happen in the same transaction as the link change. Everything a route needs
is therefore one function, not two composed ones: two calls are two
transactions, and the first can commit while the second fails.
"""

from uuid import UUID

import psycopg2
from psycopg2.extensions import connection as PGConnection

from .config import get_settings
from .schemas import Skill
from .sql_access import SqlAccessError
from .sql_db import get_pg_connection

# docs/API.md: skill IDs are positive integers within PostgreSQL's integer
# range. Anything larger is a client mistake, not a missing row.
MAX_SKILL_ID = 2**31 - 1

SEARCH_LIMIT_MIN = 1
SEARCH_LIMIT_MAX = 100
SEARCH_LIMIT_DEFAULT = 20
QUERY_MAX_LENGTH = 100

# Sort by lowercase name with the ID as tie-breaker, so the order does not
# depend on the database's collation of mixed case.
_ORDER = "ORDER BY lower(name), skill_id"


def database_configured() -> bool:
    return bool(get_settings().database_url)


def _require_database() -> None:
    if not database_configured():
        raise SqlAccessError("The skill dictionary is unavailable.")


def _connect() -> PGConnection:
    _require_database()
    try:
        return get_pg_connection()
    except (RuntimeError, psycopg2.Error) as exc:
        raise SqlAccessError("The skill dictionary is unavailable.") from exc


def _like_pattern(query: str) -> str:
    """Treat the student's text as literal characters, not LIKE operators.

    % and _ are ordinary characters in a skill name ("C_" would otherwise match
    everything of that length), so they are escaped and ESCAPE is declared.
    """
    escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def search_skills(query: str, limit: int) -> tuple[list[Skill], bool]:
    """Case-insensitive literal substring search over the dictionary.

    Fetches one row beyond the limit to decide has_more without a second count
    query. An empty query lists the dictionary from the start.
    """
    conn = _connect()
    try:
        with conn.cursor() as cursor:
            if query:
                cursor.execute(
                    f"""
                    SELECT skill_id, name FROM public.skills
                     WHERE name ILIKE %s ESCAPE '\\'
                     {_ORDER} LIMIT %s
                    """,
                    (_like_pattern(query), limit + 1),
                )
            else:
                cursor.execute(
                    f"SELECT skill_id, name FROM public.skills {_ORDER} LIMIT %s",
                    (limit + 1,),
                )
            rows = cursor.fetchall()
    except psycopg2.Error as exc:
        raise SqlAccessError("The skill dictionary could not be searched.") from exc
    finally:
        conn.close()

    has_more = len(rows) > limit
    return [Skill(skill_id=row[0], name=row[1]) for row in rows[:limit]], has_more


def confirmed_skills(user_id: UUID) -> list[Skill]:
    """A student's confirmed skills, for the profile response.

    Returns nothing when no database is configured, so the in-memory
    development store still serves a profile instead of failing.
    """
    if not database_configured():
        return []

    conn = _connect()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT s.skill_id, s.name
                  FROM public.user_skills AS us
                  JOIN public.skills AS s ON s.skill_id = us.skill_id
                 WHERE us.user_id = %s
                 ORDER BY lower(s.name), s.skill_id
                """,
                (str(user_id),),
            )
            rows = cursor.fetchall()
    except psycopg2.Error as exc:
        raise SqlAccessError("Your confirmed skills could not be read.") from exc
    finally:
        conn.close()

    return [Skill(skill_id=row[0], name=row[1]) for row in rows]


def add_confirmed_skill(user_id: UUID, skill_id: int) -> str:
    """Ensure the student has this skill. Returns what the outcome was.

    "no_profile" and "no_skill" are reported rather than raised so the route
    decides the response. Existence is checked inside the same transaction as
    the insert, so the answer cannot go stale between the two.
    """
    conn = _connect()
    try:
        with conn.cursor() as cursor:
            if not _exists(
                cursor, "SELECT 1 FROM public.users WHERE user_id = %s", (str(user_id),)
            ):
                return "no_profile"
            if not _exists(cursor, "SELECT 1 FROM public.skills WHERE skill_id = %s", (skill_id,)):
                return "no_skill"

            cursor.execute(
                """
                INSERT INTO public.user_skills (user_id, skill_id)
                VALUES (%s, %s)
                ON CONFLICT DO NOTHING
                RETURNING skill_id
                """,
                (str(user_id), skill_id),
            )
            if cursor.fetchone() is None:
                # Already confirmed. A repeat is success, and updated_at must
                # not move for a request that changed nothing.
                return "unchanged"

            _touch(cursor, user_id)
        conn.commit()
        return "added"
    except psycopg2.Error as exc:
        conn.rollback()
        raise SqlAccessError("The skill could not be saved; nothing was written.") from exc
    finally:
        conn.close()


def remove_confirmed_skill(user_id: UUID, skill_id: int) -> str:
    """Ensure the student does not have this skill.

    Only the link is deleted; the dictionary entry in public.skills is shared
    and is never touched. An absent link is already the desired state.
    """
    conn = _connect()
    try:
        with conn.cursor() as cursor:
            if not _exists(
                cursor, "SELECT 1 FROM public.users WHERE user_id = %s", (str(user_id),)
            ):
                return "no_profile"

            cursor.execute(
                """
                DELETE FROM public.user_skills
                 WHERE user_id = %s AND skill_id = %s
                RETURNING skill_id
                """,
                (str(user_id), skill_id),
            )
            if cursor.fetchone() is None:
                return "unchanged"

            _touch(cursor, user_id)
        conn.commit()
        return "removed"
    except psycopg2.Error as exc:
        conn.rollback()
        raise SqlAccessError("The skill could not be removed; nothing was written.") from exc
    finally:
        conn.close()


def _exists(cursor, query: str, parameters: tuple) -> bool:
    cursor.execute(query, parameters)
    return cursor.fetchone() is not None


def _touch(cursor, user_id: UUID) -> None:
    """Move users.updated_at in the same transaction as the membership change."""
    cursor.execute(
        "UPDATE public.users SET updated_at = now() WHERE user_id = %s",
        (str(user_id),),
    )
