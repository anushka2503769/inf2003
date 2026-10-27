"""
Shared Postgres (Supabase) connection for raw SQL reporting queries.
Reuses the same DATABASE_URL env var as skills_repository.py.

Connections are reused. Opening one costs a TCP handshake (plus TLS and login
against Supabase), and every closed one holds a local port in TIME_WAIT for
about 30 s; under sustained load that exhausted the host's ports (see
docs/perf/README.md, "Finding"). So close() on a connection from here does not
hang up: it rolls back and parks the connection in a small idle pool, and the
next get_pg_connection() hands it out again. Callers keep the usual
open / try / finally close() pattern and need no changes.
"""

import threading
import time

import psycopg2
from psycopg2.extensions import TRANSACTION_STATUS_IDLE
from psycopg2.extensions import connection as PGConnection

from .config import get_settings

_MAX_IDLE = 20  # spare connections kept open per backend process
_MAX_IDLE_SECONDS = 60.0  # spares unused for longer are closed, not reused
# Idle age uses the wall clock, not time.monotonic(): on macOS the monotonic
# clock stops while the laptop sleeps, so a connection parked before an
# hour-long sleep would look seconds old, be reused, and hang on a socket the
# network dropped meanwhile.

_idle: list["_PooledConnection"] = []
_idle_lock = threading.Lock()


class _PooledConnection(PGConnection):
    """A psycopg2 connection whose close() returns it to the idle pool."""

    _pool_dsn = ""
    _idle_since = 0.0
    _parked = False

    def close(self) -> None:
        if self.closed or self._parked:
            return  # already closed, or a second close() of a parked connection
        try:
            # Ends any open transaction, which also undoes SET LOCAL and releases
            # pg_advisory_xact_lock locks, so the next borrower starts clean.
            self.rollback()
        except psycopg2.Error:
            self.discard()  # the server or network dropped it
            return
        if self.autocommit or self.info.transaction_status != TRANSACTION_STATUS_IDLE:
            self.discard()  # not in a known clean state
            return
        self._idle_since = time.time()
        with _idle_lock:
            if len(_idle) < _MAX_IDLE:
                self._parked = True
                _idle.append(self)
                return
        self.discard()  # pool is full

    def discard(self) -> None:
        """Really close the connection (psycopg2's own close)."""
        self._parked = False
        PGConnection.close(self)


def _take_idle(database_url: str) -> PGConnection | None:
    """Pop the most recently returned usable connection, closing stale ones."""
    stale: list[_PooledConnection] = []
    found = None
    now = time.time()
    with _idle_lock:
        while _idle:
            conn = _idle.pop()  # newest first
            conn._parked = False
            if (
                conn._pool_dsn == database_url
                and not conn.closed
                # a negative age means the clock was set back: treat as stale
                and 0.0 <= now - conn._idle_since < _MAX_IDLE_SECONDS
            ):
                found = conn
                break
            stale.append(conn)
    for conn in stale:
        conn.discard()
    return found


def get_pg_connection() -> PGConnection:
    """Returns a Postgres connection, reusing an idle one when there is one.

    Caller is responsible for closing it; close() returns it to the idle pool.
    Do not use a connection after closing it: another request may have it.
    """
    database_url = get_settings().database_url
    if not database_url:
        raise RuntimeError(
            "DATABASE_URL is not set. Configure the backend before using SQL routes."
        )
    conn = _take_idle(database_url)
    if conn is not None:
        return conn
    conn = psycopg2.connect(database_url, connection_factory=_PooledConnection)
    conn._pool_dsn = database_url
    return conn


def close_idle_connections() -> None:
    """Close every parked connection (used by tests; process exit closes the rest)."""
    with _idle_lock:
        parked = list(_idle)
        _idle.clear()
    for conn in parked:
        conn.discard()
