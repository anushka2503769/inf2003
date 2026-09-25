"""Synthetic checks for job identity, extraction evidence, and SQL link replacement."""

from uuid import UUID

import pytest

from app import job_skill_extraction, jobs, jobs_external_multi
from app.auth import AuthenticatedUser
from app.errors import ApiError
from app.job_sources import ProviderJobError, normalize_provider_job
from app.sql_access import (
    SqlAccessError,
    job_pipeline_lock,
    replace_job_skills,
    upsert_provider_job,
)


def test_provider_identity_requires_explicit_id_and_url() -> None:
    record = normalize_provider_job(
        {
            "source": "synthetic",
            "external_job_id": "posting-7",
            "title": "Python Developer",
            "company": "Example Co",
            "url": "https://example.test/jobs/7",
        }
    )
    assert record["external_job_id"] == "posting-7"
    with pytest.raises(ProviderJobError):
        normalize_provider_job({**record, "external_job_id": ""})
    with pytest.raises(ProviderJobError):
        normalize_provider_job({**record, "url": ""})
    with pytest.raises(ProviderJobError):
        normalize_provider_job({**record, "external_job_id": None})
    with pytest.raises(ProviderJobError):
        normalize_provider_job({**record, "external_job_id": True})
    assert normalize_provider_job({**record, "external_job_id": 7})["external_job_id"] == "7"


@pytest.mark.parametrize("field", ["source", "title", "company", "url"])
def test_provider_null_fields_are_rejected(field: str) -> None:
    record = {
        "source": "synthetic",
        "external_job_id": "posting-7",
        "title": "Python Developer",
        "company": "Example Co",
        "url": "https://example.test/jobs/7",
    }
    with pytest.raises(ProviderJobError):
        normalize_provider_job({**record, field: None})


def test_sql_provider_null_identity_is_rejected_before_connection() -> None:
    with pytest.raises(SqlAccessError):
        upsert_provider_job(
            {
                "source": "synthetic",
                "external_job_id": None,
                "title": "Python Developer",
                "company": "Example Co",
                "url": "https://example.test/jobs/7",
            },
            {},
        )


def test_extraction_keeps_source_evidence_and_nearby_years(monkeypatch) -> None:
    monkeypatch.setattr(
        job_skill_extraction,
        "match_skills_with_ids",
        lambda text, *, require_database: [(7, "Python"), (8, "SQL")],
    )
    extracted = job_skill_extraction.extract_skills_from_job(
        "Python Developer must use Python with 3+ years experience. SQL is preferred."
    )
    assert extracted["requirements"] == [
        {
            "skill_id": 7,
            "requirement_type": "REQUIRED",
            "minimum_years": 3,
            "evidence": "Python Developer must use Python with 3+ years experience.",
        },
        {
            "skill_id": 8,
            "requirement_type": "PREFERRED",
            "minimum_years": None,
            "evidence": "SQL is preferred.",
        },
    ]


class _Cursor:
    def __init__(self, fetchone_result=(1,)):
        self.statements = []
        self.fetchone_result = fetchone_result

    def execute(self, query, params=()):
        self.statements.append((query, params))

    def fetchone(self):
        return self.fetchone_result

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


class _Connection:
    def __init__(self):
        self.cursor_obj = _Cursor()
        self.committed = False

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.committed = True

    def rollback(self):
        self.committed = False

    def close(self):
        pass


def test_replace_job_skills_deletes_stale_links(monkeypatch) -> None:
    connection = _Connection()
    monkeypatch.setattr("app.sql_access.get_pg_connection", lambda: connection)
    job_id = "00000000-0000-0000-0000-000000000007"
    replace_job_skills(
        job_id,
        [{"skill_id": 4, "requirement_type": "REQUIRED", "evidence": "Python"}],
    )
    assert connection.committed
    assert UUID(job_id)
    assert "DELETE FROM public.job_skills" in connection.cursor_obj.statements[1][0]
    assert connection.cursor_obj.statements[-1][1] == (job_id, 4, "REQUIRED")


def test_job_pipeline_lock_uses_transaction_lifecycle(monkeypatch) -> None:
    connection = _Connection()
    monkeypatch.setattr("app.sql_access.get_pg_connection", lambda: connection)
    with job_pipeline_lock():
        assert "pg_try_advisory_xact_lock" in connection.cursor_obj.statements[0][0]
        assert not connection.committed
    assert connection.committed is False


def test_job_pipeline_lock_rejects_contention(monkeypatch) -> None:
    connection = _Connection()
    connection.cursor_obj = _Cursor((False,))
    monkeypatch.setattr("app.sql_access.get_pg_connection", lambda: connection)
    with pytest.raises(SqlAccessError, match="busy"):
        with job_pipeline_lock():
            raise AssertionError("the busy lock must not enter the route")
    assert connection.committed is False


class _JobCollection:
    def __init__(self, document=None):
        self.document = document
        self.find_filter = None
        self.count_filter = None
        self.update_calls = []

    def find_one(self, query, *args):
        self.find_filter = query
        query_values = [query]
        if "$and" in query:
            query_values.extend(query["$and"])
        if (
            any("extracted_data.provider.ready" in value for value in query_values)
            and self.document
        ):
            ready = self.document.get("extracted_data", {}).get("provider", {}).get("ready")
            if ready == "false":
                return None
        return self.document

    def update_one(self, query, update):
        self.update_calls.append((query, update))

    def count_documents(self, query):
        self.count_filter = query
        return 0

    def find(self, query, *args):
        self.find_filter = query
        return self

    def sort(self, *args):
        return self

    def skip(self, *args):
        return self

    def limit(self, *args):
        return self

    def __iter__(self):
        return iter(())


class _Mongo:
    def __init__(self, collection):
        self.collection = collection

    def __getitem__(self, name):
        assert name == "job_documents"
        return self.collection


def test_get_job_hides_pending_documents(monkeypatch) -> None:
    monkeypatch.setattr(jobs, "get_active_job_ids", lambda: {"job-7"})
    collection = _JobCollection(
        {
            "_id": "mongo-id",
            "job_id": "job-7",
            "extracted_at": "2026-09-19T00:00:00Z",
            "extracted_data": {
                "role_category": "engineering",
                "requirements": [],
                "responsibilities": [],
                "provider": {"ready": "false"},
            },
        }
    )
    with pytest.raises(ApiError) as caught:
        jobs.get_job(
            "job-7",
            AuthenticatedUser(user_id=UUID("11111111-1111-4111-8111-111111111111")),
            _Mongo(collection),
        )
    assert caught.value.status_code == 404
    assert {"extracted_data.provider.ready": "true"} in collection.find_filter["$and"]
    assert {"job_id": {"$in": ["job-7"]}} in collection.find_filter["$and"]


def test_job_list_requires_explicit_ready_and_active_sql_id(monkeypatch) -> None:
    monkeypatch.setattr(jobs, "get_active_job_ids", lambda: {"job-7"})
    collection = _JobCollection()
    response = jobs.list_jobs(
        AuthenticatedUser(user_id=UUID("11111111-1111-4111-8111-111111111111")),
        _Mongo(collection),
        skip=0,
        limit=20,
        role_category=None,
        industry=None,
    )
    assert response.total_count == 0
    assert collection.count_filter == {
        "job_id": {"$in": ["job-7"]},
        "extracted_data.provider.ready": "true",
    }


def test_provider_failure_forces_sql_inactive_and_mongo_pending(monkeypatch) -> None:
    calls = []
    collection = _JobCollection()
    monkeypatch.setattr(
        jobs_external_multi,
        "set_job_active",
        lambda job_id, active: calls.append((job_id, active)),
    )
    jobs_external_multi._mark_provider_pending("job-7", _Mongo(collection))
    assert calls == [("job-7", False)]
    assert collection.update_calls[0][1] == {"$set": {"extracted_data.provider.ready": "false"}}
