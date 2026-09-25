# Job pipeline boundary

Provider refresh is an administrator operation. Each provider record must include
an explicit stable `external_job_id` and an `http` or `https` application URL; the
pipeline never derives identity from a title. SQL upserts by `(source,
external_job_id)`, then the current Mongo `job_documents` record is replaced using
the returned SQL `job_id`.

The SQL parent is staged inactive while Mongo is being replaced. It becomes active
only after the document is durable, and the document carries a nested readiness
marker while the operation is in progress. A failed refresh returns a retryable
service error and leaves the job inactive and the document pending. Repeating
the same provider record updates one SQL parent, one Mongo document, and replaces
its canonical `job_skills` links, so removed requirements do not remain linked.

Mongo `job_documents` follows the strict top-level shape from `docs/DB/001_initial_collections.js`.
Provider metadata such as title, company, source, external ID, URL, and readiness is
stored under `extracted_data.provider`; it is never written as a top-level `title`.
Evidence must be nonblank text copied from the source description. Explicit years
are retained when they occur near the matching skill. Requirement strength uses a
small preferred-language heuristic and defaults to `REQUIRED`; this is not an NLP
or LLM judgment and does not expand extraction beyond the source text.

Manual ingestion first validates the SQL parent, replaces the current Mongo
document, and synchronizes canonical SQL skill links. Re-extraction uses the same
link replacement. Job reads require authentication; provider refresh, manual
ingestion, re-extraction, duplicate preview, and deletion controls require the
configured admin allowlist.

Every job document route holds one transaction-scoped PostgreSQL advisory lock while
it reads or updates SQL and Mongo. Job reads require both `ready=true` in Mongo and
an active SQL parent, so pending or legacy documents remain hidden. SQL-only reports
query the active parent directly. Duplicate deletion
and direct job-document deletion return `409` until a cross-store
policy exists that can preserve SQL `user_jobs` references. The duplicate endpoint
therefore remains a read-only admin preview. Synthetic unit tests can verify normalizers,
extraction, SQL statement ordering, and route authorization without real providers or
databases. A live SQL/Mongo refresh still requires the team-owned development services
and is not proven by local import, lint, or mock checks.
