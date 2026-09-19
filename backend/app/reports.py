"""
Reporting endpoints that run raw SQL against Postgres (Supabase),
demonstrating JOIN, WHERE, ORDER BY, and UNION SELECT in genuine,
executable queries - not simulated.
"""

from typing import List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from psycopg2 import sql as pg_sql
from psycopg2.errors import UndefinedTable

from backend.app.sql_db import get_pg_connection

router = APIRouter(prefix="/api/reports", tags=["reports"])


class SkillProfileRow(BaseModel):
    skill_id: int
    skill_name: str
    source: str  # "user_has" or "required_by_active_job"


class SkillProfileResponse(BaseModel):
    user_id: str
    row_count: int
    rows: List[SkillProfileRow]


@router.get("/skill-profile/{user_id}", response_model=SkillProfileResponse)
def get_skill_profile(user_id: str) -> SkillProfileResponse:
    """
    Runs one SQL query combining two labeled result sets via UNION:
      1. Skills this user already has (JOIN user_skills -> skills, WHERE user_id = %s)
      2. Skills required by any active job posting (JOIN job_skills -> skills, WHERE requirement_type = 'REQUIRED')
    Sorted with ORDER BY skill_name so the two sources interleave alphabetically.

    Note: if job_skills isn't populated yet (or doesn't exist), this still
    runs - it just returns the user_has rows. UNION doesn't require both
    sides to have matching data, only matching column shape.
    """
    query = """
        SELECT s.skill_id, s.name AS skill_name, 'user_has' AS source
        FROM user_skills us
        JOIN skills s ON us.skill_id = s.skill_id
        WHERE us.user_id = %(user_id)s

        UNION

        SELECT s.skill_id, s.name AS skill_name, 'required_by_active_job' AS source
        FROM job_skills js
        JOIN skills s ON js.skill_id = s.skill_id
        WHERE js.requirement_type = 'REQUIRED'

        ORDER BY skill_name;
    """

    conn = get_pg_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(query, {"user_id": user_id})
            rows = cur.fetchall()
    except UndefinedTable as exc:
        raise HTTPException(
            status_code=503,
            detail=f"A required table doesn't exist yet (check with your team's SQL owner): {exc}",
        ) from exc
    finally:
        conn.close()

    result_rows = [
        SkillProfileRow(skill_id=row[0], skill_name=row[1], source=row[2]) for row in rows
    ]
    return SkillProfileResponse(user_id=user_id, row_count=len(result_rows), rows=result_rows)