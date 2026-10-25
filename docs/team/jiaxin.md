# Jiaxin — MongoDB and document access

> **Current work (PRD v2, 25 Oct 2026):** WP-4 (MongoDB skill gap + Mongo integration tests), WP-5 (ingestion columns, skip-and-continue, CLI) and the live ingestion run. Specs, allowed files and
> acceptance criteria are in [PRD.md §5](../PRD.md); shapes in [API.md](../API.md).
> Task IDs below are from the first milestone; check their progress notes before reusing them.

Read [team workflow](README.md), [PRD](../PRD.md), [ERD](../erd.md),
[MongoDB setup](../DB/README.md#mongodb) and the [API contract](../API.md).
Own MongoDB deployment/document work. Jason owns shared Python auth and SQL access.

## JIA-01 — prepare and verify MongoDB development storage

- Select/configure the intended team development deployment using the available account
  and explicit target authorization. Discuss costs before choosing a paid resource.
- Arrange appropriate project access for Zhihao and a database user scoped to the
  application database. Keep credentials outside Git; document names, not secret values.
- Review/apply docs/DB/001_initial_collections.js according to DB/README.md. It is not
  atomic; inspect and repair partial setup rather than dropping existing collections.
- Verify validators and unique reference indexes using synthetic records: valid insert,
  duplicate user/job reference, missing/wrong field types and resume replacement.
- Use isolated synthetic IDs and remove only your own fixtures. Test parent-reference
  handling separately: MongoDB itself cannot prove SQL IDs exist.

Done when: both collections, validators and indexes are inspected on the intended
deployment, checks are recorded and current-resume replacement is demonstrated.

## JIA-02 — minimal Python MongoDB access

Planned owned files: backend/app/documents.py and backend/tests/test_documents.py.

- Coordinate driver/config additions with Jason before changing backend shared files.
  Keep one settings/auth implementation. Agree the document-module call signatures with
  Jason before another feature depends on them.
- Implement only current-resume and current-job document read/write operations needed
  by the skeleton, with predictable missing-document behaviour and explicit database selection.
- Test BSON date/ID handling, duplicate protection, replacement and error behaviour.
  Unit fixtures can run without the SQL API. Live tests must be explicitly selected
  and must not reset a shared database.

Done when: the access module can be tested independently, failures are surfaced clearly,
and no real credentials/resumes are in fixtures or logs. No public document endpoints
are implied; the first profile/skill milestone does not yet depend on MongoDB.

## Later work — discuss before implementation

Resume upload/extraction, JD processing and role-gap aggregation belong here later.
They need contracts, provider selection and normalization/SQL consistency decisions.
Do not choose an LLM/job provider, invent endpoints or start a background-worker system
as part of JIA-01/02. Raise ambiguities in validators for team review.

## Progress

Initial status: JIA-01/02 not verified complete. The bootstrap has syntax/simulated-shell
checks only; no deployment, live enforcement or Python document module is verified.
Inspect current code before work. Append task/result/check/PR/next-step notes here.

### WP-5 progress note (overnight 2026-10-26)

- Branch: `feat/wp5-ingestion`; commit: (filled in by orchestrator).
- Built: normalizers now fill `location` (null instead of "Not specified"), `job_type`,
  `work_arrangement`, `source_posted_at`; upsert writes them, refreshes `last_seen_at`, keeps
  `first_seen_at` and reports inserted vs updated (`xmax = 0`); fetch-multi skips bad records
  and returns `summary`; `backend/scripts/ingest_jobs.py` (provider sources and
  `--file` for the LinkedIn Apify export, no network for `--file`).
- Checks: `ruff check`, `ruff format --check`, `pytest` (64 passed, 39 skipped without a
  database) and `bash backend/scripts/run_disposable_db_tests.sh` (103 passed).
- Unverified: not run against Supabase/MongoDB or the real LinkedIn export. Human step, from
  `backend/`: `uv run --env-file .env python scripts/ingest_jobs.py --file ../data/raw/linkedin_sg_<date>.json`
  then `uv run --env-file .env python scripts/ingest_jobs.py --sources arbeitnow devitjobs_uk --limit-per-source 200`;
  paste the printed summary into the report. DevITjobs and AI Dev Jobs date/type field names are
  best guesses (their payloads are only partly documented); check the first live summary.
- Exit code: 1 when nothing was inserted or updated and there was an error (or no jobs were found),
  or on an unrecoverable exception; 0 otherwise (partial failures still print their errors).
- Open question: `API.md` section 9 now documents `summary` (shape change). See the report.

#### WP-5 fix round (overnight 2026-10-26)

- Nothing-stored status rule: 422 only if every rejection was validation (pre-storage or Mongo
  schema validation); any storage/outage rejection makes it 503 (API.md section 9 updated).
- Intern matching: `intern`, `interns`, `internship(s)` not followed by a letter, so
  "Internship2026" matches while "Internal"/"International" do not. Open question for Zhihao:
  this deviates from the literal "title contains intern".
- `FetchSummary` / `FetchJobsWithSummaryResponse` moved to `backend/app/schemas.py` (appended).
- Open question (strict xfail `test_reextraction_keeps_imported_linkedin_industry`): re-extraction
  (`backend/app/jobs_extraction_router.py` `_extract_one`) calls `extract_skills_from_job(doc["raw_jd"])`
  with plain `descriptionText`, so imported industry and title context are lost (industry becomes
  "Unclassified"). Required change outside WP-5 files: in `_extract_one`, build the extraction input from the
  stored document (e.g. prefix the title from `extracted_data.provider.title`) and, after extraction, keep
  the existing `extracted_data.industry` when the new value is "Unclassified" (or when the document's source is
  `linkedin_apify`).
