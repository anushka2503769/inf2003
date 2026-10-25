"""Skill-gap routes (docs/API.md section 8) with fake Mongo and SQL.

No database is involved: the job read dependency is overridden with a fake
Mongo handle, the active-id lookup and the SQL name/user-skill step are
patched. These pin the HTTP contract (shapes, validation, the no-profile 404,
the empty-role 200). The real pipeline runs against disposable databases in
tests/test_skill_gap_db.py.
"""

import asyncio
from collections.abc import Iterator
from typing import Any
from uuid import UUID

import httpx
import pytest

from app import skill_gap
from app.routers import skill_gap as skill_gap_router

ANA = UUID("11111111-1111-4111-8111-111111111111")
ACTIVE = ["aaaaaaaa-0000-4000-8000-000000000001", "aaaaaaaa-0000-4000-8000-000000000002"]

ROW_KEYS = {
    "skill_id",
    "name",
    "job_count",
    "frequency",
    "required_count",
    "preferred_count",
    "max_minimum_years",
    "years_mentions",
    "user_has",
}


class _Collection:
    def __init__(self, result: list[dict[str, Any]]) -> None:
        self.result = result
        self.pipelines: list[list[dict[str, Any]]] = []

    def aggregate(self, pipeline: list[dict[str, Any]]) -> Iterator[dict[str, Any]]:
        self.pipelines.append(pipeline)
        return iter(self.result)


class _Mongo:
    def __init__(self, collection: _Collection) -> None:
        self.collection = collection

    def __getitem__(self, name: str) -> _Collection:
        assert name == "job_documents"
        return self.collection


FACET = [
    {
        "sample": [{"jobs": 4}],
        "skills": [
            {
                "_id": 1,
                "job_count": 2,
                "required_count": 1,
                "max_years": 5,
                "years_mentions": 1,
            },
            {
                "_id": 2,
                "job_count": 2,
                "required_count": 1,
                "max_years": 1.5,
                "years_mentions": 1,
            },
            {
                "_id": 3,
                "job_count": 1,
                "required_count": 1,
                "max_years": None,
                "years_mentions": 0,
            },
        ],
    }
]


@pytest.fixture
def fakes(monkeypatch: pytest.MonkeyPatch):
    """Install a fake job database and SQL lookups; yield the fake collection."""
    state: dict[str, Any] = {"collection": _Collection(FACET), "profile": True}
    monkeypatch.setattr(skill_gap_router, "get_active_job_ids", lambda: set(ACTIVE))

    def lookup(user_id: UUID, skill_ids: list[int]):
        state["lookup_ids"] = list(skill_ids)
        if not state["profile"]:
            return None
        names = {1: "Python", 2: "SQL", 3: "Docker"}
        return {i: names[i] for i in skill_ids if i in names}, {1}

    monkeypatch.setattr(skill_gap, "skill_names_and_user_skills", lookup)
    return state


def call(path: str, state: dict[str, Any] | None, user_id: UUID | None = ANA) -> httpx.Response:
    from app.auth import AuthenticatedUser, current_user
    from app.dependencies import get_authenticated_job_db
    from app.main import app

    if user_id is not None:
        app.dependency_overrides[current_user] = lambda: AuthenticatedUser(
            user_id=user_id, email="student@example.edu"
        )
    if state is not None:
        app.dependency_overrides[get_authenticated_job_db] = lambda: _Mongo(state["collection"])

    async def send() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get(path)

    try:
        return asyncio.run(send())
    finally:
        app.dependency_overrides.pop(current_user, None)
        app.dependency_overrides.pop(get_authenticated_job_db, None)


def test_skill_gap_requires_a_token() -> None:
    response = call("/api/me/skill-gap?role_category=x", None, user_id=None)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


def test_roles_require_a_token() -> None:
    response = call("/api/skill-gap/roles", None, user_id=None)
    assert response.status_code == 401


def test_skill_gap_shape_matches_the_contract(fakes) -> None:
    response = call("/api/me/skill-gap?role_category=Software%20Engineering", fakes)

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"role_category", "sample_size", "skills", "summary"}
    assert body["role_category"] == "Software Engineering"
    assert body["sample_size"] == 4
    assert all(set(row) == ROW_KEYS for row in body["skills"])
    assert body["skills"][0] == {
        "skill_id": 1,
        "name": "Python",
        "job_count": 2,
        "frequency": 0.5,
        "required_count": 1,
        "preferred_count": 1,
        "max_minimum_years": 5,
        "years_mentions": 1,
        "user_has": True,
    }
    assert [row["skill_id"] for row in body["skills"]] == [1, 2, 3]
    assert body["skills"][1]["max_minimum_years"] == 1.5
    assert body["skills"][2]["max_minimum_years"] is None
    assert body["skills"][2]["frequency"] == 0.25
    assert body["summary"] == {"top_n": 3, "user_has_in_top_n": 1}


def test_pipeline_filters_active_ready_role_and_uses_facet(fakes) -> None:
    call("/api/me/skill-gap?role_category=Software%20Engineering", fakes)

    pipeline = fakes["collection"].pipelines[0]
    assert pipeline[0] == {
        "$match": {
            "job_id": {"$in": sorted(ACTIVE)},
            "extracted_data.role_category": "Software Engineering",
            "extracted_data.provider.ready": "true",
        }
    }
    assert set(pipeline[1]["$facet"]) == {"sample", "skills"}
    assert fakes["lookup_ids"] == [1, 2, 3]


def test_limit_truncates_skills_and_summary(fakes) -> None:
    response = call("/api/me/skill-gap?role_category=SE&limit=1", fakes)
    body = response.json()
    assert [row["skill_id"] for row in body["skills"]] == [1]
    assert body["summary"] == {"top_n": 1, "user_has_in_top_n": 1}


def test_empty_match_returns_zero_sample_not_an_error(fakes) -> None:
    # $facet with $count yields [] (not [{jobs: 0}]) when nothing matched.
    fakes["collection"] = _Collection([{"sample": [], "skills": []}])
    response = call("/api/me/skill-gap?role_category=Nobody%20Hires%20This", fakes)

    assert response.status_code == 200
    assert response.json() == {
        "role_category": "Nobody Hires This",
        "sample_size": 0,
        "skills": [],
        "summary": {"top_n": 0, "user_has_in_top_n": 0},
    }


def test_empty_role_string_is_an_empty_result(fakes) -> None:
    fakes["collection"] = _Collection([{"sample": [], "skills": []}])
    response = call("/api/me/skill-gap?role_category=", fakes)
    assert response.status_code == 200
    assert response.json()["sample_size"] == 0
    assert response.json()["skills"] == []


def test_skill_missing_from_dictionary_is_dropped(fakes) -> None:
    fakes["collection"] = _Collection(
        [
            {
                "sample": [{"jobs": 1}],
                "skills": [
                    {
                        "_id": 99,
                        "job_count": 1,
                        "required_count": 1,
                        "max_years": None,
                        "years_mentions": 0,
                    }
                ],
            }
        ]
    )
    body = call("/api/me/skill-gap?role_category=SE", fakes).json()
    assert body["sample_size"] == 1
    assert body["skills"] == []


def test_no_profile_is_not_found_profile(fakes) -> None:
    fakes["profile"] = False
    response = call("/api/me/skill-gap?role_category=SE", fakes)

    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "not_found"
    assert error["details"] == {"resource": "profile"}


@pytest.mark.parametrize(
    ("query", "field"),
    [
        ("", "role_category"),
        ("?limit=5", "role_category"),
        ("?role_category=SE&limit=0", "limit"),
        ("?role_category=SE&limit=101", "limit"),
        ("?role_category=SE&limit=ten", "limit"),
        ("?role_category=" + "r" * 101, "role_category"),
        ("?role_category=SE&offset=3", "offset"),
    ],
)
def test_invalid_query_is_rejected(fakes, query: str, field: str) -> None:
    response = call(f"/api/me/skill-gap{query}", fakes)

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_failed"
    assert error["details"] == {"field": field}


def test_role_category_of_exactly_100_characters_is_accepted(fakes) -> None:
    response = call("/api/me/skill-gap?role_category=" + "r" * 100, fakes)
    assert response.status_code == 200


def test_roles_shape_and_order(fakes) -> None:
    fakes["collection"] = _Collection(
        [
            {"_id": "Software Engineering", "job_count": 4},
            {"_id": "Cybersecurity", "job_count": 2},
            {"_id": "Data Analytics", "job_count": 2},
        ]
    )
    response = call("/api/skill-gap/roles", fakes)

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {"role_category": "Software Engineering", "job_count": 4},
            {"role_category": "Cybersecurity", "job_count": 2},
            {"role_category": "Data Analytics", "job_count": 2},
        ]
    }
    pipeline = fakes["collection"].pipelines[0]
    assert pipeline[0] == {
        "$match": {
            "job_id": {"$in": sorted(ACTIVE)},
            "extracted_data.provider.ready": "true",
        }
    }
    assert pipeline[-1] == {"$sort": {"job_count": -1, "_id": 1}}


def test_roles_reject_unknown_parameters(fakes) -> None:
    response = call("/api/skill-gap/roles?limit=5", fakes)
    assert response.status_code == 422
    assert response.json()["error"]["details"] == {"field": "limit"}


def test_roles_empty_when_nothing_is_ready(fakes) -> None:
    fakes["collection"] = _Collection([])
    response = call("/api/skill-gap/roles", fakes)
    assert response.status_code == 200
    assert response.json() == {"items": []}
