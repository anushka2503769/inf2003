"""PostgreSQL implementation of ProfileStore.

Follows the connection idiom established in sql_access.py: one operation opens
one connection, does all of its work on one cursor inside one transaction,
commits once, and closes in a finally block. Nothing here composes two public
functions to reach an atomic result, because two calls are two transactions and
the first can succeed while the second fails.

psycopg2 errors are wrapped in SqlAccessError so no driver text, SQL or
connection detail reaches a response. errors.py turns that into the 503
"service_unavailable" envelope, which is the outage case docs/API.md separates
from an invalid credential.
"""

from uuid import UUID

import psycopg2
from psycopg2 import errors as pg_errors
from psycopg2.extensions import connection as PGConnection

from .schemas import Profile
from .sql_access import SqlAccessError
from .sql_db import get_pg_connection

_COLUMNS = "user_id, full_name, created_at, updated_at"

_UPSERT = f"""
INSERT INTO public.users (user_id, full_name)
VALUES (%s, %s)
ON CONFLICT (user_id) DO UPDATE
    SET full_name = EXCLUDED.full_name,
        updated_at = now()
RETURNING {_COLUMNS}
"""

# Inside UPDATE, a column reference in an expression is the pre-update value,
# so this compares the stored name against the incoming one.
_RENAME = f"""
UPDATE public.users
   SET full_name = %s,
       updated_at = CASE WHEN full_name IS DISTINCT FROM %s THEN now() ELSE updated_at END
 WHERE user_id = %s
RETURNING {_COLUMNS}
"""


def _profile(row: tuple) -> Profile:
    return Profile(user_id=row[0], full_name=row[1], created_at=row[2], updated_at=row[3])


def _connect() -> PGConnection:
    try:
        return get_pg_connection()
    except (RuntimeError, psycopg2.Error) as exc:
        raise SqlAccessError("The profile database is unavailable.") from exc


class PostgresProfileStore:
    """Reads and writes public.users.

    Every method takes the user id from the caller, which routes derive from the
    verified token. The backend connects with a privileged role that bypasses
    RLS, so ownership is enforced here by always filtering on that id and never
    accepting one from a request body.
    """

    def get(self, user_id: UUID) -> Profile | None:
        conn = _connect()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"SELECT {_COLUMNS} FROM public.users WHERE user_id = %s",
                    (str(user_id),),
                )
                row = cursor.fetchone()
            return _profile(row) if row else None
        except psycopg2.Error as exc:
            raise SqlAccessError("The profile could not be read.") from exc
        finally:
            conn.close()

    def upsert(self, user_id: UUID, full_name: str) -> Profile:
        """Creates the row, or updates the name when it already exists.

        ON CONFLICT rather than check-then-insert: a retry after a lost response
        must not raise a conflict the student cannot act on, and two simultaneous
        first logins must not produce two rows. created_at is absent from the
        update, so the original creation time survives a retry.
        """
        conn = _connect()
        try:
            with conn.cursor() as cursor:
                cursor.execute(_UPSERT, (str(user_id), full_name))
                row = cursor.fetchone()
                if row is None:
                    raise SqlAccessError("The profile write did not return a row.")
            conn.commit()
            return _profile(row)
        except SqlAccessError:
            conn.rollback()
            raise
        except pg_errors.ForeignKeyViolation as exc:
            # public.users.user_id references auth.users.id. A verified token
            # always has that account, so this means the API is pointed at a
            # different project than the one that issued the token.
            conn.rollback()
            raise SqlAccessError(
                "The signed-in account does not exist in this project's authentication store."
            ) from exc
        except psycopg2.Error as exc:
            conn.rollback()
            raise SqlAccessError("The profile could not be saved; nothing was written.") from exc
        finally:
            conn.close()

    def update_name(self, user_id: UUID, full_name: str) -> Profile | None:
        """Renames an existing student. Returns None when there is no row.

        updated_at moves only when the stored name actually changes, per
        docs/API.md; a repeated rename to the same value is a no-op.
        """
        conn = _connect()
        try:
            with conn.cursor() as cursor:
                cursor.execute(_RENAME, (full_name, full_name, str(user_id)))
                row = cursor.fetchone()
            conn.commit()
            return _profile(row) if row else None
        except psycopg2.Error as exc:
            conn.rollback()
            raise SqlAccessError("The profile could not be saved; nothing was written.") from exc
        finally:
            conn.close()
