"""Pure-Python parts of the WP-10 seed and benchmark scripts (no database needed)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import benchmark  # noqa: E402
import seed_synthetic  # noqa: E402

GOOD_PG = "postgresql://postgres:pw@127.0.0.1:5432/postgres"
GOOD_MONGO = "mongodb://127.0.0.1:27017/?directConnection=true"


@pytest.fixture(autouse=True)
def _clean_libpq_env(monkeypatch):
    for name in seed_synthetic.ROUTING_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


@pytest.mark.parametrize(
    "pg",
    [
        GOOD_PG,
        "postgresql://postgres:pw@localhost:5432/postgres",
        "postgresql://postgres:pw@127.0.0.1/postgres?hostaddr=127.0.0.1",
    ],
)
def test_local_postgres_urls_are_accepted(pg):
    seed_synthetic.assert_local_urls(pg, GOOD_MONGO)


@pytest.mark.parametrize(
    "pg",
    [
        "postgresql://postgres:pw@db.example.supabase.co:5432/postgres",
        "postgresql://postgres:pw@127.0.0.1.evil.example:5432/postgres",
        "postgresql://localhost@remote.example/postgres",
        "postgresql:///postgres",  # no host
        "",
        # bypasses of a naive authority-only check
        "postgresql://u:p@127.0.0.1/db?host=remote.example",
        "postgresql://u:p@127.0.0.1/db?hostaddr=203.0.113.1",
        "postgresql://u:p@127.0.0.1/db?host=127.0.0.1,remote.example",
        "postgresql://u:p@127.0.0.1/db?service=prod",
        "postgresql://u:p@127.0.0.1/db?servicefile=/tmp/x",
        "host=remote.example dbname=x",
    ],
)
def test_non_local_postgres_urls_are_refused(pg):
    with pytest.raises(seed_synthetic.NotLocalError):
        seed_synthetic.assert_local_urls(pg, GOOD_MONGO)


@pytest.mark.parametrize(
    "mongo",
    [
        "mongodb+srv://user:pw@cluster0.example.mongodb.net/",
        "mongodb+srv://127.0.0.1/",
        "mongodb://127.0.0.1:27017,remote.example:27017/",
        "mongodb://127.0.0.1:27017,127.0.0.1:27018/",
        "mongodb://remote.example:27017/",
        "mongodb://localhost.evil.example:27017/",
        "",
    ],
)
def test_non_local_mongo_uris_are_refused(mongo):
    with pytest.raises(seed_synthetic.NotLocalError):
        seed_synthetic.assert_local_urls(GOOD_PG, mongo)


@pytest.mark.parametrize("name", seed_synthetic.ROUTING_ENV_VARS)
def test_inherited_libpq_routing_env_is_refused(monkeypatch, name):
    monkeypatch.setenv(name, "anything")
    with pytest.raises(seed_synthetic.NotLocalError):
        seed_synthetic.assert_local_urls(GOOD_PG, GOOD_MONGO)
    with pytest.raises(seed_synthetic.NotLocalError):
        seed_synthetic.seed(GOOD_PG, GOOD_MONGO, "x", n_jobs=10)


def test_seed_refuses_before_touching_any_database():
    with pytest.raises(seed_synthetic.NotLocalError):
        seed_synthetic.seed(
            "postgresql://postgres:pw@db.example.supabase.co:5432/postgres",
            GOOD_MONGO,
            "x",
            n_jobs=10,
        )


def test_seed_cli_exits_2_for_a_remote_url(capsys):
    code = seed_synthetic.main(
        [
            "--database-url",
            "postgresql://postgres:pw@db.example.supabase.co:5432/postgres",
            "--mongodb-uri",
            GOOD_MONGO,
        ]
    )
    assert code == 2
    assert "Refusing to run" in capsys.readouterr().err


def test_dataset_is_deterministic_and_within_spec():
    skills = list(range(1, 151))
    first = seed_synthetic.build_dataset(300, skills, seed=7, heavy_rows=100)
    again = seed_synthetic.build_dataset(300, skills, seed=7, heavy_rows=100)
    other = seed_synthetic.build_dataset(300, skills, seed=8, heavy_rows=100)
    assert first == again
    assert first != other

    per_job: dict[str, int] = {}
    for job_id, skill_id, _ in first["job_skills"]:
        per_job[job_id] = per_job.get(job_id, 0) + 1
        assert skill_id in skills
    assert len(per_job) == 300
    assert all(3 <= n <= 12 for n in per_job.values())

    assert len(first["users"]) == 51  # 50 plus the heavy user
    per_user_skills: dict[str, int] = {}
    for user_id, _ in first["user_skills"]:
        per_user_skills[user_id] = per_user_skills.get(user_id, 0) + 1
    assert all(5 <= n <= 20 for n in per_user_skills.values())

    tracker: dict[str, int] = {}
    for user_id, *_ in first["user_jobs"]:
        tracker[user_id] = tracker.get(user_id, 0) + 1
    heavy = seed_synthetic.user_id_for(seed_synthetic.USER_COUNT)
    assert tracker[heavy] == 100
    assert all(n <= 50 for user, n in tracker.items() if user != heavy)

    assert len(first["documents"]) == 300
    doc = first["documents"][0]
    assert doc["extracted_data"]["provider"]["ready"] == "true"
    assert all(isinstance(r["skill_id"], int) for r in doc["extracted_data"]["requirements"])


def test_percentile_and_summary():
    assert benchmark.percentile([5], 95) == 5
    assert benchmark.percentile([1, 2, 3, 4], 50) == 2.5
    assert benchmark.percentile(list(range(1, 101)), 95) == pytest.approx(95.05)
    assert benchmark.percentile([3, 1, 2], 0) == 1
    assert benchmark.percentile([3, 1, 2], 100) == 3
    with pytest.raises(ValueError):
        benchmark.percentile([], 50)
    with pytest.raises(ValueError):
        benchmark.percentile([1], 101)
    summary = benchmark.summarize([10, 20, 30, 40, 50])
    assert summary == {"n": 5, "median": 30, "p95": pytest.approx(48)}


def test_measure_runs_warmups_then_timed_calls():
    calls = []
    stats = benchmark.measure(lambda: calls.append(1), warmups=3, runs=30)
    assert len(calls) == 33
    assert stats["n"] == 30


def test_speedup_wording():
    assert benchmark.speedup(10, 5) == "x2.0 faster"
    assert benchmark.speedup(5, 10) == "x2.0 slower"
    assert benchmark.speedup(10, 10.2) == "about the same"


def test_index_ddl_is_taken_from_migration_003():
    text = (
        Path(__file__).resolve().parents[2] / "docs/DB/003_views_triggers_indexes.sql"
    ).read_text()
    ddl = benchmark.extract_sql_index_ddl(text, benchmark.SQL_INDEXES)
    assert set(ddl) == set(benchmark.SQL_INDEXES)
    assert ddl["jobs_active_posted_at_idx"].endswith("WHERE is_active;")
    assert "(user_id, status)" in ddl["user_jobs_user_status_idx"]
    with pytest.raises(RuntimeError):
        benchmark.extract_sql_index_ddl(text, ["no_such_index"])
