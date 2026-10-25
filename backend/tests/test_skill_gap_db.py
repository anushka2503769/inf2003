"""Skill gap against real PostgreSQL and MongoDB (disposable containers).

Skipped unless BOTH TEST_DATABASE_URL and TEST_MONGODB_URI are set; they must
point at throwaway databases (backend/scripts/run_disposable_db_tests.sh makes
them). The fixtures truncate SQL users/skills/jobs and delete every document in
the test Mongo database's job_documents. Never point them at the team's
Supabase or MongoDB projects.

The script loads docs/DB/001_initial_collections.js into MONGO_TEST_DATABASE
first, so every fixture document below passes the production validator.
Requests go through the HTTP routes and the real job read dependency (the
job pipeline lock on the test PostgreSQL), not fakes.
"""

import asyncio
import os
from collections.abc import Iterator
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import httpx
import psycopg2
import pytest
from pymongo import MongoClient
from pymongo.errors import WriteError

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "").strip()
TEST_MONGODB_URI = os.environ.get("TEST_MONGODB_URI", "").strip()
MONGO_TEST_DATABASE = "jobless_simulator_test"

pytestmark = pytest.mark.skipif(
    not (TEST_DATABASE_URL and TEST_MONGODB_URI),
    reason="Set TEST_DATABASE_URL and TEST_MONGODB_URI to throwaway databases to run these.",
)

ANA = UUID("11111111-1111-4111-8111-111111111111")  # has a profile
BEN = UUID("22222222-2222-4222-8222-222222222222")  # never onboarded

SE = "Software Engineering"
DA = "Data Analytics"
CY = "Cybersecurity"
DESIGN = "Design"  # present in Mongo, but no active+ready posting

SKILLS = ["Python", "SQL", "Docker", "Excel", "Go"]


def _job_id(n: int) -> str:
    return f"aaaaaaaa-0000-4000-8000-{n:012d}"


def req(skill: str, kind: str, years: Any = None) -> dict[str, Any]:
    return {"skill": skill, "requirement_type": kind, "minimum_years": years}


# (n, role, sql is_active, mongo ready, requirements). Requirement order matters:
# job 3 lists PREFERRED before REQUIRED to prove precedence is not "first wins".
JOBS: list[tuple[int, str, bool, str, list[dict[str, Any]]]] = [
    # Python listed twice in one job: counted once, REQUIRED wins, max years 5.
    (
        1,
        SE,
        True,
        "true",
        [req("Python", "REQUIRED", 3), req("SQL", "PREFERRED"), req("Python", "PREFERRED", 5)],
    ),
    (2, SE, True, "true", [req("Python", "PREFERRED"), req("Docker", "REQUIRED", 2)]),
    (3, SE, True, "true", [req("SQL", "PREFERRED", 1.5), req("SQL", "REQUIRED")]),
    (4, SE, True, "true", []),  # in the denominator with no skills
    (5, SE, False, "true", [req("Go", "REQUIRED", 10)]),  # inactive SQL parent
    (6, SE, True, "false", [req("Go", "REQUIRED", 10)]),  # Mongo doc not ready
    (7, DA, True, "true", [req("Excel", "REQUIRED"), req("Go", "REQUIRED")]),  # other role
    (8, DA, True, "true", [req("Excel", "PREFERRED", 0)]),
    (9, CY, True, "true", []),
    (10, CY, True, "true", []),
    (11, DESIGN, True, "false", [req("Excel", "REQUIRED")]),
    (12, DESIGN, False, "true", [req("Excel", "REQUIRED")]),
]


@pytest.fixture(autouse=True)
def databases(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    monkeypatch.setenv("MONGODB_URI", TEST_MONGODB_URI)
    monkeypatch.setenv("MONGODB_DATABASE", MONGO_TEST_DATABASE)
    from app import config, db

    config.get_settings.cache_clear()
    db.reset_client_for_tests()
    _reset()
    _seed()
    yield
    _reset()
    db.reset_client_for_tests()
    config.get_settings.cache_clear()


def _sql() -> psycopg2.extensions.connection:
    return psycopg2.connect(TEST_DATABASE_URL)


def _mongo():
    client = MongoClient(TEST_MONGODB_URI)
    return client, client[MONGO_TEST_DATABASE]


def _reset() -> None:
    conn = _sql()
    try:
        with conn.cursor() as cursor:
            cursor.execute("TRUNCATE public.users, public.skills, public.jobs CASCADE")
            cursor.execute("DELETE FROM auth.users")
        conn.commit()
    finally:
        conn.close()
    client, mongo = _mongo()
    try:
        # Delete documents only: dropping would discard the bootstrap validator.
        mongo["job_documents"].delete_many({})
    finally:
        client.close()


def skill_ids() -> dict[str, int]:
    conn = _sql()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT name, skill_id FROM public.skills")
            return dict(cursor.fetchall())
    finally:
        conn.close()


def _seed() -> None:
    conn = _sql()
    try:
        with conn.cursor() as cursor:
            for name in SKILLS:
                cursor.execute("INSERT INTO public.skills (name) VALUES (%s)", (name,))
            cursor.execute("SELECT name, skill_id FROM public.skills")
            ids = dict(cursor.fetchall())
            cursor.execute("INSERT INTO auth.users (id) VALUES (%s), (%s)", (str(ANA), str(BEN)))
            cursor.execute(
                "INSERT INTO public.users (user_id, full_name) VALUES (%s, 'Test Student')",
                (str(ANA),),
            )
            for name in ("Python", "Excel"):
                cursor.execute(
                    "INSERT INTO public.user_skills (user_id, skill_id) VALUES (%s, %s)",
                    (str(ANA), ids[name]),
                )
            for n, _, active, _, requirements in JOBS:
                cursor.execute(
                    """
                    INSERT INTO public.jobs
                        (job_id, source, external_job_id, title, company_name,
                         application_url, is_active)
                    VALUES (%s, 'synthetic', %s, 'Synthetic Role', 'Example Co',
                            'https://example.test/jobs', %s)
                    """,
                    (_job_id(n), f"posting-{n}", active),
                )
                # Canonical links with one row per skill and REQUIRED precedence,
                # i.e. what job_skills should hold for the same requirements.
                strength: dict[str, str] = {}
                for item in requirements:
                    if strength.get(item["skill"]) != "REQUIRED":
                        strength[item["skill"]] = item["requirement_type"]
                for name, kind in strength.items():
                    cursor.execute(
                        "INSERT INTO public.job_skills (job_id, skill_id, requirement_type)"
                        " VALUES (%s, %s, %s)",
                        (_job_id(n), ids[name], kind),
                    )
        conn.commit()
    finally:
        conn.close()

    client, mongo = _mongo()
    try:
        mongo["job_documents"].insert_many(
            [
                {
                    "job_id": _job_id(n),
                    "raw_jd": "Synthetic job description.",
                    "extracted_at": datetime(2026, 10, 1, tzinfo=timezone.utc),
                    "extracted_data": {
                        "role_category": role,
                        "responsibilities": [],
                        "requirements": [
                            {
                                "skill_id": ids[item["skill"]],
                                "requirement_type": item["requirement_type"],
                                "minimum_years": item["minimum_years"],
                                "evidence": f"Uses {item['skill']}.",
                            }
                            for item in requirements
                        ],
                        "provider": {"ready": ready, "title": "Synthetic Role"},
                    },
                }
                for n, role, _, ready, requirements in JOBS
            ]
        )
    finally:
        client.close()


def get(path: str, user_id: UUID = ANA) -> httpx.Response:
    from app.auth import AuthenticatedUser, current_user
    from app.main import app

    app.dependency_overrides[current_user] = lambda: AuthenticatedUser(
        user_id=user_id, email="student@example.edu"
    )

    async def send() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get(path)

    try:
        return asyncio.run(send())
    finally:
        app.dependency_overrides.pop(current_user, None)


def gap(role: str, **params: Any) -> dict[str, Any]:
    response = get("/api/me/skill-gap?" + str(httpx.QueryParams({"role_category": role, **params})))
    assert response.status_code == 200, response.text
    return response.json()


def by_name(body: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {row["name"]: row for row in body["skills"]}


def test_fixture_documents_are_checked_by_the_production_validator() -> None:
    client, mongo = _mongo()
    try:
        options = mongo.command("listCollections", filter={"name": "job_documents"})
        info = options["cursor"]["firstBatch"][0]["options"]
        assert info["validationLevel"] == "strict"
        with pytest.raises(WriteError):
            mongo["job_documents"].insert_one({"job_id": _job_id(99), "title": "flat shape"})
    finally:
        client.close()


def test_denominator_is_active_ready_jobs_in_the_role() -> None:
    body = gap(SE)
    # Jobs 1-4. Job 5 (inactive), 6 (not ready) and 7-8 (other role) are excluded,
    # job 4 counts although it has no requirements.
    assert body["sample_size"] == 4
    assert "Go" not in by_name(body)
    assert "Excel" not in by_name(body)


def test_each_skill_counts_once_per_job_and_required_wins() -> None:
    rows = by_name(gap(SE))
    ids = skill_ids()

    assert rows["Python"] == {
        "skill_id": ids["Python"],
        "name": "Python",
        "job_count": 2,  # job 1 lists it twice
        "frequency": 0.5,
        "required_count": 1,  # job 1: REQUIRED beats its own PREFERRED line
        "preferred_count": 1,  # job 2
        "max_minimum_years": 5,
        "years_mentions": 1,  # job 1 only; job 2 states no years
        "user_has": True,
    }
    assert rows["SQL"]["job_count"] == 2
    assert rows["SQL"]["required_count"] == 1  # job 3: REQUIRED listed after PREFERRED
    assert rows["SQL"]["preferred_count"] == 1
    assert rows["SQL"]["max_minimum_years"] == 1.5
    assert rows["SQL"]["years_mentions"] == 1
    assert rows["SQL"]["user_has"] is False
    assert rows["Docker"]["job_count"] == 1
    assert rows["Docker"]["frequency"] == 0.25
    assert rows["Docker"]["max_minimum_years"] == 2


def test_order_summary_and_limit() -> None:
    ids = skill_ids()
    body = gap(SE)
    # job_count desc, then skill_id: Python and SQL tie on 2.
    assert [row["skill_id"] for row in body["skills"]] == [
        ids["Python"],
        ids["SQL"],
        ids["Docker"],
    ]
    assert body["summary"] == {"top_n": 3, "user_has_in_top_n": 1}

    limited = gap(SE, limit=1)
    assert [row["name"] for row in limited["skills"]] == ["Python"]
    assert limited["sample_size"] == 4
    assert limited["summary"] == {"top_n": 1, "user_has_in_top_n": 1}


def test_zero_years_is_a_mention() -> None:
    rows = by_name(gap(DA))
    assert rows["Excel"]["max_minimum_years"] == 0
    assert rows["Excel"]["years_mentions"] == 1
    assert rows["Excel"]["user_has"] is True


EMPTY_SUMMARY = {"top_n": 0, "user_has_in_top_n": 0}


def test_role_with_no_active_ready_posting_is_empty_not_an_error() -> None:
    assert gap(DESIGN) == {
        "role_category": DESIGN,
        "sample_size": 0,
        "skills": [],
        "summary": EMPTY_SUMMARY,
    }


def test_role_with_ready_jobs_but_no_requirements_has_a_sample_and_no_skills() -> None:
    body = gap(CY)
    assert body["sample_size"] == 2
    assert body["skills"] == []


@pytest.mark.parametrize("role", ["Underwater Basket Weaving", "", "software engineering"])
def test_unknown_role_is_the_same_empty_result(role: str) -> None:
    # Exact match: a different case is a different (unknown) role.
    assert gap(role) == {
        "role_category": role,
        "sample_size": 0,
        "skills": [],
        "summary": EMPTY_SUMMARY,
    }


def test_no_profile_is_not_found_profile() -> None:
    response = get("/api/me/skill-gap?role_category=Software%20Engineering", user_id=BEN)
    assert response.status_code == 404
    assert response.json()["error"]["details"] == {"resource": "profile"}


def test_roles_count_active_ready_jobs_by_count_then_name() -> None:
    response = get("/api/skill-gap/roles")
    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {"role_category": SE, "job_count": 4},
            {"role_category": CY, "job_count": 2},
            {"role_category": DA, "job_count": 2},
        ]
    }


COUNT_FIELDS = {
    "skill_id",
    "name",
    "job_count",
    "frequency",
    "required_count",
    "preferred_count",
    "user_has",
}


def _both_engines(role: str):
    from app.db import get_db
    from app.skill_gap import role_job_ids, skill_gap_mongo, skill_gap_sql
    from app.sql_access import get_active_job_ids

    db = get_db()
    active = get_active_job_ids()
    mongo = skill_gap_mongo(db, active, role, ANA)
    sql = skill_gap_sql(role_job_ids(db, active, role), ANA)
    return mongo, sql


@pytest.mark.parametrize("role", [SE, DA, CY, DESIGN, "Unknown"])
def test_engines_agree_on_normalised_job_skills_links(role: str) -> None:
    """Engine parity on job_skills seeded by _seed() with REQUIRED precedence applied.

    This proves the two queries count the same way. It does NOT prove production
    ingestion writes such links: see the xfail test below.
    """
    (mongo_sample, mongo_rows), (sql_sample, sql_rows) = _both_engines(role)

    assert sql_sample == mongo_sample
    assert [row.model_dump(include=COUNT_FIELDS) for row in sql_rows] == [
        row.model_dump(include=COUNT_FIELDS) for row in mongo_rows
    ]
    if role == SE:
        assert sql_sample == 4 and len(sql_rows) == 3


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,  # any other error (e.g. the resync failing) is a real failure
    reason="sql_access._replace_job_skills is last-wins; PRD §4 says REQUIRED wins"
    " — open question for Zhihao",
)
def test_engines_agree_when_links_come_from_production_sync() -> None:
    """Job 1 lists Python REQUIRED then PREFERRED; resync its links the production way."""
    from app.sql_access import replace_job_skills

    client, mongo = _mongo()
    try:
        document = mongo["job_documents"].find_one({"job_id": _job_id(1)})
    finally:
        client.close()
    replace_job_skills(_job_id(1), document["extracted_data"]["requirements"])

    (_, mongo_rows), (_, sql_rows) = _both_engines(SE)
    python = skill_ids()["Python"]
    mongo_required = next(row.required_count for row in mongo_rows if row.skill_id == python)
    sql_required = next(row.required_count for row in sql_rows if row.skill_id == python)
    assert mongo_required == 1
    assert sql_required == mongo_required
