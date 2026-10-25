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


# ---------------------------------------------------------------------------
# WP-5: normalizer fields, LinkedIn file import, skip-and-continue, CLI, SQL columns
# ---------------------------------------------------------------------------
import argparse  # noqa: E402
import importlib.util  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import socket  # noqa: E402
import time  # noqa: E402
from contextlib import contextmanager  # noqa: E402
from datetime import datetime, timezone  # noqa: E402
from pathlib import Path  # noqa: E402

from pymongo.errors import PyMongoError  # noqa: E402

from app import job_sources  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"
LINKEDIN_FIXTURE = FIXTURES / "linkedin_apify_sample.json"


class _FakeResponse:
    def __init__(self, payload=None, content=b""):
        self._payload = payload
        self.content = content

    def raise_for_status(self) -> None:
        pass

    def json(self):
        return self._payload


def _fixture_json(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _deny_network(monkeypatch) -> None:
    def refuse(*_args, **_kwargs):
        raise AssertionError("network access is not allowed in this test")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(job_sources.requests, "get", refuse)
    monkeypatch.setattr(job_sources.requests.Session, "request", refuse)


def _iso(epoch: int) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()


def test_arbeitnow_normalizer_fields(monkeypatch) -> None:
    payload = _fixture_json("arbeitnow_sample.json")
    monkeypatch.setattr(job_sources.time, "sleep", lambda *_: None)
    monkeypatch.setattr(job_sources.requests, "get", lambda *a, **k: _FakeResponse(payload))
    intern, remote, bare = job_sources.fetch_arbeitnow(10)
    assert (intern["location"], intern["job_type"], intern["work_arrangement"]) == (
        "Berlin",
        "INTERNSHIP",
        "HYBRID",
    )
    assert intern["source_posted_at"] == _iso(1760000000)
    assert intern["external_job_id"] == "python-intern-example-1"
    assert (remote["location"], remote["job_type"], remote["work_arrangement"]) == (
        None,
        "PART_TIME",
        "REMOTE",
    )
    assert remote["remote"] is True
    assert (bare["location"], bare["job_type"], bare["work_arrangement"]) == (None, None, None)
    assert bare["source_posted_at"] is None


def test_devitjobs_normalizer_fields(monkeypatch) -> None:
    xml = (FIXTURES / "devitjobs_uk_sample.xml").read_bytes()
    monkeypatch.setattr(job_sources.requests, "get", lambda *a, **k: _FakeResponse(content=xml))
    intern, remote, bare = job_sources.fetch_devitjobs_uk(10)
    assert (intern["location"], intern["job_type"], intern["work_arrangement"]) == (
        "Leeds (Hybrid)",
        "INTERNSHIP",
        "HYBRID",
    )
    assert intern["source_posted_at"] == "2026-10-12T00:00:00+00:00"
    assert (remote["location"], remote["job_type"], remote["work_arrangement"]) == (
        "Remote, UK",
        "FULL_TIME",
        "REMOTE",
    )
    assert remote["source_posted_at"] is None
    assert (bare["location"], bare["job_type"], bare["work_arrangement"]) == (None, None, None)


def test_ai_dev_jobs_normalizer_fields_and_unreadable_record(monkeypatch) -> None:
    payload = _fixture_json("ai_dev_jobs_sample.json")

    def fake_get(url, params=None, **_kwargs):
        return _FakeResponse(payload if params["page"] == 1 else {"jobs": []})

    monkeypatch.setattr(job_sources.time, "sleep", lambda *_: None)
    monkeypatch.setattr(job_sources.requests, "get", fake_get)
    intern, remote, onsite, unreadable = job_sources.fetch_ai_dev_jobs(10)
    assert (intern["location"], intern["job_type"], intern["work_arrangement"]) == (
        "London",
        "INTERNSHIP",
        "HYBRID",
    )
    assert intern["source_posted_at"] == "2026-10-10T12:00:00+00:00"
    assert (remote["location"], remote["job_type"], remote["work_arrangement"]) == (
        None,
        "FULL_TIME",
        "REMOTE",
    )
    assert remote["source_posted_at"] == "2026-10-11T00:00:00+00:00"
    assert remote["url"] == "https://www.example.com/aidev/2"
    assert (onsite["job_type"], onsite["work_arrangement"]) == ("PART_TIME", "ONSITE")
    assert onsite["source_posted_at"] is None
    # A non-object entry becomes a stub that validation rejects on its own.
    assert unreadable == {"source": "ai_dev_jobs", "external_job_id": None}
    valid, errors = job_sources.validate_provider_jobs([intern, remote, onsite, unreadable])
    assert len(valid) == 3 and errors == [
        "ai_dev_jobs: Provider job is missing a stable external job ID."
    ]


def test_field_inference_helpers() -> None:
    assert job_sources.infer_job_type("Internal Auditor", "Full Time") == "FULL_TIME"
    assert job_sources.infer_job_type("Summer Intern", ["Full Time"]) == "INTERNSHIP"
    assert job_sources.infer_job_type("Engineer", "Contract") is None
    assert job_sources.clean_location("  Not specified ") is None
    assert job_sources.clean_location(" Singapore ") == "Singapore"
    assert job_sources.parse_posted_at(1760000000000) == _iso(1760000000)
    assert job_sources.parse_posted_at("garbage") is None
    assert job_sources.infer_work_arrangement("Hybrid, Remote friendly") == "HYBRID"
    assert job_sources.infer_work_arrangement("remote sensing lab") is None
    assert job_sources.infer_work_arrangement("anything", remote_flag=True) == "REMOTE"


def test_linkedin_file_mapping(monkeypatch) -> None:
    _deny_network(monkeypatch)
    jobs, errors = job_sources.load_linkedin_apify_file(LINKEDIN_FIXTURE)
    by_id = {job["external_job_id"]: job for job in jobs}
    assert sorted(by_id) == [f"90000{n:02d}" for n in range(1, 9)]
    assert {job["source"] for job in jobs} == {"linkedin_apify"}

    first = by_id["9000001"]
    assert first["company"] == "Example Analytics Pte Ltd"
    assert first["url"] == "https://careers.example.com/apply/9000001"  # http(s) applyUrl wins
    assert first["location"] == "Singapore"
    assert first["source_posted_at"] == "2026-10-20T00:00:00+00:00"
    assert first["job_type"] == "INTERNSHIP"
    assert first["work_arrangement"] == "HYBRID"
    assert first["raw_jd"] == first["description"] and "Python and SQL" in first["raw_jd"]
    assert first["industry"] == "IT Services and IT Consulting"
    assert first["responsibilities"] == ["Build dashboards", "Clean datasets"]

    remote = by_id["9000002"]  # empty applyUrl falls back to the page url
    assert remote["url"] == "https://www.example.com/jobs/view/9000002/"
    assert (remote["job_type"], remote["work_arrangement"]) == ("FULL_TIME", "REMOTE")

    part_time = by_id["9000003"]  # non-http applyUrl falls back to the page url
    assert part_time["url"] == "https://www.example.com/jobs/view/9000003/"
    assert (part_time["job_type"], part_time["work_arrangement"]) == ("PART_TIME", "ONSITE")

    for contract_or_temp in ("9000004", "9000005"):
        assert by_id[contract_or_temp]["job_type"] is None
    assert by_id["9000004"]["work_arrangement"] is None

    by_title = by_id["9000006"]  # no employmentType, "Intern" in the title
    assert by_title["job_type"] == "INTERNSHIP"
    assert by_title["source_posted_at"] is None and by_title["industry"] is None

    assert (by_id["9000007"]["job_type"], by_id["9000007"]["work_arrangement"]) == (
        "FULL_TIME",
        "ONSITE",
    )
    by_type = by_id["9000008"]  # employmentType alone makes it an internship; date only
    assert by_type["job_type"] == "INTERNSHIP"
    assert by_type["source_posted_at"] == "2026-10-14T00:00:00+00:00"

    assert errors == [
        "linkedin_apify: Provider job is missing a stable external job ID.",
        "linkedin_apify/9000010: Provider job is missing title or company.",
    ]


def test_linkedin_file_rejects_other_shapes(tmp_path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text('{"source": "linkedin_apify", "jobs": "nope"}', encoding="utf-8")
    with pytest.raises(ProviderJobError):
        job_sources.load_linkedin_apify_file(bad)
    with pytest.raises(ProviderJobError):
        job_sources.load_linkedin_apify_file(tmp_path / "missing.json")


class _FakeMongoCollection:
    def __init__(self, fail_for=()):
        self.documents = {}
        self.ready = {}
        self.fail_for = set(fail_for)
        self.pending = []

    def replace_one(self, query, document, upsert=False):
        if document["job_id"] in self.fail_for:
            raise PyMongoError("simulated outage")
        self.documents[document["job_id"]] = document
        return type("Result", (), {"upserted_id": f"doc-{document['job_id'][-2:]}"})()

    def find_one(self, query, projection=None):
        return {"_id": "existing"}

    def update_one(self, query, update):
        value = update["$set"]["extracted_data.provider.ready"]
        self.ready[query["job_id"]] = value


class _FakeMongoDb:
    def __init__(self, collection):
        self.collection = collection

    def __getitem__(self, name):
        assert name == "job_documents"
        return self.collection


def _install_fake_stores(monkeypatch, *, existing=(), fail=(), mongo_fail=()):
    """Replace extraction and SQL with fakes; return (collection, active_calls)."""
    active_calls: list[tuple[str, bool]] = []
    ids: dict[str, UUID] = {}

    def fake_upsert(job, extracted):
        external_id = job["external_job_id"]
        if external_id in fail:
            raise SqlAccessError("SQL job upsert failed; no fetched job is confirmed.")
        job_id = ids.setdefault(external_id, UUID(int=len(ids) + 1))
        return job_id, external_id not in existing

    monkeypatch.setattr(
        jobs_external_multi,
        "extract_skills_from_job",
        lambda raw, *, require_database: {
            "role_category": "Other",
            "industry": "Unclassified",
            "requirements": [],
            "responsibilities": [],
            "provider": {"source": "x"},
        },
    )
    monkeypatch.setattr(jobs_external_multi, "upsert_provider_job_with_status", fake_upsert)
    monkeypatch.setattr(
        jobs_external_multi,
        "set_job_active",
        lambda job_id, active: active_calls.append((job_id, active)),
    )
    mongo_fail_ids = {str(UUID(int=i)) for i in mongo_fail}
    return _FakeMongoCollection(fail_for=mongo_fail_ids), active_calls


def test_skip_and_continue_counts_and_documents(monkeypatch) -> None:
    jobs, rejected = job_sources.load_linkedin_apify_file(LINKEDIN_FIXTURE)
    # 9000002 already exists (update); 9000005 fails in SQL; the 3rd stored job fails in Mongo.
    collection, active_calls = _install_fake_stores(
        monkeypatch, existing={"9000002"}, fail={"9000005"}, mongo_fail={3}
    )
    stored, summary = jobs_external_multi.ingest_provider_jobs(
        _FakeMongoDb(collection), jobs, rejected
    )
    assert summary.requested == 10
    assert (summary.inserted, summary.updated, summary.rejected) == (5, 1, 4)
    assert len(summary.errors) == 4
    assert len(stored) == 6
    # errors[:2] are the records refused before storage; then Mongo (3rd job), then SQL.
    assert summary.errors[2] == (
        "linkedin_apify/9000003: Job refresh could not be completed; retry is safe."
    )
    assert summary.errors[3] == (
        "linkedin_apify/9000005: SQL job upsert failed; no fetched job is confirmed."
    )
    assert all(
        "simulated outage" not in error and "descriptionText" not in error
        for error in summary.errors
    )
    # The failed Mongo write left that job inactive; stored jobs were activated.
    assert (str(UUID(int=3)), False) in active_calls
    first_doc = collection.documents[str(UUID(int=1))]
    assert first_doc["raw_jd"].startswith("Join our team for a hybrid internship")
    assert first_doc["extracted_data"]["industry"] == "IT Services and IT Consulting"
    assert collection.ready[str(UUID(int=1))] == "true"


def test_fetch_multi_route_summary_and_total_failure(monkeypatch) -> None:
    good = {
        "source": "synthetic",
        "external_job_id": "a",
        "title": "Engineer",
        "company": "Example Co",
        "url": "https://example.test/a",
        "location": None,
        "job_type": None,
        "work_arrangement": None,
        "source_posted_at": None,
    }
    records = [good, {**good, "external_job_id": "b"}, {**good, "external_job_id": ""}]
    monkeypatch.setitem(job_sources.SOURCE_REGISTRY, "synthetic", lambda limit: list(records))
    collection, _ = _install_fake_stores(monkeypatch, existing={"b"})
    response = jobs_external_multi.fetch_and_store_jobs_multi(
        _FakeMongoDb(collection), sources=["synthetic"], limit_per_source=5, total_limit=None
    )
    assert response.fetched_count == 2
    assert response.summary.model_dump() == {
        "requested": 3,
        "inserted": 1,
        "updated": 1,
        "rejected": 1,
        "errors": ["synthetic: Provider job is missing a stable external job ID."],
    }

    # Every record invalid: 422 with the summary in details, nothing stored.
    monkeypatch.setitem(
        job_sources.SOURCE_REGISTRY, "synthetic", lambda limit: [{**good, "title": ""}]
    )
    with pytest.raises(ApiError) as invalid:
        jobs_external_multi.fetch_and_store_jobs_multi(
            _FakeMongoDb(collection), sources=["synthetic"], limit_per_source=5, total_limit=None
        )
    assert invalid.value.status_code == 422
    assert invalid.value.details["summary"]["rejected"] == 1

    # Every record fails in storage: 503.
    monkeypatch.setitem(job_sources.SOURCE_REGISTRY, "synthetic", lambda limit: [good])
    _install_fake_stores(monkeypatch, fail={"a"})
    with pytest.raises(ApiError) as outage:
        jobs_external_multi.fetch_and_store_jobs_multi(
            _FakeMongoDb(collection), sources=["synthetic"], limit_per_source=5, total_limit=None
        )
    assert outage.value.status_code == 503


def _load_ingest_script():
    path = Path(__file__).resolve().parents[1] / "scripts" / "ingest_jobs.py"
    spec = importlib.util.spec_from_file_location("ingest_jobs_script", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fake_stores(db):
    @contextmanager
    def stores():
        yield db

    return stores


def test_ingest_cli_argument_parsing() -> None:
    script = _load_ingest_script()
    default = script.parse_args([])
    assert default.sources == ["arbeitnow"] and default.file is None
    parsed = script.parse_args(
        ["--sources", "arbeitnow", "devitjobs_uk", "--limit-per-source", "200"]
    )
    assert parsed.sources == ["arbeitnow", "devitjobs_uk"] and parsed.limit_per_source == 200
    assert script.parse_args(["--file", "export.json"]).file == Path("export.json")
    with pytest.raises(SystemExit):
        script.parse_args(["--file", "export.json", "--sources", "arbeitnow"])
    with pytest.raises(SystemExit):
        script.parse_args(["--limit-per-source", "0"])


def test_ingest_cli_file_import_prints_summary_without_network(monkeypatch) -> None:
    script = _load_ingest_script()
    _deny_network(monkeypatch)
    collection, _ = _install_fake_stores(monkeypatch)
    printed: list[str] = []

    def forbidden_collect(*_args, **_kwargs):
        raise AssertionError("--file must not call a provider")

    code = script.run(
        script.parse_args(["--file", str(LINKEDIN_FIXTURE)]),
        collect=forbidden_collect,
        stores=_fake_stores(_FakeMongoDb(collection)),
        out=printed.append,
    )
    assert code == 0
    summary = json.loads(printed[-1])
    assert summary["requested"] == 10 and summary["inserted"] == 8
    assert summary["rejected"] == 2 and len(summary["errors"]) == 2


def test_ingest_cli_sources_use_the_same_pipeline(monkeypatch) -> None:
    script = _load_ingest_script()
    calls = []
    job = {
        "source": "synthetic",
        "external_job_id": "a",
        "title": "Engineer",
        "company": "Example Co",
        "url": "https://example.test/a",
    }

    def fake_collect(sources, limit_per_source):
        calls.append((sources, limit_per_source))
        return [job], ["synthetic: Provider job is missing a stable external job ID."]

    collection, _ = _install_fake_stores(monkeypatch)
    printed: list[str] = []
    code = script.run(
        script.parse_args(["--sources", "arbeitnow", "devitjobs_uk", "--limit-per-source", "200"]),
        collect=fake_collect,
        stores=_fake_stores(_FakeMongoDb(collection)),
        out=printed.append,
    )
    assert calls == [(["arbeitnow", "devitjobs_uk"], 200)]
    assert code == 0  # partial failure is not total failure
    assert json.loads(printed[-1])["rejected"] == 1


def test_ingest_cli_exit_codes_on_total_failure(monkeypatch, tmp_path) -> None:
    script = _load_ingest_script()
    collection, _ = _install_fake_stores(monkeypatch, fail={"a"})
    job = {
        "source": "synthetic",
        "external_job_id": "a",
        "title": "Engineer",
        "company": "Example Co",
        "url": "https://example.test/a",
    }
    args = script.parse_args(["--sources", "arbeitnow"])
    stores = _fake_stores(_FakeMongoDb(collection))

    # Nothing stored and an error reported.
    printed: list[str] = []
    assert (
        script.run(args, collect=lambda *a, **k: ([job], []), stores=stores, out=printed.append)
        == 1
    )
    assert json.loads(printed[-1])["rejected"] == 1

    # Nothing found at all counts as failure too.
    printed = []
    assert (
        script.run(args, collect=lambda *a, **k: ([], []), stores=stores, out=printed.append) == 1
    )
    assert json.loads(printed[-1])["errors"] == ["No jobs were found in the input."]

    # Unrecoverable exceptions: provider down, unreadable file, database unreachable.
    def provider_down(*_a, **_k):
        raise ProviderJobError("Job source 'arbeitnow' is unavailable.")

    printed = []
    assert script.run(args, collect=provider_down, stores=stores, out=printed.append) == 1
    assert "unavailable" in printed[-1]
    missing = script.parse_args(["--file", str(tmp_path / "missing.json")])
    assert script.run(missing, stores=stores, out=printed.append) == 1

    @contextmanager
    def unreachable():
        raise RuntimeError("DATABASE_URL is not configured.")
        yield

    printed = []
    assert (
        script.run(
            args, collect=lambda *a, **k: ([job], []), stores=unreachable, out=printed.append
        )
        == 1
    )
    assert "DATABASE_URL" in printed[-1]


def test_ingest_cli_namespace_has_no_env_loading() -> None:
    script = _load_ingest_script()
    source = Path(script.__file__).read_text(encoding="utf-8")
    assert "dotenv" not in source and "load_dotenv" not in source
    assert isinstance(script.parse_args([]), argparse.Namespace)


# --- SQL columns against a disposable database (skipped without TEST_DATABASE_URL) ---

_TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "").strip()
requires_database = pytest.mark.skipif(
    not _TEST_DATABASE_URL,
    reason="Set TEST_DATABASE_URL to a throwaway PostgreSQL database to run this.",
)


@pytest.fixture
def jobs_database(monkeypatch):
    import psycopg2

    from app import config

    monkeypatch.setenv("DATABASE_URL", _TEST_DATABASE_URL)
    config.get_settings.cache_clear()

    def clean() -> None:
        conn = psycopg2.connect(_TEST_DATABASE_URL)
        try:
            with conn.cursor() as cursor:
                cursor.execute("DELETE FROM public.jobs WHERE source = 'wp5-test'")
            conn.commit()
        finally:
            conn.close()

    clean()
    yield psycopg2
    clean()
    config.get_settings.cache_clear()


@requires_database
def test_upsert_writes_columns_and_preserves_first_seen(jobs_database) -> None:
    from app.sql_access import upsert_provider_job_with_status

    job = {
        "source": "wp5-test",
        "external_job_id": "x-1",
        "title": "Data Intern",
        "company": "Example Co",
        "url": "https://example.test/x-1",
        "location": "Singapore",
        "job_type": "INTERNSHIP",
        "work_arrangement": "HYBRID",
        "source_posted_at": "2026-10-20T00:00:00+00:00",
    }

    def row(job_id):
        conn = jobs_database.connect(_TEST_DATABASE_URL)
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT location, job_type, work_arrangement, source_posted_at,"
                    " first_seen_at, last_seen_at, is_active FROM public.jobs WHERE job_id = %s",
                    (job_id,),
                )
                return cursor.fetchone()
        finally:
            conn.close()

    job_id, inserted = upsert_provider_job_with_status(job, {"requirements": []})
    assert inserted is True
    first = row(job_id)
    assert first[:3] == ("Singapore", "INTERNSHIP", "HYBRID")
    assert first[3] == datetime(2026, 10, 20, tzinfo=timezone.utc)
    assert first[6] is False

    time.sleep(0.05)
    changed = {**job, "location": None, "job_type": "FULL_TIME", "work_arrangement": None}
    changed["source_posted_at"] = "2026-10-21T00:00:00+00:00"
    second_id, inserted_again = upsert_provider_job_with_status(changed, {"requirements": []})
    assert second_id == job_id and inserted_again is False
    second = row(job_id)
    assert second[:3] == (None, "FULL_TIME", None)
    assert second[3] == datetime(2026, 10, 21, tzinfo=timezone.utc)
    assert second[4] == first[4]  # first_seen_at is never overwritten
    assert second[5] > first[5]  # last_seen_at is refreshed

    with pytest.raises(SqlAccessError):
        upsert_provider_job_with_status({**job, "job_type": "CONTRACT"}, {"requirements": []})
