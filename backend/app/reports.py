"""Authenticated own-user SQL reports over active job requirements."""

from typing import List

import psycopg2
from fastapi import APIRouter
from pydantic import BaseModel

from .auth import CurrentUser
from .errors import ApiError
from .sql_db import get_pg_connection

router = APIRouter(prefix="/api/reports", tags=["reports"])


class SkillProfileRow(BaseModel):
    skill_id: int
    skill_name: str
    source: str


class SkillProfileResponse(BaseModel):
    user_id: str
    row_count: int
    rows: List[SkillProfileRow]


@router.get("/skill-profile", response_model=SkillProfileResponse)
def get_skill_profile(user: CurrentUser) -> SkillProfileResponse:
    query = """
        SELECT s.skill_id, s.name AS skill_name, 'user_has' AS source
        FROM public.user_skills us
        JOIN public.skills s ON us.skill_id = s.skill_id
        WHERE us.user_id = %(user_id)s

        UNION

        SELECT DISTINCT s.skill_id, s.name AS skill_name, 'required_by_active_job' AS source
        FROM public.job_skills js
        JOIN public.skills s ON js.skill_id = s.skill_id
        JOIN public.jobs j ON j.job_id = js.job_id
        WHERE js.requirement_type = 'REQUIRED' AND j.is_active = true

        ORDER BY skill_name;
    """
    conn = None
    try:
        conn = get_pg_connection()
        with conn.cursor() as cursor:
            cursor.execute(query, {"user_id": str(user.user_id)})
            rows = cursor.fetchall()
    except (RuntimeError, psycopg2.Error) as exc:
        raise ApiError(
            503, "service_unavailable", "The report is temporarily unavailable."
        ) from exc
    finally:
        if conn is not None:
            conn.close()

    result_rows = [
        SkillProfileRow(skill_id=row[0], skill_name=row[1], source=row[2]) for row in rows
    ]
    return SkillProfileResponse(
        user_id=str(user.user_id), row_count=len(result_rows), rows=result_rows
    )
