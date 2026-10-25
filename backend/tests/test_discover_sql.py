"""Discover ranking (docs/API.md section 7) against a real PostgreSQL database.

Skipped unless TEST_DATABASE_URL is set (see tests/test_sql_profile.py). The
database must be throwaway with 001 and 003 applied: fixtures truncate the
application tables. Use backend/scripts/run_disposable_db_tests.sh.

The fixture below is small enough to rank by hand. Every expected order in
this file is written out literally rather than recomputed, so a change to the
ranking rule shows up as a failing list, not as a silently agreeing helper.
"""

import os
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import psycopg2
import pytest

from app.sql_discover import (
    DISCOVER_SQL,
    DiscoverFilters,
    DiscoverProfileMissing,
    PostgresDiscoverStore,
    query_parameters,
)

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "").strip()

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="Set TEST_DATABASE_URL to a throwaway PostgreSQL database to run these.",
)

ANA = UUID("11111111-1111-4111-8111-111111111111")
BEN = UUID("22222222-2222-4222-8222-222222222222")
NOBODY = UUID("33333333-3333-4333-8333-333333333333")

# Ana knows Python, SQL, Git and Docker. Ben knows only Java.
SKILLS = ["Python", "SQL", "Git", "Docker", "Java", "React", "AWS", "Kubernetes"]
USER_SKILLS = {ANA: ["Python", "SQL", "Git", "Docker"], BEN: ["Java"]}


def _uuid(n: int) -> str:
    return f"00000000-0000-4000-8000-{n:012d}"


# J4 deliberately has a smaller job_id than J3 although it is inserted later,
# so the job_id tie-break cannot pass by accident of insertion order.
JOB_IDS = {
    "J1": _uuid(10),
    "J2": _uuid(20),
    "J3": _uuid(40),
    "J4": _uuid(30),
    "J5": _uuid(50),
    "J6": _uuid(60),
    "J7": _uuid(70),
    "J8": _uuid(80),
    "J9": _uuid(90),
    "J10": _uuid(100),
    "J11": _uuid(110),
    "J12": _uuid(120),
}
NAME_BY_ID = {job_id: name for name, job_id in JOB_IDS.items()}


def _day(day: int) -> datetime:
    return datetime(2026, 10, day, 9, 0, tzinfo=UTC)


# name: (title, company, location, job_type, work_arrangement, posted, active,
#        REQUIRED skills, PREFERRED skills)
# fmt: off
JOBS = {
    # coverage 2/2, preferred 1/1
    "J1": (
        "Data Analyst Intern", "Acme", "Singapore", "INTERNSHIP", "REMOTE",
        _day(1), True, ["Python", "SQL"], ["Git"],
    ),
    # coverage 2/2, preferred 0/1, newer than J12
    "J2": (
        "Data Engineer Intern", "Beta", "Remote - Singapore", "INTERNSHIP", "HYBRID",
        _day(20), True, ["Python", "SQL"], ["Java"],
    ),
    # coverage 1/2, preferred 2/2, same date as J4: tie, broken by job_id
    "J3": (
        "Backend Developer", "Gamma Data", "100% Remote", "FULL_TIME", "REMOTE",
        _day(5), True, ["Python", "Java"], ["Git", "Docker"],
    ),
    "J4": (
        "Backend Intern", "Delta", "Block_A Jurong", "INTERNSHIP", "REMOTE",
        _day(5), True, ["Python", "Java"], ["Git", "Docker"],
    ),
    # same keys as J3/J4 except no posted date: NULLS LAST puts it after them
    "J5": (
        "Frontend Intern", "Epsilon", "Singapore", "INTERNSHIP", "ONSITE",
        None, True, ["Python", "Java"], ["Git", "Docker"],
    ),
    # coverage 0/2 although it is the newest scored job
    "J6": (
        "Data Steward", "Zeta", "singapore", "PART_TIME", "REMOTE",
        _day(25), True, ["Java", "React"], ["Git"],
    ),
    # coverage 1/4
    "J7": (
        "ML Intern", "Eta", None, "INTERNSHIP", "REMOTE",
        _day(2), True, ["Java", "React", "AWS", "Python"], ["Kubernetes"],
    ),
    # no requirements at all: coverage null, newest of all, still last
    "J8": (
        "Data Intern", "Theta", "Singapore", "INTERNSHIP", "REMOTE",
        _day(26), True, [], [],
    ),
    # only PREFERRED skills: coverage null, but one preferred match beats J8
    "J9": (
        "Ops Intern", "Iota", None, "INTERNSHIP", None,
        _day(3), True, [], ["Python"],
    ),
    # inactive: would rank first, must never appear
    "J10": (
        "Data Platform Intern", "Kappa", "Singapore", "INTERNSHIP", "REMOTE",
        _day(21), False, ["Python"], [],
    ),
    # reviewed by Ana: would rank first, must never appear for Ana
    "J11": (
        "Data Science Intern", "Lambda", "Singapore", "INTERNSHIP", "REMOTE",
        _day(22), True, ["Python"], [],
    ),
    # tracked by Ben only: still in Ana's feed
    "J12": (
        "Analyst", "Mu", "Singapore", "INTERNSHIP", "REMOTE",
        _day(10), True, ["SQL"], [],
    ),
}
# fmt: on

TRACKER = [(ANA, "J11", "NOT_INTERESTED"), (BEN, "J12", "SAVED")]

# Hand-ranked for Ana:
#   coverage 1.0  J1 (pref 1) > J2 (pref 0, 20 Oct) > J12 (pref 0, 10 Oct)
#   coverage 0.5  J4 = J3 (pref 2, 5 Oct; J4 has the smaller job_id) > J5 (no date)
#   coverage 0.25 J7
#   coverage 0.0  J6
#   coverage null J9 (pref 1) > J8 (pref 0)
EXPECTED_ORDER = ["J1", "J2", "J12", "J4", "J3", "J5", "J7", "J6", "J9", "J8"]
EXPECTED_RANKS = [1, 2, 3, 4, 4, 6, 7, 8, 9, 10]


def _open():
    return psycopg2.connect(TEST_DATABASE_URL)


def _reset() -> None:
    conn = _open()
    try:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE public.users, public.jobs, public.skills CASCADE")
            cur.execute("DELETE FROM auth.users")
        conn.commit()
    finally:
        conn.close()


def _seed() -> None:
    conn = _open()
    try:
        with conn.cursor() as cur:
            skill_ids = {}
            for name in SKILLS:
                cur.execute(
                    "INSERT INTO public.skills (name) VALUES (%s) RETURNING skill_id", (name,)
                )
                skill_ids[name] = cur.fetchone()[0]
            for user_id, names in USER_SKILLS.items():
                cur.execute("INSERT INTO auth.users (id) VALUES (%s)", (str(user_id),))
                cur.execute(
                    "INSERT INTO public.users (user_id, full_name) VALUES (%s, 'Synthetic')",
                    (str(user_id),),
                )
                for name in names:
                    cur.execute(
                        "INSERT INTO public.user_skills VALUES (%s, %s)",
                        (str(user_id), skill_ids[name]),
                    )
            for name, row in JOBS.items():
                req, pref = row[7], row[8]
                cur.execute(
                    """
                    INSERT INTO public.jobs
                        (job_id, source, external_job_id, title, company_name, location,
                         job_type, work_arrangement, application_url, source_posted_at,
                         is_active)
                    VALUES (%s, 'synthetic', %s, %s, %s, %s, %s, %s,
                            'https://example.test/apply', %s, %s)
                    """,
                    (JOB_IDS[name], name, *row[:7]),
                )
                for kind, skill_names in (("REQUIRED", req), ("PREFERRED", pref)):
                    for skill in skill_names:
                        cur.execute(
                            "INSERT INTO public.job_skills VALUES (%s, %s, %s)",
                            (JOB_IDS[name], skill_ids[skill], kind),
                        )
            for user_id, job, status in TRACKER:
                cur.execute(
                    "INSERT INTO public.user_jobs (user_id, job_id, status) VALUES (%s, %s, %s)",
                    (str(user_id), JOB_IDS[job], status),
                )
        conn.commit()
    finally:
        conn.close()


@pytest.fixture(autouse=True)
def database(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    from app import config

    config.get_settings.cache_clear()
    _reset()
    _seed()
    yield
    _reset()
    config.get_settings.cache_clear()


def _track(user_id: UUID, job: str, status: str) -> None:
    conn = _open()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO public.user_jobs (user_id, job_id, status) VALUES (%s, %s, %s)",
                (str(user_id), JOB_IDS[job], status),
            )
        conn.commit()
    finally:
        conn.close()


def feed(user_id: UUID = ANA, limit: int = 50, offset: int = 0, **filters):
    return PostgresDiscoverStore().feed(user_id, DiscoverFilters(**filters), limit, offset)


def names(response) -> list[str]:
    return [NAME_BY_ID[item.job.job_id] for item in response.items]


# --- ranking ---------------------------------------------------------------


def test_feed_order_is_deterministic_and_matches_hand_ranking() -> None:
    response = feed()
    assert names(response) == EXPECTED_ORDER
    assert [item.rank for item in response.items] == EXPECTED_RANKS
    assert response.has_more is False
    # Same answer on a second run: the order does not depend on plan or timing.
    assert names(feed()) == EXPECTED_ORDER


def test_counts_and_coverage_values() -> None:
    by_name = {NAME_BY_ID[item.job.job_id]: item.match for item in feed().items}
    j3 = by_name["J3"]
    assert (j3.required_total, j3.required_matched) == (2, 1)
    assert (j3.preferred_total, j3.preferred_matched) == (2, 2)
    assert j3.coverage == pytest.approx(0.5)
    assert by_name["J7"].coverage == pytest.approx(0.25)
    assert by_name["J6"].coverage == 0
    assert by_name["J1"].coverage == 1


def test_job_without_requirements_has_null_coverage_and_sorts_last() -> None:
    items = feed().items
    by_name = {NAME_BY_ID[item.job.job_id]: item for item in items}
    for name in ("J8", "J9"):
        match = by_name[name].match
        assert match.required_total == 0
        assert match.coverage is None
    assert by_name["J9"].match.preferred_matched == 1
    assert by_name["J8"].match.matched_skills == []
    assert by_name["J8"].match.missing_skills == []
    scored = [item.rank for item in items if item.match.coverage is not None]
    unscored = [item.rank for item in items if item.match.coverage is None]
    assert max(scored) < min(unscored)


def test_matched_and_missing_lists_are_required_first_then_by_name() -> None:
    by_name = {NAME_BY_ID[item.job.job_id]: item.match for item in feed().items}

    def pairs(skills):
        return [(s.name, s.requirement_type) for s in skills]

    assert pairs(by_name["J3"].matched_skills) == [
        ("Python", "REQUIRED"),
        ("Docker", "PREFERRED"),
        ("Git", "PREFERRED"),
    ]
    assert pairs(by_name["J3"].missing_skills) == [("Java", "REQUIRED")]
    assert pairs(by_name["J7"].matched_skills) == [("Python", "REQUIRED")]
    assert pairs(by_name["J7"].missing_skills) == [
        ("AWS", "REQUIRED"),
        ("Java", "REQUIRED"),
        ("React", "REQUIRED"),
        ("Kubernetes", "PREFERRED"),
    ]
    assert all(isinstance(s.skill_id, int) for s in by_name["J7"].missing_skills)


def test_job_summary_fields() -> None:
    first = feed().items[0].job
    assert first.job_id == JOB_IDS["J1"]
    assert first.title == "Data Analyst Intern"
    assert first.company_name == "Acme"
    assert first.location == "Singapore"
    assert first.job_type == "INTERNSHIP"
    assert first.work_arrangement == "REMOTE"
    assert first.application_url == "https://example.test/apply"
    assert first.source == "synthetic"
    assert first.source_posted_at == _day(1)
    assert first.is_active is True


# --- exclusions ------------------------------------------------------------


def test_inactive_jobs_never_appear() -> None:
    assert "J10" not in names(feed())
    assert "J10" not in names(feed(BEN))
    assert "J10" not in names(feed(q="Data Platform"))


@pytest.mark.parametrize(
    "status", ["NOT_INTERESTED", "SAVED", "APPLIED", "INTERVIEW", "REJECTED", "OFFER"]
)
def test_reviewed_jobs_never_appear_whatever_the_status(status: str) -> None:
    _track(ANA, "J1", status)
    remaining = names(feed())
    assert "J1" not in remaining and "J11" not in remaining
    assert remaining == [name for name in EXPECTED_ORDER if name != "J1"]


def test_another_users_tracker_rows_do_not_hide_jobs() -> None:
    assert "J12" in names(feed(ANA))
    ben = names(feed(BEN))
    assert "J12" not in ben
    assert "J11" in ben  # Ana's review hides J11 for Ana only


def test_ranking_uses_the_callers_own_skills() -> None:
    ben = {NAME_BY_ID[item.job.job_id]: item.match for item in feed(BEN).items}
    assert ben["J6"].coverage == pytest.approx(0.5)  # Ben knows Java
    assert ben["J1"].coverage == 0
    assert names(feed(BEN))[0] == "J6"


def test_no_profile_raises() -> None:
    with pytest.raises(DiscoverProfileMissing):
        feed(NOBODY)


# --- filters ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("filters", "expected"),
    [
        ({"job_type": "FULL_TIME"}, ["J3"]),
        ({"job_type": "PART_TIME"}, ["J6"]),
        ({"work_arrangement": "HYBRID"}, ["J2"]),
        ({"work_arrangement": "ONSITE"}, ["J5"]),
        # case-insensitive substring; J6's "singapore" is lowercase
        ({"location": "SINGAPORE"}, ["J1", "J2", "J12", "J5", "J6", "J8"]),
        # q matches title or company ("Gamma Data")
        ({"q": "data"}, ["J1", "J2", "J3", "J6", "J8"]),
        ({"q": "gamma"}, ["J3"]),
        # filters combine with AND
        (
            {"job_type": "INTERNSHIP", "work_arrangement": "REMOTE", "location": "singapore"},
            ["J1", "J12", "J8"],
        ),
        (
            {
                "job_type": "INTERNSHIP",
                "work_arrangement": "REMOTE",
                "location": "singapore",
                "q": "data",
            },
            ["J1", "J8"],
        ),
        ({"job_type": "FULL_TIME", "q": "intern"}, []),
    ],
)
def test_filters(filters: dict, expected: list[str]) -> None:
    assert names(feed(**filters)) == expected


def test_location_wildcards_are_literal() -> None:
    # As LIKE operators these would match every non-null location.
    assert names(feed(location="%")) == ["J3"]  # "100% Remote"
    assert names(feed(location="_")) == ["J4"]  # "Block_A Jurong"
    assert names(feed(location="k_A")) == ["J4"]
    assert names(feed(location="0%_")) == []
    assert names(feed(location="\\")) == []


def test_q_wildcards_are_literal() -> None:
    assert names(feed(q="%")) == []
    assert names(feed(q="_")) == []


def test_ranks_stay_global_under_a_filter() -> None:
    response = feed(job_type="INTERNSHIP", work_arrangement="REMOTE")
    # J1, J12, J4, J7, J8 after filtering; RANK() is over the filtered feed.
    assert names(response) == ["J1", "J12", "J4", "J7", "J8"]
    assert [item.rank for item in response.items] == [1, 2, 3, 4, 5]


# --- pagination ------------------------------------------------------------


def test_pagination_is_stable_and_ranks_are_global() -> None:
    pages = [feed(limit=4, offset=offset) for offset in (0, 4, 8)]
    assert [names(page) for page in pages] == [
        ["J1", "J2", "J12", "J4"],
        ["J3", "J5", "J7", "J6"],
        ["J9", "J8"],
    ]
    assert [page.has_more for page in pages] == [True, True, False]
    # J4 and J3 tie at rank 4 across the page boundary.
    assert [item.rank for page in pages for item in page.items] == EXPECTED_RANKS


def test_has_more_is_false_on_an_exact_final_page() -> None:
    assert feed(limit=10).has_more is False
    assert feed(limit=9).has_more is True
    assert feed(limit=5, offset=10).items == []


# --- plan ------------------------------------------------------------------


def test_explain_analyze_uses_anti_join_and_window() -> None:
    """The plan shows the NOT EXISTS anti-join and the RANK() window.

    With WRITE_PERF_ARTIFACTS=1 the plan is also written to docs/perf/ for
    WP-10. Without it nothing is written, so a normal run leaves docs alone.
    """
    params = query_parameters(ANA, DiscoverFilters(), limit=21, offset=0)
    conn = _open()
    try:
        with conn.cursor() as cur:
            cur.execute("ANALYZE")
            cur.execute("EXPLAIN (ANALYZE, BUFFERS) " + DISCOVER_SQL, params)
            plan = "\n".join(row[0] for row in cur.fetchall())
            cur.execute("SHOW server_version")
            version = cur.fetchone()[0]
    finally:
        conn.rollback()
        conn.close()

    assert "Anti Join" in plan
    assert "WindowAgg" in plan

    if os.environ.get("WRITE_PERF_ARTIFACTS") == "1":
        target = Path(__file__).resolve().parents[2] / "docs/perf/discover-explain-fixture.txt"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            "Discover query (backend/app/sql_discover.py DISCOVER_SQL)\n"
            "EXPLAIN (ANALYZE, BUFFERS), disposable PostgreSQL "
            f"{version}, migrations 001 + 003.\n"
            "Fixture: backend/tests/test_discover_sql.py (12 jobs, 8 skills, 2 users);\n"
            "caller ANA, no filters, limit 20 (+1 for has_more), offset 0.\n"
            "Regenerate: WRITE_PERF_ARTIFACTS=1 bash backend/scripts/run_disposable_db_tests.sh\n"
            "Timings are from a tiny synthetic fixture; WP-10 measures at scale.\n\n"
            f"{plan}\n",
            encoding="utf-8",
        )
