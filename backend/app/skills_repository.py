"""Load the canonical skill dictionary from PostgreSQL."""

import time

from .sql_db import get_pg_connection

Skill = tuple[int, str]
_CACHE_TTL_SECONDS = 300
_cache: list[Skill] = []
_cache_loaded_at = 0.0


class SkillsRepositoryError(RuntimeError):
    """The canonical SQL skill dictionary could not be read."""


def _fetch_skills_from_sql() -> list[Skill]:
    conn = get_pg_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT skill_id, name FROM public.skills ORDER BY skill_id")
            return [(int(skill_id), str(name)) for skill_id, name in cursor.fetchall()]
    finally:
        conn.close()


def get_all_skills(force_refresh: bool = False, *, require_database: bool = True) -> list[Skill]:
    """Return cached canonical skills; raise instead of using a local fallback."""
    del require_database  # retained for callers that explicitly require SQL.
    global _cache, _cache_loaded_at
    stale = time.time() - _cache_loaded_at > _CACHE_TTL_SECONDS
    if not (force_refresh or stale or not _cache):
        return _cache
    try:
        skills = _fetch_skills_from_sql()
    except Exception as exc:
        raise SkillsRepositoryError("SQL skills dictionary is unavailable.") from exc
    if not skills:
        raise SkillsRepositoryError("SQL skills dictionary is empty.")
    _cache = skills
    _cache_loaded_at = time.time()
    return _cache
