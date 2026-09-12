# Jobless Simulator — MVP PRD

Status: provisional MVP baseline, 9 September 2026. The professor considers the
current database skeleton suitable as a starting point; refine it as the module progresses.
This document distinguishes the runnable auth shell from planned product functionality.

## Goal

Help students discover internships/entry-level jobs matching their confirmed skills,
understand gaps for another target role, and track opportunities through external applications.
INF2003 requires meaningful relational and non-relational database implementation.
The application should be complete, explainable and small enough for all five members to maintain.

## Team and framework

- Zhihao: moderator, final review, consolidation and integration.
- Nasya and Anuska: frontend.
- Jason and Jiaxin: backend and database integration.
- Frontend: React + TypeScript + Vite; npm with package-lock.json.
- Backend: Python 3.14 + FastAPI; uv with uv.lock; pytest and Ruff.
- Planned databases: Supabase/PostgreSQL and MongoDB.
- Browser talks to Python through `/api`; Python will own database and provider integrations.
- No additional queue server, cache service, microservices or container orchestration for the base.

## Framework acceptance criteria (current delivery)

- A teammate can install both projects using the README and lockfiles.
- Frontend provides Google sign-in, onboarding and profile screens through the development proxy.
- Backend verifies bearer tokens, returns a typed health response, and exposes profile routes and OpenAPI documentation.
- The profile store is process-local memory; it is a development seam for the planned PostgreSQL integration.
- Frontend build/type checks and backend test/lint checks are repeatable locally and in CI.
- Supabase configuration is required for real sign-in; no database service is required for this auth-shell slice.

## Product MVP (planned, not implemented by the framework setup)

### Profile

Upload a resume, extract text and structured information, then let the student confirm
or edit skills. Confirmed skills belong in SQL. MongoDB retains one current resume's
text and extraction JSON per user. Replacing a resume overwrites that current document;
no original PDF storage, download feature or upload history.

### Discover

Show active, unreviewed jobs matching session filters, ranked by an explainable skill
comparison. Filters include location, job type and work arrangement, not stored user
preferences. Show matched/missing skills; describe scores as skill coverage, not hiring probability.
Job types: FULL_TIME, PART_TIME, INTERNSHIP (a full-time internship is classified as INTERNSHIP).
Work arrangements: ONSITE, HYBRID, REMOTE; unknown values remain unknown.

Left swipe records NOT_INTERESTED; right swipe records SAVED. Both enter the tracker
and disappear from discovery. No requeue. Empty state offers changing filters or checking
for new jobs; refreshing does not guarantee unseen results.

### Swipe persistence

Respond immediately in the UI, retain pending decisions in browser storage scoped to
the signed-in user, and synchronize small batches during use. Keep the latest pending
decision per job. Clear only acknowledged versions: a response to an older request must
not erase a newer local decision. Retry failures without duplicate rows. Do not rely on
browser-close delivery. Batch thresholds, concurrent-tab/device conflict rules and
ordering against later application-status edits must be resolved before this feature is built.
Measure immediate writes versus batching; batching reduces requests, not the number of
underlying records that need persistence.

### Vault / tracker

Show saved and not-interested jobs with filters. One user-job row holds current status:
NOT_INTERESTED, SAVED, APPLIED, INTERVIEW, REJECTED, OFFER. Students can change their
mind. Apply opens the provider's URL; status changes remain manual. No status-history table.

### Target-role search / skill gap

A student with SWE skills may search for Financial Analyst. Aggregate requirements
from actual relevant job documents, then compare with their confirmed skills. Proposed
ownership: MongoDB aggregates target-role requirements; SQL supports individual job matching.
Show sample size, skill frequencies, matched skills and gaps. Preserve evidence and any
explicit experience requirements. Presence in user_skills does not prove years of experience;
show experience as unconfirmed. Never invent missing requirements or treat failed extraction
as a skill-free job. Define denominator, role categorization and required/preferred treatment
before finalizing calculations.

### Job ingestion and extraction

Start with one provider and approximately 200–500 recent relevant listings if coverage allows.
Manual refresh normalizes and upserts by unique (source, external_job_id). Existing provider
IDs update existing jobs; user_jobs still excludes reviewed jobs per user. Reposts under new
IDs or across providers need a later duplicate policy. Do not infer closure from one missing
search result. Provider choice, rate limits, coverage and permitted use must be verified first.

Use a small LLM extraction layer for resumes and JDs; reuse stored output for browsing
and analytics. Map extracted skill names to shared skill IDs in application normalization,
not invented LLM IDs. Re-extract changed JDs; define how SQL links and MongoDB documents
become ready together and how partial failures recover. The LLM does not autonomously rank
jobs or change application statuses. Semantic matching is desired but its method/storage
and contribution to scoring remain open; no vector infrastructure is selected yet.

## Data skeleton

See [erd.md](erd.md) for fields, types, keys and cardinalities.

SQL: users, skills, user_skills, jobs, job_skills, user_jobs.
MongoDB: resume_documents, job_documents.
Cross-database UUID references are application-managed, not foreign keys.
No migrations or live collections are provisioned in this framework delivery.

## Product verification before calling the MVP complete

- A student can complete upload → confirm → discover → save → external apply → track.
- A target-role query uses real stored requirements and shows a reproducible calculation.
- Both databases demonstrate useful CRUD/query operations and appropriate constraints/indexes.
- Refreshing repeated provider results creates no duplicate provider listings.
- Already-reviewed jobs stay excluded, including after reload and refresh.
- Rapid decisions, connection loss, retry and reload preserve the latest intended state.
- One user's pending decisions and records cannot appear in another user's account.
- Missing skills, empty datasets, extraction failures and partial database writes have honest states.
- Compare selected SQL/NoSQL operations on equivalent inputs where useful; report measured
  behaviour and limitations. Grade depends on demonstrated work, not table count or infrastructure.

## Still open

Account deletion and referential actions; external job and LLM providers;
normalization/role taxonomy; ranking and semantic method; batch thresholds and
conflict handling; inactive-job policy; SQL/Mongo recovery; final Mongo validation and indexing;
deployment; frontend feature-test tooling. Schema refinements require discussion and PRD/ERD updates.

## Non-goals

Employer/recruiter portals, internal applications, automatic applications, resume rewriting,
interview coaching/scheduling, salary or hiring-success predictions, complex career roadmaps,
LinkedIn/MCF scraping dependencies, multi-agent workflows, Kafka, distributed background workers,
real-time ingestion and complex RAG pipelines.
