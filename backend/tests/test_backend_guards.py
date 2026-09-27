"""Offline regression tests for backend security and storage boundaries."""

from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi import HTTPException

from app import db, skills_repository
from app.auth import AuthenticatedUser
from app.config import get_settings
from app.document_access import replace_current_resume
from app.errors import ApiError
from app.resumes_read import delete_resume, get_resume
from app.schemas import ExtractedData
from app.skills_repository import SkillsRepositoryError


def test_mongodb_connection_is_lazy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MONGODB_URI", raising=False)
    get_settings.cache_clear()
    db.reset_client_for_tests()
    with pytest.raises(ApiError) as caught:
        db.get_db()
    assert caught.value.status_code == 503
    get_settings.cache_clear()


def test_skill_lookup_has_no_static_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(skills_repository, "_cache", [])
    monkeypatch.setattr(skills_repository, "_cache_loaded_at", 0.0)
    monkeypatch.setattr(
        skills_repository,
        "_fetch_skills_from_sql",
        lambda: (_ for _ in ()).throw(RuntimeError("database unavailable")),
    )
    with pytest.raises(SkillsRepositoryError):
        skills_repository.get_all_skills(force_refresh=True)


class _ReplaceResult:
    upserted_id = "generated-id"


class _ResumeCollection:
    def __init__(self) -> None:
        self.filter = None
        self.document = None
        self.upsert = None

    def replace_one(self, filter_: dict, document: dict, *, upsert: bool) -> _ReplaceResult:
        self.filter = filter_
        self.document = document
        self.upsert = upsert
        return _ReplaceResult()


class _Database:
    def __init__(self, collection: _ResumeCollection) -> None:
        self.collection = collection

    def __getitem__(self, name: str) -> _ResumeCollection:
        assert name == "resume_documents"
        return self.collection


def test_resume_replacement_is_user_scoped_and_upserted() -> None:
    collection = _ResumeCollection()
    document = {
        "user_id": str(UUID("11111111-1111-4111-8111-111111111111")),
        "file_name": "resume.pdf",
        "raw_text": "Python",
        "extracted_data": {"skills": ["Python"], "education": [], "experience": [], "projects": []},
        "uploaded_at": datetime.now(UTC),
    }
    stored = replace_current_resume(_Database(collection), document)
    assert collection.filter == {"user_id": document["user_id"]}
    assert collection.upsert is True
    assert stored["_id"] == "generated-id"


class _ReadCollection:
    def __init__(self) -> None:
        self.find_query = None
        self.delete_query = None

    def find_one(self, query: dict):
        self.find_query = query
        return None

    def delete_one(self, query: dict):
        self.delete_query = query
        return type("DeleteResult", (), {"deleted_count": 0})()


class _ReadDatabase:
    def __init__(self, collection: _ReadCollection) -> None:
        self.collection = collection

    def __getitem__(self, name: str) -> _ReadCollection:
        assert name == "resume_documents"
        return self.collection


def test_resume_reads_and_deletes_filter_by_authenticated_user() -> None:
    collection = _ReadCollection()
    db_handle = _ReadDatabase(collection)
    user = AuthenticatedUser(user_id=UUID("11111111-1111-4111-8111-111111111111"))
    with pytest.raises(HTTPException):
        get_resume(user, "507f1f77bcf86cd799439011", db_handle)
    assert collection.find_query["user_id"] == str(user.user_id)
    with pytest.raises(HTTPException):
        delete_resume(user, "507f1f77bcf86cd799439011", db_handle)
    assert collection.delete_query["user_id"] == str(user.user_id)


def test_resume_sections_preserve_flexible_mongo_objects() -> None:
    extracted = ExtractedData(
        skills=[],
        education=[{"institution": "SIT", "degree": "Computing"}],
        experience=[{"company": "Example Co", "role": "Intern"}],
        projects=[{"name": "Simulator", "technologies": ["Python"]}],
    )
    assert extracted.education[0]["institution"] == "SIT"
    assert extracted.projects[0]["technologies"] == ["Python"]
