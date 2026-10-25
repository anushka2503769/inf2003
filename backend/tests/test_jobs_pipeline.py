"""Synthetic checks for job identity, extraction evidence, and SQL link replacement."""

import os
from contextlib import contextmanager
from uuid import UUID

import psycopg2
import psycopg2.errors
import pytest

from app import dependencies, job_skill_extraction, jobs, jobs_external_multi
from app.auth import AuthenticatedUser
from app.errors import ApiError
from app.job_sources import ProviderJobError, normalize_provider_job
from app.sql_access import (
    SqlAccessError,
    job_pipeline_lock,
    job_read_lock,
    job_write_lock,
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


def test_read_lock_is_shared_after_lock_timeout(monkeypatch) -> None:
    connection = _Connection()
    monkeypatch.setattr("app.sql_access.get_pg_connection", lambda: connection)
    with job_read_lock():
        statements = [query for query, _ in connection.cursor_obj.statements]
        assert statements[0] == "SET LOCAL lock_timeout = '3s'"
        assert "pg_advisory_xact_lock_shared" in statements[1]
        assert connection.cursor_obj.statements[1][1] == (2003001,)
        assert not connection.committed
    assert connection.committed is False


def test_write_lock_is_exclusive_after_lock_timeout(monkeypatch) -> None:
    connection = _Connection()
    monkeypatch.setattr("app.sql_access.get_pg_connection", lambda: connection)
    with job_write_lock():
        statements = [query for query, _ in connection.cursor_obj.statements]
        assert statements[0] == "SET LOCAL lock_timeout = '3s'"
        assert "pg_advisory_xact_lock_shared" not in statements[1]
        assert "pg_advisory_xact_lock(" in statements[1]
        assert connection.cursor_obj.statements[1][1] == (2003001,)


def test_legacy_pipeline_lock_name_means_read_lock() -> None:
    assert job_pipeline_lock is job_read_lock


class _TimeoutCursor(_Cursor):
    def execute(self, query, params=()):
        super().execute(query, params)
        if "pg_advisory" in query:
            error = psycopg2.errors.LockNotAvailable("canceling statement due to lock timeout")
            raise error


@pytest.mark.parametrize("lock", [job_read_lock, job_write_lock])
def test_lock_timeout_becomes_busy_sql_access_error(monkeypatch, lock) -> None:
    connection = _Connection()
    connection.cursor_obj = _TimeoutCursor()
    monkeypatch.setattr("app.sql_access.get_pg_connection", lambda: connection)
    with pytest.raises(SqlAccessError, match="busy"):
        with lock():
            raise AssertionError("a timed-out lock must not enter the route")
    assert connection.committed is False


def _drive(dependency, *args):
    generator = dependency(*args)
    try:
        next(generator)
    finally:
        generator.close()


@pytest.fixture
def recorded_locks(monkeypatch):
    calls: list[str] = []

    @contextmanager
    def fake(name):
        calls.append(name)
        yield

    monkeypatch.setattr(dependencies, "job_read_lock", lambda: fake("read"))
    monkeypatch.setattr(dependencies, "job_write_lock", lambda: fake("write"))
    monkeypatch.setattr(dependencies, "get_db", lambda: object())
    return calls


def test_read_dependency_takes_shared_and_admin_dependency_exclusive(recorded_locks) -> None:
    user = AuthenticatedUser(user_id="00000000-0000-0000-0000-000000000001")
    _drive(dependencies.get_authenticated_job_db, user)
    assert recorded_locks == ["read"]
    _drive(dependencies.get_admin_job_db, user)
    assert recorded_locks == ["read", "write"]


def test_read_and_admin_routes_are_wired_to_the_right_dependencies() -> None:
    from fastapi.routing import APIRoute

    def deps(path: str, method: str) -> set:
        route = next(
            r
            for r in jobs.router.routes
            if isinstance(r, APIRoute) and r.path == path and method in r.methods
        )
        stack, found = [route.dependant], set()
        while stack:
            node = stack.pop()
            found.add(node.call)
            stack.extend(node.dependencies)
        return found

    assert dependencies.get_authenticated_job_db in deps("/api/jobs/{job_id}", "GET")
    assert dependencies.get_admin_job_db not in deps("/api/jobs/{job_id}", "GET")
    assert dependencies.get_admin_job_db in deps("/api/jobs/{job_id}", "DELETE")
    assert dependencies.get_authenticated_job_db not in deps("/api/jobs/{job_id}", "DELETE")


def test_lock_timeout_maps_to_503_service_unavailable(monkeypatch) -> None:
    @contextmanager
    def busy():
        raise SqlAccessError("SQL job synchronization is busy; retry shortly.")
        yield

    monkeypatch.setattr(dependencies, "job_read_lock", busy)
    monkeypatch.setattr(dependencies, "job_write_lock", busy)
    user = AuthenticatedUser(user_id="00000000-0000-0000-0000-000000000001")
    for dependency in (dependencies.get_authenticated_job_db, dependencies.get_admin_job_db):
        with pytest.raises(ApiError) as caught:
            _drive(dependency, user)
        assert caught.value.status_code == 503
        assert caught.value.code == "service_unavailable"


_TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "").strip()


@pytest.mark.skipif(not _TEST_DATABASE_URL, reason="Set TEST_DATABASE_URL to run.")
def test_real_postgres_shared_locks_coexist_and_writer_times_out(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", _TEST_DATABASE_URL)
    from app import config

    config.get_settings.cache_clear()
    try:
        with job_read_lock(), job_read_lock():
            with pytest.raises(SqlAccessError, match="busy"):
                with job_write_lock():
                    raise AssertionError("writer must wait behind readers")
        with job_write_lock():
            with pytest.raises(SqlAccessError, match="busy"):
                with job_read_lock():
                    raise AssertionError("reader must wait behind a writer")
        with job_write_lock():  # all locks released by the rollbacks above
            pass
    finally:
        config.get_settings.cache_clear()


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
