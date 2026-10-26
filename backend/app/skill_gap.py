"""Skill gap for one target role: what active postings ask for, and what you have.

docs/API.md section 8, PRD WP-4. Two engines answer the same question:

- ``skill_gap_mongo`` - the production path, a MongoDB aggregation over
  ``job_documents`` (the requirement arrays live there, with years).
- ``skill_gap_sql`` - the same counts from SQL ``job_skills``. Not a route; it
  exists for the WP-10 benchmark and for the test that both engines agree.

Rules (PRD section 4): the denominator is the number of active, ready jobs in the
role. A skill counts once per job; REQUIRED wins over PREFERRED when one job
lists both. ``minimum_years`` is reported ("mentioned in N postings, max X
yrs") and never compared with the student.

The route holds the job read dependency (``AuthenticatedJobDatabase``) for the
whole request, so the active-id set read from SQL and the Mongo documents
aggregated against it come from the same pipeline state.
"""

from decimal import Decimal
from typing import Any, Iterable
from uuid import UUID

import psycopg2
from bson.decimal128 import Decimal128
from pymongo.database import Database

from .schemas import SkillGapResponse, SkillGapRole, SkillGapRow, SkillGapSummary
from .sql_access import SqlAccessError
from .sql_db import get_pg_connection

ROLE_CATEGORY_MAX_LENGTH = 100
LIMIT_MIN = 1
LIMIT_MAX = 100
LIMIT_DEFAULT = 30
TOP_N = 10

_READY = "true"  # extracted_data.provider.ready is the STRING "true" (job-pipeline.md)


def _ready_match(active_job_ids: Iterable[str]) -> dict[str, Any]:
    """Documents a job read may see: active SQL parent and explicit Mongo readiness."""
    return {
        "job_id": {"$in": sorted(active_job_ids)},
        "extracted_data.provider.ready": _READY,
    }


def skill_gap_pipeline(active_job_ids: Iterable[str], role_category: str) -> list[dict]:
    """The aggregation for one role. Stages:

    1. $match   - job_id in the active SQL ids, exact role_category, ready == "true".
                  This set of documents is the sample (the denominator).
    2. $facet   - two sub-pipelines over the same matched documents:
       sample:  $count -> [{jobs: N}]; [] when nothing matched (handled by caller).
       skills:
         a. $unwind  extracted_data.requirements - one document per requirement.
                     A job with no requirements drops out here but is still in sample.
         b. $group   by {job_id, skill_id} - dedupe per job. required = $max of
                     (type == REQUIRED ? 1 : 0), so REQUIRED wins over PREFERRED;
                     years = $max of minimum_years ($max ignores nulls).
         c. $group   by skill_id - job_count = jobs mentioning it (once each),
                     required_count = sum of the per-job flags, max_years = $max,
                     years_mentions = jobs whose years is a number.
         d. $sort    job_count desc, then skill_id asc (API.md order).
    """
    requirement = "$extracted_data.requirements"
    return [
        {
            "$match": {
                "job_id": {"$in": sorted(active_job_ids)},
                "extracted_data.role_category": role_category,
                "extracted_data.provider.ready": _READY,
            }
        },
        {
            "$facet": {
                "sample": [{"$count": "jobs"}],
                "skills": [
                    {"$unwind": requirement},
                    {
                        "$group": {
                            "_id": {"job_id": "$job_id", "skill_id": f"{requirement}.skill_id"},
                            "required": {
                                "$max": {
                                    "$cond": [
                                        {"$eq": [f"{requirement}.requirement_type", "REQUIRED"]},
                                        1,
                                        0,
                                    ]
                                }
                            },
                            "years": {"$max": f"{requirement}.minimum_years"},
                        }
                    },
                    {
                        "$group": {
                            "_id": "$_id.skill_id",
                            "job_count": {"$sum": 1},
                            "required_count": {"$sum": "$required"},
                            "max_years": {"$max": "$years"},
                            "years_mentions": {"$sum": {"$cond": [{"$isNumber": "$years"}, 1, 0]}},
                        }
                    },
                    {"$sort": {"job_count": -1, "_id": 1}},
                ],
            }
        },
    ]


def roles_pipeline(active_job_ids: Iterable[str]) -> list[dict]:
    """Ready, active documents grouped by role, most postings first, then by name."""
    return [
        {"$match": _ready_match(active_job_ids)},
        {
            "$group": {
                "_id": {"$ifNull": ["$extracted_data.role_category", "Unclassified"]},
                "job_count": {"$sum": 1},
            }
        },
        {"$sort": {"job_count": -1, "_id": 1}},
    ]


def list_roles(db: Database, active_job_ids: Iterable[str]) -> list[SkillGapRole]:
    return [
        SkillGapRole(role_category=str(doc["_id"]), job_count=int(doc["job_count"]))
        for doc in db["job_documents"].aggregate(roles_pipeline(active_job_ids))
    ]


def role_job_ids(db: Database, active_job_ids: Iterable[str], role_category: str) -> list[str]:
    """The sample's job ids (same $match as the pipeline), for ``skill_gap_sql``."""
    match = skill_gap_pipeline(active_job_ids, role_category)[0]["$match"]
    return sorted(str(doc["job_id"]) for doc in db["job_documents"].find(match, {"job_id": 1}))


def _years(value: Any) -> int | float | None:
    if isinstance(value, Decimal128):
        value = value.to_decimal()
    if isinstance(value, Decimal):
        return float(value)
    return value


def _frequency(job_count: int, sample_size: int) -> float:
    return job_count / sample_size if sample_size else 0.0


def skill_gap_mongo(
    db: Database, active_job_ids: Iterable[str], role_category: str, user_id: UUID
) -> tuple[int, list[SkillGapRow]] | None:
    """Mongo engine: (sample_size, every skill row in API order), or None without a profile.

    Step 1 (active ids under the read lock) is the caller's; this is steps 2 and 3.
    """
    facet = next(
        iter(db["job_documents"].aggregate(skill_gap_pipeline(active_job_ids, role_category))), {}
    )
    sample = facet.get("sample") or []
    sample_size = int(sample[0]["jobs"]) if sample else 0
    counted = facet.get("skills") or []

    lookup = skill_names_and_user_skills(user_id, [int(doc["_id"]) for doc in counted])
    if lookup is None:
        return None
    names, user_skill_ids = lookup

    rows = []
    for doc in counted:
        skill_id = int(doc["_id"])
        if skill_id not in names:
            # A Mongo requirement whose id is no longer in the SQL dictionary
            # cannot be shown or added; it is left out rather than renamed.
            continue
        job_count = int(doc["job_count"])
        required = int(doc["required_count"])
        rows.append(
            SkillGapRow(
                skill_id=skill_id,
                name=names[skill_id],
                job_count=job_count,
                frequency=_frequency(job_count, sample_size),
                required_count=required,
                preferred_count=job_count - required,
                max_minimum_years=_years(doc.get("max_years")),
                years_mentions=int(doc.get("years_mentions") or 0),
                user_has=skill_id in user_skill_ids,
            )
        )
    return sample_size, rows


def _connect():
    try:
        return get_pg_connection()
    except (RuntimeError, psycopg2.Error) as exc:
        raise SqlAccessError("The skill gap is temporarily unavailable.") from exc


def skill_names_and_user_skills(
    user_id: UUID, skill_ids: list[int]
) -> tuple[dict[int, str], set[int]] | None:
    """Step 3: dictionary names for the counted ids and which the student confirmed.

    One connection, one read-only transaction. None means the student has no
    profile row (API.md: 404 profile).
    """
    conn = _connect()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT 1 FROM public.users WHERE user_id = %s", (str(user_id),))
            if cursor.fetchone() is None:
                return None
            cursor.execute(
                "SELECT skill_id, name FROM public.skills WHERE skill_id = ANY(%s)",
                (skill_ids,),
            )
            names = {int(row[0]): row[1] for row in cursor.fetchall()}
            cursor.execute(
                """
                SELECT skill_id FROM public.user_skills
                 WHERE user_id = %s AND skill_id = ANY(%s)
                """,
                (str(user_id), skill_ids),
            )
            owned = {int(row[0]) for row in cursor.fetchall()}
        return names, owned
    except psycopg2.Error as exc:
        raise SqlAccessError("The skill gap is temporarily unavailable.") from exc
    finally:
        conn.rollback()
        conn.close()


_SQL_SAMPLE = """
SELECT count(*) FROM public.jobs
 WHERE job_id = ANY(%s::uuid[]) AND is_active
"""

# job_skills has one row per (job_id, skill_id), so counting rows is already
# once per job, and its single requirement_type is the per-job strength.
_SQL_SKILLS = """
WITH sample AS (
    SELECT job_id FROM public.jobs
     WHERE job_id = ANY(%s::uuid[]) AND is_active
)
SELECT js.skill_id,
       s.name,
       count(*) AS job_count,
       count(*) FILTER (WHERE js.requirement_type = 'REQUIRED') AS required_count,
       EXISTS (
           SELECT 1 FROM public.user_skills AS us
            WHERE us.user_id = %s AND us.skill_id = js.skill_id
       ) AS user_has
  FROM sample
  JOIN public.job_skills AS js ON js.job_id = sample.job_id
  JOIN public.skills AS s ON s.skill_id = js.skill_id
 GROUP BY js.skill_id, s.name
 ORDER BY job_count DESC, js.skill_id
"""


def skill_gap_sql(role_ids: Iterable[str], user_id: UUID) -> tuple[int, list[SkillGapRow]]:
    """SQL engine: the same (sample_size, rows) from ``job_skills``.

    ``role_ids`` are the role's job ids from Mongo (``role_job_ids``): SQL has
    no role_category. SQL also has no minimum_years, so ``max_minimum_years``
    is None and ``years_mentions`` 0 here; every count matches the Mongo engine.
    """
    ids = sorted({str(job_id) for job_id in role_ids})
    conn = _connect()
    try:
        with conn.cursor() as cursor:
            cursor.execute(_SQL_SAMPLE, (ids,))
            sample_size = int(cursor.fetchone()[0])
            cursor.execute(_SQL_SKILLS, (ids, str(user_id)))
            fetched = cursor.fetchall()
    except psycopg2.Error as exc:
        raise SqlAccessError("The skill gap is temporarily unavailable.") from exc
    finally:
        conn.rollback()
        conn.close()

    rows = [
        SkillGapRow(
            skill_id=int(skill_id),
            name=name,
            job_count=int(job_count),
            frequency=_frequency(int(job_count), sample_size),
            required_count=int(required),
            preferred_count=int(job_count) - int(required),
            max_minimum_years=None,
            years_mentions=0,
            user_has=bool(user_has),
        )
        for skill_id, name, job_count, required, user_has in fetched
    ]
    return sample_size, rows


def build_response(
    role_category: str, sample_size: int, rows: list[SkillGapRow], limit: int
) -> SkillGapResponse:
    skills = rows[:limit]
    top_n = min(TOP_N, len(skills))
    return SkillGapResponse(
        role_category=role_category,
        sample_size=sample_size,
        skills=skills,
        summary=SkillGapSummary(
            top_n=top_n, user_has_in_top_n=sum(row.user_has for row in skills[:top_n])
        ),
    )
