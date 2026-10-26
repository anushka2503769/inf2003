"""WP-6 resume routes with fakes for Mongo and SQL (no database, no real resumes).

Covers docs/API.md section 5: the profile check happens before extraction,
extracted names are mapped to dictionary ids, and GET /api/me/resume.
"""

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime
from io import BytesIO
from typing import Any
from uuid import UUID

import httpx
import pytest
from bson import ObjectId
from docx import Document

from app import resumes
from app.auth import AuthenticatedUser, current_user
from app.dependencies import get_authenticated_db
from app.main import app
from app.schemas import Skill
from app.skills_repository import SkillsRepositoryError
from app.sql_access import SqlAccessError, SqlParentMissing

ANA = UUID("11111111-1111-4111-8111-111111111111")
BEN = UUID("22222222-2222-4222-8222-222222222222")
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

DICTIONARY = [(1, "Python"), (2, "SQL"), (3, "Java"), (4, "Git"), (5, "C++")]


class FakeCollection:
    def __init__(self, documents: list[dict[str, Any]] | None = None) -> None:
        self.documents = documents or []
        self.filters: list[dict[str, Any]] = []

    def find_one(self, filter_: dict[str, Any]) -> dict[str, Any] | None:
        self.filters.append(filter_)
        for document in self.documents:
            if all(document.get(key) == value for key, value in filter_.items()):
                return document
        return None


class FakeDatabase:
    def __init__(self, collection: FakeCollection) -> None:
        self.collection = collection

    def __getitem__(self, name: str) -> FakeCollection:
        assert name == "resume_documents"
        return self.collection


def _docx_bytes(text: str = "Synthetic Student\nSkills: placeholder") -> bytes:
    document = Document()
    for line in text.split("\n"):
        document.add_paragraph(line)
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


class World:
    """Everything the upload route touches, recorded in call order."""

    def __init__(self) -> None:
        self.events: list[str] = []
        self.profile = True
        self.extracted_names: list[str] = ["Python"]
        self.confirmed: list[Skill] = []
        self.stored: list[dict[str, Any]] = []
        self.collection = FakeCollection()


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch) -> Iterator[World]:
    state = World()

    def ensure_user(user_id: str) -> None:
        state.events.append("profile")
        if not state.profile:
            raise SqlParentMissing("SQL user does not exist.")

    def extract_text(file_bytes: bytes, file_kind: str) -> str:
        state.events.append("extract_text")
        return "synthetic resume text"

    def extract_fields(raw_text: str) -> dict[str, Any]:
        state.events.append("extract_fields")
        return {
            "skills": state.extracted_names,
            "education": [],
            "experience": [],
            "projects": [],
        }

    def replace(db: Any, document: dict[str, Any]) -> dict[str, Any]:
        state.events.append("store")
        saved = {**document, "_id": ObjectId("507f1f77bcf86cd799439011")}
        state.stored.append(saved)
        return saved

    monkeypatch.setattr(resumes, "ensure_sql_user_exists", ensure_user)
    monkeypatch.setattr(resumes, "extract_raw_text", extract_text)
    monkeypatch.setattr(resumes, "extract_structured_fields", extract_fields)
    monkeypatch.setattr(resumes, "replace_current_resume", replace)
    monkeypatch.setattr(resumes, "get_all_skills", lambda: DICTIONARY)
    monkeypatch.setattr(resumes, "confirmed_skills", lambda user_id: state.confirmed)

    app.dependency_overrides[current_user] = lambda: AuthenticatedUser(
        user_id=ANA, email="ana@example.test"
    )
    app.dependency_overrides[get_authenticated_db] = lambda: FakeDatabase(state.collection)
    yield state
    app.dependency_overrides.pop(current_user, None)
    app.dependency_overrides.pop(get_authenticated_db, None)


def _call(method: str, path: str, **kwargs: Any) -> httpx.Response:
    async def run() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.request(method, path, **kwargs)

    return asyncio.run(run())


def _upload(name: str = "synthetic.docx", content: bytes | None = None) -> httpx.Response:
    data = _docx_bytes() if content is None else content
    return _call("POST", "/api/resumes/upload", files={"file": (name, data, DOCX)})


def test_upload_checks_profile_before_extraction(world: World) -> None:
    world.profile = False
    response = _upload()
    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "not_found"
    assert error["details"] == {"resource": "profile"}
    # Extraction (text and skill matching) never ran, and nothing was stored.
    assert world.events == ["profile"]
    assert world.stored == []


def test_upload_runs_profile_check_then_extraction_then_store(world: World) -> None:
    assert _upload().status_code == 200
    assert world.events == ["profile", "extract_text", "extract_fields", "store"]


def test_upload_maps_names_case_insensitively_ordered_by_name(world: World) -> None:
    world.extracted_names = ["sql", "PYTHON", "Git"]
    body = _upload().json()
    assert body["suggested_skills"] == [
        {"skill_id": 4, "name": "Git"},
        {"skill_id": 1, "name": "Python"},
        {"skill_id": 2, "name": "SQL"},
    ]
    assert body["extracted_data"]["skills"] == ["sql", "PYTHON", "Git"]


def test_upload_drops_unknown_names(world: World) -> None:
    world.extracted_names = ["Python", "Cobol", "Underwater Basket Weaving"]
    assert _upload().json()["suggested_skills"] == [{"skill_id": 1, "name": "Python"}]


def test_upload_excludes_already_confirmed_skills(world: World) -> None:
    world.extracted_names = ["Python", "SQL", "Java"]
    world.confirmed = [Skill(skill_id=2, name="SQL")]
    names = [skill["name"] for skill in _upload().json()["suggested_skills"]]
    assert names == ["Java", "Python"]


def test_upload_suggestions_have_no_duplicates(world: World) -> None:
    world.extracted_names = ["Python", "python", "PYTHON", "Python"]
    assert _upload().json()["suggested_skills"] == [{"skill_id": 1, "name": "Python"}]


def test_upload_handles_names_with_symbols(world: World) -> None:
    world.extracted_names = ["c++"]
    assert _upload().json()["suggested_skills"] == [{"skill_id": 5, "name": "C++"}]


def test_upload_with_nothing_to_suggest_returns_empty_list(world: World) -> None:
    world.extracted_names = []
    assert _upload().json()["suggested_skills"] == []


def test_upload_rejects_unsupported_file_type(world: World) -> None:
    response = _call(
        "POST", "/api/resumes/upload", files={"file": ("notes.txt", b"hello", "text/plain")}
    )
    assert response.status_code == 415
    assert world.events == []


def test_upload_rejects_oversize_file(world: World) -> None:
    response = _upload(content=b"x" * (resumes.MAX_FILE_SIZE_BYTES + 1))
    assert response.status_code == 413
    assert world.events == []


def _stored_document(user_id: UUID, skills: list[str]) -> dict[str, Any]:
    return {
        "_id": ObjectId("507f1f77bcf86cd799439011"),
        "user_id": str(user_id),
        "file_name": "synthetic.docx",
        "raw_text": "synthetic",
        "extracted_data": {
            "skills": skills,
            "education": [],
            "experience": [],
            "projects": [],
        },
        "uploaded_at": datetime(2026, 10, 20, 8, 30, tzinfo=UTC),
    }


def test_get_my_resume_returns_current_resume_with_suggestions(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    world.collection.documents = [
        _stored_document(BEN, ["Java"]),
        _stored_document(ANA, ["python", "SQL", "Cobol"]),
    ]
    world.confirmed = [Skill(skill_id=2, name="SQL")]
    response = _call("GET", "/api/me/resume")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "resume_id",
        "user_id",
        "file_name",
        "uploaded_at",
        "extracted_data",
        "suggested_skills",
    }
    assert body["user_id"] == str(ANA)
    assert body["file_name"] == "synthetic.docx"
    assert body["suggested_skills"] == [{"skill_id": 1, "name": "Python"}]
    # The lookup is scoped to the verified caller.
    assert world.collection.filters == [{"user_id": str(ANA)}]


def test_get_my_resume_is_404_resume_when_none_uploaded(world: World) -> None:
    world.collection.documents = [_stored_document(BEN, ["Java"])]
    response = _call("GET", "/api/me/resume")
    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "not_found"
    assert error["details"] == {"resource": "resume"}


def test_get_my_resume_requires_authentication() -> None:
    app.dependency_overrides.pop(current_user, None)
    assert _call("GET", "/api/me/resume").status_code in (401, 403)


def test_upload_is_503_and_stores_nothing_when_suggestions_fail(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(user_id: UUID) -> list[Skill]:
        raise SqlAccessError("Your confirmed skills could not be read.")

    monkeypatch.setattr(resumes, "confirmed_skills", broken)
    response = _upload()
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "service_unavailable"
    # The previous resume is untouched: the store was never called.
    assert "store" not in world.events
    assert world.stored == []


def test_get_my_resume_503_uses_service_unavailable_code(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    world.collection.documents = [_stored_document(ANA, ["Python"])]
    monkeypatch.setattr(
        resumes,
        "get_all_skills",
        lambda: (_ for _ in ()).throw(SkillsRepositoryError("down")),
    )
    response = _call("GET", "/api/me/resume")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "service_unavailable"
